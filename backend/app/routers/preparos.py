"""Preparos: criação, pedido de entrada e aprovação de membros pelo dono."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .. import auth
from ..auth import exigir_login
from ..database import db_session, now_iso
from ..schemas import MembroNovoIn, MembroSituacaoIn, PreparoNovo

router = APIRouter(prefix="/api/preparos", tags=["preparos"], dependencies=[Depends(exigir_login)])

_MSG_NAO_ENCONTRADO = (
    "Não encontramos uma pessoa cadastrada e ativa com esse e-mail. Confira o e-mail ou peça que ela se cadastre."
)


def _exigir_dono(conn: sqlite3.Connection, preparo_id: str, usuario_id: int) -> None:
    row = conn.execute(
        "SELECT 1 FROM preparo_membros WHERE preparo_id = ? AND usuario_id = ? "
        "AND papel = 'dono' AND situacao = 'aprovado'",
        (preparo_id, usuario_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=403, detail="Apenas o dono do preparo pode fazer isso.")


@router.get("")
def listar(usuario: dict[str, Any] = Depends(exigir_login)) -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.nome, u.nome AS dono_nome,
                   m.papel AS meu_papel, m.situacao AS minha_situacao, m.permissao AS minha_permissao,
                   (SELECT COUNT(*) FROM preparo_membros x
                     WHERE x.preparo_id = p.id AND x.situacao = 'pendente') AS pendentes
            FROM preparos p
            JOIN usuarios u ON u.id = p.criado_por
            LEFT JOIN preparo_membros m ON m.preparo_id = p.id AND m.usuario_id = ?
            ORDER BY p.nome COLLATE NOCASE
            """,
            (usuario["id"],),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "nome": r["nome"],
            "donoNome": r["dono_nome"],
            "meuPapel": r["meu_papel"],
            "minhaSituacao": r["minha_situacao"],
            "minhaPermissao": _minha_permissao(r),
            "pendentes": r["pendentes"] if r["meu_papel"] == "dono" else 0,
        }
        for r in rows
    ]


def _minha_permissao(r: sqlite3.Row) -> str | None:
    if r["meu_papel"] == "dono":
        return "editar"
    return r["minha_permissao"] if r["minha_situacao"] == "aprovado" else None


@router.post("", status_code=201)
def criar(body: PreparoNovo, usuario: dict[str, Any] = Depends(exigir_login)) -> dict[str, str]:
    preparo_id = uuid.uuid4().hex
    ts = now_iso()
    with db_session() as conn:
        conn.execute(
            "INSERT INTO preparos (id, nome, criado_por, created_at) VALUES (?, ?, ?, ?)",
            (preparo_id, body.nome.strip(), usuario["id"], ts),
        )
        conn.execute(
            "INSERT INTO preparo_membros (preparo_id, usuario_id, papel, situacao, created_at) "
            "VALUES (?, ?, 'dono', 'aprovado', ?)",
            (preparo_id, usuario["id"], ts),
        )
    return {"id": preparo_id, "nome": body.nome.strip()}


