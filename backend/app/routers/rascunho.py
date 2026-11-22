"""Rotas do rascunho do preparo em andamento (um por preparo, compartilhado entre os membros)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..database import ConflitoRascunho, clear_rascunho, db_session, get_rascunho, save_rascunho
from ..preparos import preparo_atual

router = APIRouter(prefix="/api/rascunho", tags=["rascunho"])


@router.get("")
def read_rascunho(preparo: dict[str, Any] = Depends(preparo_atual)) -> dict[str, Any] | None:
    with db_session() as conn:
        return get_rascunho(conn, preparo["id"])


@router.put("", response_model=None)
def upsert_rascunho(payload: dict[str, Any], preparo: dict[str, Any] = Depends(preparo_atual)):
    """Grava o rascunho. Se outra pessoa o alterou depois da última leitura, responde 409 com a versão atual."""
    with db_session() as conn:
        try:
            return save_rascunho(conn, preparo["id"], payload, preparo["usuario"])
        except ConflitoRascunho as exc:
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "Outra pessoa alterou o preparo. A tela foi atualizada com a versão mais recente.",
                    "atual": exc.atual or None,
                },
            )


@router.delete("")
def delete_rascunho(preparo: dict[str, Any] = Depends(preparo_atual)) -> dict[str, bool]:
    with db_session() as conn:
        clear_rascunho(conn, preparo["id"])
    return {"ok": True}
