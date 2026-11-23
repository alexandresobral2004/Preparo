"""Autenticação: hash de senha, sessões em cookie e dependências de acesso."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request

from .database import adotar_dados_legados, db_session, now_iso

COOKIE_SESSAO = "preparo_sessao"
SESSAO_DIAS = 30
MAX_FALHAS = 5
JANELA_BLOQUEIO_S = 15 * 60
SENHA_MIN = 8
MAX_PENDENTES = 50  # contas aguardando aprovação; evita encher o banco com cadastros falsos

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1

# Tentativas erradas por login nos últimos 15 min (memória do processo; um único worker).
_falhas: dict[str, list[float]] = {}


def hash_senha(senha: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(senha.encode(), salt=sal, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P,
        base64.b64encode(sal).decode(), base64.b64encode(h).decode(),
    )


def verificar_senha(senha: str, armazenado: str) -> bool:
    try:
        algoritmo, n, r, p, sal_b64, h_b64 = armazenado.split("$")
        if algoritmo != "scrypt":
            return False
        esperado = base64.b64decode(h_b64)
        calculado = hashlib.scrypt(
            senha.encode(), salt=base64.b64decode(sal_b64), n=int(n), r=int(r), p=int(p), dklen=len(esperado)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculado, esperado)


# Usado quando o login não existe, para o tempo de resposta não revelar isso.
_HASH_FALSO = hash_senha(secrets.token_urlsafe(16))


def _chave(login: str) -> str:
    return login.strip().lower()


def bloqueado(login: str) -> bool:
    agora = time.monotonic()
    chave = _chave(login)
    recentes = [t for t in _falhas.get(chave, []) if agora - t < JANELA_BLOQUEIO_S]
    if recentes:
        _falhas[chave] = recentes
    else:
        _falhas.pop(chave, None)  # sem tentativas na janela, não guarda a chave (evita crescer sem limite)
    return len(recentes) >= MAX_FALHAS


def registrar_falha(login: str) -> None:
    _falhas.setdefault(_chave(login), []).append(time.monotonic())


def limpar_falhas(login: str | None = None) -> None:
    if login is None:
        _falhas.clear()
    else:
        _falhas.pop(_chave(login), None)


def autenticar(conn: sqlite3.Connection, login: str, senha: str) -> sqlite3.Row | None:
    """Devolve o usuário se login e senha conferem (qualquer situação); senão None.

    Identificador com "@" é e-mail; sem "@" é o login antigo. Uma só regra, nos dois casos hash verificado.
    """
    identificador = login.strip()
    if "@" in identificador:
        row = conn.execute("SELECT * FROM usuarios WHERE email = ?", (identificador.lower(),)).fetchone()
    else:
        row = conn.execute("SELECT * FROM usuarios WHERE login = ?", (identificador,)).fetchone()
    senha_ok = verificar_senha(senha, row["senha_hash"] if row else _HASH_FALSO)
    if row is None or not senha_ok:
        return None
    return row


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def criar_sessao(conn: sqlite3.Connection, usuario_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expira = datetime.now(timezone.utc) + timedelta(days=SESSAO_DIAS)
    conn.execute(
        "INSERT INTO sessoes (token_hash, usuario_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (_hash_token(token), usuario_id, now_iso(), expira.isoformat()),
    )
    return token


def encerrar_sessao(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessoes WHERE token_hash = ?", (_hash_token(token),))


def encerrar_sessoes_do_usuario(
    conn: sqlite3.Connection, usuario_id: int, manter_token: str | None = None
) -> None:
    if manter_token:
        conn.execute(
            "DELETE FROM sessoes WHERE usuario_id = ? AND token_hash != ?",
            (usuario_id, _hash_token(manter_token)),
        )
    else:
        conn.execute("DELETE FROM sessoes WHERE usuario_id = ?", (usuario_id,))


def usuario_da_sessao(conn: sqlite3.Connection, token: str | None) -> sqlite3.Row | None:
    if not token:
        return None
    row = conn.execute(
        """
        SELECT u.* FROM sessoes s JOIN usuarios u ON u.id = s.usuario_id
        WHERE s.token_hash = ? AND s.expires_at > ? AND u.situacao = 'ativo'
        """,
        (_hash_token(token), now_iso()),
    ).fetchone()
    return row


def usuario_publico(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "login": row["login"],
        "email": row["email"],
        "nome": row["nome"],
        "papel": row["papel"],
        "situacao": row["situacao"],
        "grau": row["grau"],
        "nucleo": row["nucleo"],
    }


def cookie_seguro() -> bool:
    return os.environ.get("PREPARO_COOKIE_SECURE", "").lower() in {"1", "true", "sim"}


def exigir_login(request: Request) -> dict[str, Any]:
    with db_session() as conn:
        row = usuario_da_sessao(conn, request.cookies.get(COOKIE_SESSAO))
        if row is None:
            raise HTTPException(status_code=401, detail="Faça login para continuar.")
        return usuario_publico(row)


def exigir_admin(usuario: dict[str, Any] = Depends(exigir_login)) -> dict[str, Any]:
    if usuario["papel"] != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores podem fazer isso.")
    return usuario


def garantir_admin_inicial() -> None:
    """Cria o primeiro administrador a partir do ambiente, só se não houver nenhum usuário."""
    login = os.environ.get("PREPARO_ADMIN_LOGIN", "").strip()
    senha = os.environ.get("PREPARO_ADMIN_SENHA", "")
    if not login or not senha:
        return
    with db_session() as conn:
        if conn.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone():
            return
        email = login.lower() if "@" in login else None
        cur = conn.execute(
            "INSERT INTO usuarios (login, nome, senha_hash, papel, situacao, created_at, email) "
            "VALUES (?, ?, ?, 'admin', 'ativo', ?, ?)",
            (login, login, hash_senha(senha), now_iso(), email),
        )
        adotar_dados_legados(conn, cur.lastrowid)
