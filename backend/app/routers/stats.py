"""Rotas do motor estatístico de predição de fervura e calibração histórica."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends

from ..database import db_session, get_config_map
from ..domain import calcular_metricas_bloco, calcular_totais_por_tipo, estado_panela, validar_panela
from ..preparos import preparo_atual
from ..schemas import PredictRequest
from ..stats import (
    list_distinct_dry_weights,
    load_historical_samples,
    predict_panela,
    summarize_stats,
)

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.post("/predict")
def predict_blocos(body: PredictRequest, preparo: dict[str, Any] = Depends(preparo_atual)) -> dict[str, Any]:
    now_dt = datetime.fromisoformat(body.agora) if body.agora else datetime.now()
    with db_session() as conn:
        samples = load_historical_samples(conn, preparo["id"])
        cfg = get_config_map(conn, preparo["id"])
        summary = summarize_stats(conn, preparo["id"])

    meta_padrao = body.metaLitrosPadrao or cfg["metaLitrosPadrao"]
    min_sem_fervura = cfg["minSemFervura"]
    horas_sem_colheita = cfg["horasSemColheita"]

    blocos_dict = [b.model_dump() for b in body.blocos]
    blocos_out: list[dict[str, Any]] = []

    no_fogo_count = 0
    colhidas_count = 0
    pendencias_count = 0

    for b_idx, bloco in enumerate(blocos_dict):
        panelas_out: list[dict[str, Any]] = []
        for p_idx, pan in enumerate(bloco.get("panelas") or []):
            numero = pan.get("numero") or (b_idx * 5 + p_idx + 1)
            pan_with_num = {**pan, "numero": numero}
            est = estado_panela(pan_with_num)
            alertas = validar_panela(
                pan_with_num,
                body.data,
                now_dt,
                min_sem_fervura=min_sem_fervura,
                horas_sem_colheita=horas_sem_colheita,
            )
            pred = predict_panela(
                pan_with_num,
                body.data,
                samples,
                meta_litros_padrao=meta_padrao,
                now_dt=now_dt,
            )

            if est in {"no_fogo", "fervendo"}:
                no_fogo_count += 1
            elif est == "colhida":
                colhidas_count += 1
            if alertas["faltando"] or alertas["conferir"]:
                pendencias_count += 1

            panelas_out.append(
                {
                    "numero": numero,
                    "estado": est,
                    "alertas": alertas,
                    "predicao": pred,
                }
            )

        blocos_out.append(
            {
                "blocoIndex": b_idx,
                "metricas": calcular_metricas_bloco(bloco),
                "panelas": panelas_out,
            }
        )

    return {
        "resumo": {
            "noFogo": no_fogo_count,
            "colhidas": colhidas_count,
            "comPendencias": pendencias_count,
        },
        "totais": calcular_totais_por_tipo(blocos_dict),
        "modelo": summary,
        "blocos": blocos_out,
    }


@router.get("/summary")
def read_stats_summary(preparo: dict[str, Any] = Depends(preparo_atual)) -> dict[str, Any]:
    with db_session() as conn:
        return summarize_stats(conn, preparo["id"])


@router.get("/pesos-panelas")
def read_pesos_panelas(preparo: dict[str, Any] = Depends(preparo_atual)) -> list[dict[str, Any]]:
    with db_session() as conn:
        return list_distinct_dry_weights(conn, preparo["id"])
