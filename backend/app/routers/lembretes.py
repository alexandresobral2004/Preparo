"""Rotas de lembretes do preparo."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..database import db_session, now_iso
from ..preparos import preparo_atual
from ..schemas import LembreteCreate, LembretePatch

router = APIRouter(prefix="/api/lembretes", tags=["lembretes"])


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "texto": row["texto"],
        "horario": row["horario"],
        "feito": bool(row["feito"]),
        "criadoEm": row["created_at"],
    }


@router.get("")
def list_lembretes(preparo: dict[str, Any] = Depends(preparo_atual)) -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM lembretes WHERE preparo_id = ? ORDER BY feito ASC, horario ASC, created_at DESC",
            (preparo["id"],),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


@router.post("", status_code=201)
def create_lembrete(body: LembreteCreate, preparo: dict[str, Any] = Depends(preparo_atual)) -> dict[str, Any]:
    lid = f"lem-{uuid.uuid4().hex[:10]}"
    ts = now_iso()
    with db_session() as conn:
        conn.execute(
            "INSERT INTO lembretes (id, texto, horario, feito, created_at, preparo_id) VALUES (?, ?, ?, 0, ?, ?)",
            (lid, body.texto, body.horario.strip(), ts, preparo["id"]),
        )
        row = conn.execute("SELECT * FROM lembretes WHERE id = ?", (lid,)).fetchone()
        return _row_to_dict(row)


@router.patch("/{lembrete_id}")
def patch_lembrete(
    lembrete_id: str, body: LembretePatch, preparo: dict[str, Any] = Depends(preparo_atual)
) -> dict[str, Any]:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM lembretes WHERE id = ? AND preparo_id = ?", (lembrete_id, preparo["id"])
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Lembrete não encontrado.")

        feito = int(body.feito) if body.feito is not None else row["feito"]
        texto = body.texto.strip() if body.texto is not None else row["texto"]
        horario = body.horario.strip() if body.horario is not None else row["horario"]

        conn.execute(
            "UPDATE lembretes SET feito = ?, texto = ?, horario = ? WHERE id = ?",
            (feito, texto, horario, lembrete_id),
        )
        updated = conn.execute("SELECT * FROM lembretes WHERE id = ?", (lembrete_id,)).fetchone()
        return _row_to_dict(updated)


@router.delete("/{lembrete_id}")
def delete_lembrete(lembrete_id: str, preparo: dict[str, Any] = Depends(preparo_atual)) -> dict[str, Any]:
    with db_session() as conn:
        cur = conn.execute(
            "DELETE FROM lembretes WHERE id = ? AND preparo_id = ?", (lembrete_id, preparo["id"])
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Lembrete não encontrado.")
    return {"ok": True, "id": lembrete_id}