@router.post("/{preparo_id}/solicitar")
def solicitar(preparo_id: str, usuario: dict[str, Any] = Depends(exigir_login)) -> dict[str, str]:
    with db_session() as conn:
        if conn.execute("SELECT 1 FROM preparos WHERE id = ?", (preparo_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Preparo não encontrado.")
        atual = conn.execute(
            "SELECT situacao FROM preparo_membros WHERE preparo_id = ? AND usuario_id = ?",
            (preparo_id, usuario["id"]),
        ).fetchone()
        if atual is None:
            conn.execute(
                "INSERT INTO preparo_membros (preparo_id, usuario_id, papel, situacao, created_at) "
                "VALUES (?, ?, 'membro', 'pendente', ?)",
                (preparo_id, usuario["id"], now_iso()),
            )
            return {"situacao": "pendente"}
        if atual["situacao"] == "recusado":
            raise HTTPException(status_code=409, detail="O dono do preparo não liberou sua entrada.")
        return {"situacao": atual["situacao"]}


@router.get("/{preparo_id}/membros")
def listar_membros(preparo_id: str, usuario: dict[str, Any] = Depends(exigir_login)) -> list[dict[str, Any]]:
    with db_session() as conn:
        _exigir_dono(conn, preparo_id, usuario["id"])
        rows = conn.execute(
            """
            SELECT m.usuario_id, u.nome, u.login, u.email, m.papel, m.situacao, m.permissao
            FROM preparo_membros m JOIN usuarios u ON u.id = m.usuario_id
            WHERE m.preparo_id = ?
            ORDER BY CASE m.papel WHEN 'dono' THEN 0 ELSE 1 END, u.nome COLLATE NOCASE
            """,
            (preparo_id,),
        ).fetchall()
    return [
        {
            "usuarioId": r["usuario_id"],
            "nome": r["nome"],
            "login": r["login"],
            "email": r["email"],
            "papel": r["papel"],
            "situacao": r["situacao"],
            "permissao": r["permissao"],
        }
        for r in rows
    ]


@router.post("/{preparo_id}/membros")
def adicionar_membro(
    preparo_id: str,
    body: MembroNovoIn,
    usuario: dict[str, Any] = Depends(exigir_login),
) -> dict[str, Any]:
    """Dono adiciona uma pessoa cadastrada e ativa pelo e-mail: ela entra na hora, já aprovada."""
    chave = f"membro:{usuario['id']}"
    with db_session() as conn:
        _exigir_dono(conn, preparo_id, usuario["id"])
        if auth.bloqueado(chave):
            raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde 15 minutos e tente de novo.")
        pessoa = conn.execute(
            "SELECT id, nome FROM usuarios WHERE email = ? AND situacao = 'ativo'", (body.email,)
        ).fetchone()
        if pessoa is None:
            auth.registrar_falha(chave)
            raise HTTPException(status_code=404, detail=_MSG_NAO_ENCONTRADO)
        atual = conn.execute(
            "SELECT papel, situacao FROM preparo_membros WHERE preparo_id = ? AND usuario_id = ?",
            (preparo_id, pessoa["id"]),
        ).fetchone()
        if atual is None:
            try:
                conn.execute(
                    "INSERT INTO preparo_membros (preparo_id, usuario_id, papel, situacao, permissao, created_at) "
                    "VALUES (?, ?, 'membro', 'aprovado', ?, ?)",
                    (preparo_id, pessoa["id"], body.permissao, now_iso()),
                )
            except sqlite3.IntegrityError:
                pass  # corrida: outra requisição inseriu a mesma linha depois da checagem; relê abaixo
            atual = conn.execute(
                "SELECT papel, situacao FROM preparo_membros WHERE preparo_id = ? AND usuario_id = ?",
                (preparo_id, pessoa["id"]),
            ).fetchone()
        papel = atual["papel"]
        permissao = "editar" if papel == "dono" else body.permissao  # o dono nunca é rebaixado pelo convite
        if papel != "dono":  # pendente, recusado ou já aprovado: o convite explícito do dono aprova e define a permissão
            conn.execute(
                "UPDATE preparo_membros SET situacao = 'aprovado', permissao = ? WHERE preparo_id = ? AND usuario_id = ?",
                (permissao, preparo_id, pessoa["id"]),
            )
    return {
        "usuarioId": pessoa["id"],
        "nome": pessoa["nome"],
        "papel": papel,
        "situacao": "aprovado",
        "permissao": permissao,
    }


@router.patch("/{preparo_id}/membros/{usuario_id}")
def decidir_membro(
    preparo_id: str,
    usuario_id: int,
    body: MembroSituacaoIn,
    usuario: dict[str, Any] = Depends(exigir_login),
) -> dict[str, str]:
    with db_session() as conn:
        _exigir_dono(conn, preparo_id, usuario["id"])
        alvo = conn.execute(
            "SELECT papel FROM preparo_membros WHERE preparo_id = ? AND usuario_id = ?",
            (preparo_id, usuario_id),
        ).fetchone()
        if alvo is None:
            raise HTTPException(status_code=404, detail="Membro não encontrado.")
        if alvo["papel"] == "dono":
            raise HTTPException(status_code=400, detail="O dono do preparo não pode ser alterado.")
        # Permissão só muda ao aprovar; ao recusar, COALESCE mantém a que a linha já tem.
        permissao = body.permissao if body.situacao == "aprovado" else None
        conn.execute(
            "UPDATE preparo_membros SET situacao = ?, permissao = COALESCE(?, permissao) "
            "WHERE preparo_id = ? AND usuario_id = ?",
            (body.situacao, permissao, preparo_id, usuario_id),
        )
    return {"situacao": body.situacao}
