"""Gestão de usuários (apenas administradores)."""

from __future__ import annotations

import json
import secrets
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .. import auth
from ..database import db_session, now_iso
from ..schemas import PREFIXO_USUARIO_REMOVIDO, UsuarioEdicao, UsuarioNovo

router = APIRouter(
    prefix="/api/usuarios",
    tags=["usuarios"],
    dependencies=[Depends(auth.exigir_admin)],
)

NOME_REMOVIDO = "Usuário removido"

# Tabelas que apontam para o usuário: se houver qualquer linha, a conta não pode sumir do banco.
_VINCULOS_SQL = """
SELECT EXISTS(SELECT 1 FROM preparos WHERE criado_por = :id)
    OR EXISTS(SELECT 1 FROM preparo_membros WHERE usuario_id = :id)
    OR EXISTS(SELECT 1 FROM registros WHERE criado_por_id = :id OR atualizado_por_id = :id)
    OR EXISTS(SELECT 1 FROM blocos WHERE criado_por_id = :id OR editado_por_id = :id)
"""


def _email_em_uso(conn: sqlite3.Connection, email: str, usuario_id: int | None = None) -> bool:
    """E-mail (ou login antigo igual) de outra conta. Em criação, usuario_id é None."""
    return conn.execute(
        "SELECT 1 FROM usuarios WHERE (email = ? OR login = ?) AND id IS NOT ?", (email, email, usuario_id)
    ).fetchone() is not None


def _admins_ativos(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM usuarios WHERE papel = 'admin' AND situacao = 'ativo'").fetchone()[0]


def _preserva_admin(conn: sqlite3.Connection, row: sqlite3.Row, novo_papel: str, nova_situacao: str) -> None:
    era_admin_ativo = row["papel"] == "admin" and row["situacao"] == "ativo"
    continua_admin_ativo = novo_papel == "admin" and nova_situacao == "ativo"
    if era_admin_ativo and not continua_admin_ativo and _admins_ativos(conn) <= 1:
        raise HTTPException(status_code=400, detail="O sistema precisa de pelo menos um administrador ativo.")


def _usuario_visivel(conn: sqlite3.Connection, usuario_id: int) -> sqlite3.Row | None:
    """Contas anonimizadas se comportam como inexistentes para o admin."""
    row = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    if row is None or row["login"].lower().startswith(PREFIXO_USUARIO_REMOVIDO):
        return None
    return row


def _anonimiza(conn: sqlite3.Connection, usuario_id: int) -> None:
    """Tira a identidade da conta e mantém a linha (FKs e histórico continuam válidos)."""
    senha_descartada = auth.hash_senha(secrets.token_urlsafe(32))  # ninguém conhece: a conta não loga mais
    conn.execute(
        "UPDATE usuarios SET nome = ?, login = ?, email = NULL, senha_hash = ?, situacao = 'inativo', grau = '', nucleo = '' "
        "WHERE id = ?",
        (NOME_REMOVIDO, f"{PREFIXO_USUARIO_REMOVIDO}{usuario_id}", senha_descartada, usuario_id),
    )
    conn.execute("UPDATE registros SET criado_por_nome = ? WHERE criado_por_id = ?", (NOME_REMOVIDO, usuario_id))
    conn.execute("UPDATE registros SET atualizado_por_nome = ? WHERE atualizado_por_id = ?", (NOME_REMOVIDO, usuario_id))
    conn.execute("UPDATE blocos SET criado_por_nome = ? WHERE criado_por_id = ?", (NOME_REMOVIDO, usuario_id))
    conn.execute("UPDATE blocos SET editado_por_nome = ? WHERE editado_por_id = ?", (NOME_REMOVIDO, usuario_id))
    auth.encerrar_sessoes_do_usuario(conn, usuario_id)


def _anonimiza_rascunhos(conn: sqlite3.Connection, usuario_id: int) -> None:
    """Troca o nome do autor dentro do JSON dos rascunhos (a autoria dos blocos fica guardada ali)."""
    for row in conn.execute("SELECT preparo_id, payload_json FROM rascunhos").fetchall():
        try:
            payload = json.loads(row["payload_json"])
        except (ValueError, TypeError):
            continue  # payload corrompido não pode travar a exclusão; o rascunho segue sem troca
        if not isinstance(payload, dict) or not isinstance(payload.get("blocos"), list):
            continue
        alterou = False
        for bloco in payload["blocos"]:
            autoria = bloco.get("autoria") if isinstance(bloco, dict) else None
            if not isinstance(autoria, dict):
                continue
            for campo_id, campo_nome in (("criadoPorId", "criadoPorNome"), ("editadoPorId", "editadoPorNome")):
                if autoria.get(campo_id) == usuario_id and autoria.get(campo_nome) != NOME_REMOVIDO:
                    autoria[campo_nome] = NOME_REMOVIDO
                    alterou = True
        if alterou:
            conn.execute(
                "UPDATE rascunhos SET payload_json = ? WHERE preparo_id = ?",
                (json.dumps(payload, ensure_ascii=False), row["preparo_id"]),
            )


@router.get("")
def listar() -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM usuarios WHERE login NOT LIKE 'removido-%' ORDER BY nome COLLATE NOCASE"
        ).fetchall()
        return [auth.usuario_publico(r) for r in rows]


