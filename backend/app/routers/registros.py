"""Rotas de CRUD, importação e exportação de registros no SQLite."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from ..database import (
    RegistroDeOutroPreparo,
    db_session,
    delete_registro,
    get_registro,
    list_registros,
    now_iso,
    save_registro,
)
from ..domain import calcular_totais_por_tipo, try_parse_decimal_ptbr
from ..exporter import import_registros_json, registros_to_csv
from ..preparos import preparo_atual, preparo_editavel
from ..schemas import ImportRequest, ImportSummary, RegistroPayload

router = APIRouter(prefix="/api/registros", tags=["registros"])


def _enrich_registro(reg: dict[str, Any]) -> dict[str, Any]:
    totais = calcular_totais_por_tipo(reg.get("blocos") or [])
    chacrona_kg = sum(
        (try_parse_decimal_ptbr(c.get("kg")) or 0.0)
        for c in (reg.get("chacrona") or [])
    )
    return {
        **reg,
        "chacronaTotalKg": round(chacrona_kg, 2),
        "totalLitros": totais["totalGeral"],
        "totaisPorTipo": totais["porTipo"],
    }


@router.get("")
def get_all_registros(preparo: dict[str, Any] = Depends(preparo_atual)) -> list[dict[str, Any]]:
    with db_session() as conn:
        regs = list_registros(conn, preparo["id"])
        return [_enrich_registro(r) for r in regs]


@router.get("/export/csv")
def export_csv(preparo: dict[str, Any] = Depends(preparo_atual)) -> Response:
    with db_session() as conn:
        regs = list_registros(conn, preparo["id"])
        csv_text = registros_to_csv(regs)
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="preparo-vegetal-registros.csv"'
        },
    )


@router.get("/export/json")
def export_json(preparo: dict[str, Any] = Depends(preparo_atual)) -> list[dict[str, Any]]:
    with db_session() as conn:
        return list_registros(conn, preparo["id"])


@router.post("/import", response_model=ImportSummary)
def import_json(body: ImportRequest, preparo: dict[str, Any] = Depends(preparo_editavel)) -> ImportSummary:
    with db_session() as conn:
        try:
            res = import_registros_json(conn, body.payload, preparo_id=preparo["id"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportSummary(**res)


@router.get("/{reg_id}")
def get_one_registro(reg_id: str, preparo: dict[str, Any] = Depends(preparo_atual)) -> dict[str, Any]:
    with db_session() as conn:
        reg = get_registro(conn, reg_id, preparo["id"])
        if not reg:
            raise HTTPException(status_code=404, detail="Registro não encontrado.")
        return _enrich_registro(reg)


@router.post("", status_code=201)
def create_or_save_registro(
    payload: RegistroPayload, preparo: dict[str, Any] = Depends(preparo_editavel)
) -> dict[str, Any]:
    if not payload.data.strip():
        raise HTTPException(
            status_code=400,
            detail="Informe a data do preparo no Cabeçalho antes de salvar.",
        )
    data = payload.model_dump()
    if not data.get("id"):
        data["id"] = f"reg-{uuid.uuid4().hex[:12]}"
    data["salvoEm"] = now_iso()

    with db_session() as conn:
        try:
            saved = save_registro(conn, data, preparo["id"], preparo["usuario"])
        except RegistroDeOutroPreparo as exc:
            raise HTTPException(status_code=404, detail="Registro não encontrado.") from exc
        return _enrich_registro(saved)


@router.put("/{reg_id}")
def update_registro(
    reg_id: str, payload: RegistroPayload, preparo: dict[str, Any] = Depends(preparo_editavel)
) -> dict[str, Any]:
    if not payload.data.strip():
        raise HTTPException(
            status_code=400,
            detail="Informe a data do preparo no Cabeçalho antes de salvar.",
        )
    data = payload.model_dump()
    data["id"] = reg_id
    data["salvoEm"] = now_iso()

    with db_session() as conn:
        try:
            saved = save_registro(conn, data, preparo["id"], preparo["usuario"])
        except RegistroDeOutroPreparo as exc:
            raise HTTPException(status_code=404, detail="Registro não encontrado.") from exc
        return _enrich_registro(saved)


@router.delete("/{reg_id}")
def remove_registro(reg_id: str, preparo: dict[str, Any] = Depends(preparo_editavel)) -> dict[str, Any]:
    with db_session() as conn:
        ok = delete_registro(conn, reg_id, preparo["id"])
        if not ok:
            raise HTTPException(status_code=404, detail="Registro não encontrado.")
    return {"ok": True, "id": reg_id}
