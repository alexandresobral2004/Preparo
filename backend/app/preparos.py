"""Contexto do preparo escolhido: só membros aprovados acessam os dados dele."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request

from .auth import exigir_login
from .database import db_session

HEADER_PREPARO = "X-Preparo-Id"


def preparo_atual(request: Request, usuario: dict[str, Any] = Depends(exigir_login)) -> dict[str, Any]:
    """Valida o preparo informado no cabeçalho e o vínculo aprovado do usuário com ele."""
    preparo_id = request.headers.get(HEADER_PREPARO, "").strip()
    if not preparo_id:
        raise HTTPException(status_code=400, detail="Escolha um preparo para continuar.")
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT p.id, p.nome, m.papel
            FROM preparos p JOIN preparo_membros m ON m.preparo_id = p.id
            WHERE p.id = ? AND m.usuario_id = ? AND m.situacao = 'aprovado'
            """,
            (preparo_id, usuario["id"]),
        ).fetchone()
    # Mesmo erro para "não existe" e "não participa": não revela quais preparos existem.
    if row is None:
        raise HTTPException(status_code=403, detail="Você não participa deste preparo.")
    return {"id": row["id"], "nome": row["nome"], "papel": row["papel"], "usuario": usuario}