@router.post("", status_code=201)
def criar(body: UsuarioNovo) -> dict[str, Any]:
    with db_session() as conn:
        if _email_em_uso(conn, body.email):
            raise HTTPException(status_code=409, detail="Este e-mail já está em uso por outra conta.")
        cur = conn.execute(
            "INSERT INTO usuarios (login, email, nome, senha_hash, papel, situacao, created_at, grau, nucleo) "
            "VALUES (?, ?, ?, ?, ?, 'ativo', ?, ?, ?)",
            (body.email, body.email, body.nome, auth.hash_senha(body.senha), body.papel, now_iso(), body.grau, body.nucleo),
        )
        row = conn.execute("SELECT * FROM usuarios WHERE id = ?", (cur.lastrowid,)).fetchone()
        return auth.usuario_publico(row)


@router.patch("/{usuario_id}")
def editar(usuario_id: int, body: UsuarioEdicao, admin: dict[str, Any] = Depends(auth.exigir_admin)) -> dict[str, Any]:
    with db_session() as conn:
        row = _usuario_visivel(conn, usuario_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        novo_papel = body.papel if body.papel is not None else row["papel"]
        nova_situacao = body.situacao if body.situacao is not None else row["situacao"]
        if usuario_id == admin["id"] and (novo_papel != row["papel"] or nova_situacao != row["situacao"]):
            raise HTTPException(status_code=400, detail="Você não pode alterar o próprio papel ou situação.")
        novo_ativo = nova_situacao == "ativo"
        _preserva_admin(conn, row, novo_papel, nova_situacao)
        if body.email is not None and _email_em_uso(conn, body.email, usuario_id):
            raise HTTPException(status_code=409, detail="Este e-mail já está em uso por outra conta.")

        conn.execute(
            "UPDATE usuarios SET nome = ?, papel = ?, situacao = ?, grau = ?, nucleo = ?, "
            "email = COALESCE(?, email), "
            "login = CASE WHEN ? IS NOT NULL AND instr(login, '@') > 0 THEN ? ELSE login END "
            "WHERE id = ?",
            (
                body.nome if body.nome else row["nome"],
                novo_papel,
                nova_situacao,
                body.grau if body.grau is not None else row["grau"],
                body.nucleo if body.nucleo is not None else row["nucleo"],
                body.email,
                body.email,
                body.email,
                usuario_id,
            ),
        )
        if body.senha:
            conn.execute(
                "UPDATE usuarios SET senha_hash = ? WHERE id = ?", (auth.hash_senha(body.senha), usuario_id)
            )
        if body.senha or not novo_ativo:
            auth.encerrar_sessoes_do_usuario(conn, usuario_id)
        atualizado = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        return auth.usuario_publico(atualizado)


@router.delete("/{usuario_id}")
def excluir(usuario_id: int, admin: dict[str, Any] = Depends(auth.exigir_admin)) -> dict[str, bool]:
    """Sem histórico, apaga a conta. Com histórico, anonimiza: a linha fica e ninguém mais entra nela."""
    with db_session() as conn:
        row = _usuario_visivel(conn, usuario_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        if usuario_id == admin["id"]:
            raise HTTPException(status_code=400, detail="Você não pode excluir a própria conta.")
        # Quem chama é outro admin ativo, então _preserva_admin nunca dispara aqui; fica como rede de segurança.
        _preserva_admin(conn, row, row["papel"], "inativo")
        _anonimiza_rascunhos(conn, usuario_id)
        if conn.execute(_VINCULOS_SQL, {"id": usuario_id}).fetchone()[0]:
            _anonimiza(conn, usuario_id)
            return {"anonimizado": True}
        conn.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))  # sessões caem em cascata
        return {"anonimizado": False}
