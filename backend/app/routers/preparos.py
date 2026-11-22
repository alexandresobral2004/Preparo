"""Preparos: criação, pedido de entrada e aprovação de membros pelo dono."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..auth import exigir_login
from ..database import db_session, now_iso
from ..schemas import MembroSituacaoIn, PreparoNovo

router = APIRouter(prefix="/api/preparos", tags=["preparos"], dependencies=[Depends(exigir_login)])


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
                   m.papel AS meu_papel, m.situacao AS minha_situacao,
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
            "pendentes": r["pendentes"] if r["meu_papel"] == "dono" else 0,
        }
        for r in rows
    ]


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
            raise HTTPException(status_code=409, detail="O dono do preparo recusou o seu pedido.")
        return {"situacao": atual["situacao"]}


@router.get("/{preparo_id}/membros")
def listar_membros(preparo_id: str, usuario: dict[str, Any] = Depends(exigir_login)) -> list[dict[str, Any]]:
    with db_session() as conn:
        _exigir_dono(conn, preparo_id, usuario["id"])
        rows = conn.execute(
            """
            SELECT m.usuario_id, u.nome, u.login, m.papel, m.situacao
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
            "papel": r["papel"],
            "situacao": r["situacao"],
        }
        for r in rows
    ]


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
        conn.execute(
            "UPDATE preparo_membros SET situacao = ? WHERE preparo_id = ? AND usuario_id = ?",
            (body.situacao, preparo_id, usuario_id),
        )
    return {"situacao": body.situacao}
