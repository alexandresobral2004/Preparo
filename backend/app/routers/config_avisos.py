"""Rotas de configurações de avisos e meta padrão de colheita."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..database import db_session, get_config_map, update_config_map
from ..preparos import preparo_atual, preparo_editavel
from ..schemas import ConfigUpdate

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
def read_config(preparo: dict[str, Any] = Depends(preparo_atual)) -> dict[str, Any]:
    with db_session() as conn:
        return get_config_map(conn, preparo["id"])


@router.put("")
def write_config(body: ConfigUpdate, preparo: dict[str, Any] = Depends(preparo_editavel)) -> dict[str, Any]:
    with db_session() as conn:
        return update_config_map(conn, preparo["id"], body.model_dump(exclude_none=True))
