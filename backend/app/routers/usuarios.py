"""Gestão de usuários (apenas administradores)."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .. import auth
from ..database import db_session, now_iso
from ..schemas import UsuarioEdicao, UsuarioNovo

router = APIRouter(
    prefix="/api/usuarios",
    tags=["usuarios"],
    dependencies=[Depends(auth.exigir_admin)],
)


def _admins_ativos(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM usuarios WHERE papel = 'admin' AND situacao = 'ativo'").fetchone()[0]


@router.get("")
def listar() -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM usuarios ORDER BY nome COLLATE NOCASE").fetchall()
        return [auth.usuario_publico(r) for r in rows]


@router.post("", status_code=201)
def criar(body: UsuarioNovo) -> dict[str, Any]:
    with db_session() as conn:
        if conn.execute("SELECT 1 FROM usuarios WHERE login = ?", (body.login,)).fetchone():
            raise HTTPException(status_code=409, detail="Já existe um usuário com esse login.")
        cur = conn.execute(
            "INSERT INTO usuarios (login, nome, senha_hash, papel, situacao, created_at) "
            "VALUES (?, ?, ?, ?, 'ativo', ?)",
            (body.login, body.nome.strip(), auth.hash_senha(body.senha), body.papel, now_iso()),
        )
        row = conn.execute("SELECT * FROM usuarios WHERE id = ?", (cur.lastrowid,)).fetchone()
        return auth.usuario_publico(row)


@router.patch("/{usuario_id}")
def editar(usuario_id: int, body: UsuarioEdicao) -> dict[str, Any]:
    with db_session() as conn:
        row = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        novo_papel = body.papel if body.papel is not None else row["papel"]
        nova_situacao = body.situacao if body.situacao is not None else row["situacao"]
        novo_ativo = nova_situacao == "ativo"
        era_admin_ativo = row["papel"] == "admin" and row["situacao"] == "ativo"
        continua_admin_ativo = novo_papel == "admin" and novo_ativo
        if era_admin_ativo and not continua_admin_ativo and _admins_ativos(conn) <= 1:
            raise HTTPException(status_code=400, detail="O sistema precisa de pelo menos um administrador ativo.")

        conn.execute(
            "UPDATE usuarios SET nome = ?, papel = ?, situacao = ? WHERE id = ?",
            (body.nome.strip() if body.nome else row["nome"], novo_papel, nova_situacao, usuario_id),
        )
        if body.senha:
            conn.execute(
                "UPDATE usuarios SET senha_hash = ? WHERE id = ?", (auth.hash_senha(body.senha), usuario_id)
            )
        if body.senha or not novo_ativo:
            auth.encerrar_sessoes_do_usuario(conn, usuario_id)
        atualizado = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        return auth.usuario_publico(atualizado)
