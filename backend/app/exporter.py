"""Exportação CSV (Excel pt-BR) e importação JSON compatível com v1/v2."""

from __future__ import annotations

import csv
import io
import sqlite3
import uuid
from typing import Any

from .database import now_iso, registro_exists, save_registro
from .domain import normalizar_tipo, try_parse_decimal_ptbr

CSV_HEADERS = [
    "Data",
    "Núcleo",
    "Mestre",
    "Auxiliar",
    "Resp. Mariri",
    "Resp. Chacrona 1",
    "Resp. Chacrona 2",
    "Mariri",
    "Mariri (Kg)",
    "Chacrona (Kg)",
    "Bloco",
    "Panela",
    "Tipo",
    "Entrada",
    "Fervura",
    "Colhida",
    "Peso Seca (Kg)",
    "Peso Cheia (Kg)",
    "Litros",
    "Obs. Bloco",
    "Obs. Geral",
]


def _fmt_num_ptbr(value: Any) -> str:
    num = try_parse_decimal_ptbr(value)
    if num is None:
        return ""
    if float(num).is_integer():
        return str(int(num))
    return f"{num:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def registros_to_csv(registros: list[dict[str, Any]]) -> str:
    """Gera CSV com BOM UTF-8 e separador ';' para abrir direto no Excel."""
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_HEADERS)

    for reg in registros:
        chacrona_total = sum(
            (try_parse_decimal_ptbr(c.get("kg")) or 0.0)
            for c in (reg.get("chacrona") or [])
        )
        chacrona_str = _fmt_num_ptbr(chacrona_total) if chacrona_total > 0 else ""
        mariri_kg_str = _fmt_num_ptbr(reg.get("maririKg"))

        blocos = reg.get("blocos") or []
        wrote_row = False
        for b_idx, bloco in enumerate(blocos, start=1):
            panelas = bloco.get("panelas") or []
            for p_idx, pan in enumerate(panelas):
                numero = pan.get("numero") or ((b_idx - 1) * 5 + p_idx + 1)
                writer.writerow(
                    [
                        reg.get("data", ""),
                        reg.get("nucleo", ""),
                        reg.get("mestre", ""),
                        reg.get("auxiliar", ""),
                        reg.get("respMariri", ""),
                        reg.get("respChacrona", ""),
                        reg.get("respChacrona2", ""),
                        reg.get("mariri", ""),
                        mariri_kg_str,
                        chacrona_str,
                        b_idx,
                        numero,
                        normalizar_tipo(pan.get("tipo")),
                        pan.get("entrada", ""),
                        pan.get("fervura", ""),
                        pan.get("colhida", ""),
                        _fmt_num_ptbr(pan.get("pesoSecaKg")),
                        _fmt_num_ptbr(pan.get("pesoCheiaKg")),
                        _fmt_num_ptbr(pan.get("litros")),
                        bloco.get("obs", ""),
                        reg.get("obsGeral", ""),
                    ]
                )
                wrote_row = True

        if not wrote_row:
            writer.writerow(
                [
                    reg.get("data", ""),
                    reg.get("nucleo", ""),
                    reg.get("mestre", ""),
                    reg.get("auxiliar", ""),
                    reg.get("respMariri", ""),
                    reg.get("respChacrona", ""),
                    reg.get("respChacrona2", ""),
                    reg.get("mariri", ""),
                    mariri_kg_str,
                    chacrona_str,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    reg.get("obsGeral", ""),
                ]
            )

    return buf.getvalue()


def _extract_registros_list(raw_payload: Any) -> list[dict[str, Any]]:
    if isinstance(raw_payload, list):
        return [item for item in raw_payload if isinstance(item, dict)]
    if isinstance(raw_payload, dict):
        if isinstance(raw_payload.get("registros"), list):
            return [item for item in raw_payload["registros"] if isinstance(item, dict)]
        if "blocos" in raw_payload:
            return [raw_payload]
    raise ValueError(
        "Formato JSON inválido. Envie uma lista de registros, um registro com 'blocos' ou um objeto com a chave 'registros'."
    )


def import_registros_json(
    conn: sqlite3.Connection, raw_payload: Any, preparo_id: str
) -> dict[str, int]:
    """Importa JSON nos 3 formatos aceitos sem duplicar IDs e normalizando tipos da v1."""
    items = _extract_registros_list(raw_payload)
    importados = 0
    ja_existentes = 0
    invalidos = 0

    for item in items:
        blocos = item.get("blocos")
        if not isinstance(blocos, list):
            invalidos += 1
            continue

        reg_id = str(item.get("id") or "").strip()
        if not reg_id:
            reg_id = f"imp-{uuid.uuid4().hex[:12]}"

        if registro_exists(conn, reg_id):
            ja_existentes += 1
            continue

        normalized_blocos = []
        for b_idx, bloco in enumerate(blocos):
            if not isinstance(bloco, dict):
                continue
            panelas_norm = []
            for p_idx, pan in enumerate(bloco.get("panelas") or []):
                if not isinstance(pan, dict):
                    continue
                panelas_norm.append(
                    {
                        "numero": pan.get("numero") or (b_idx * 5 + p_idx + 1),
                        "tipo": normalizar_tipo(pan.get("tipo")),
                        "entrada": str(pan.get("entrada") or "").strip(),
                        "fervura": str(pan.get("fervura") or "").strip(),
                        "colhida": str(pan.get("colhida") or "").strip(),
                        "litros": try_parse_decimal_ptbr(pan.get("litros")),
                        "pesoSecaKg": try_parse_decimal_ptbr(
                            pan.get("pesoSecaKg") if "pesoSecaKg" in pan else pan.get("peso_seca_kg")
                        ),
                        "pesoCheiaKg": try_parse_decimal_ptbr(
                            pan.get("pesoCheiaKg") if "pesoCheiaKg" in pan else pan.get("peso_cheia_kg")
                        ),
                        "metaLitros": try_parse_decimal_ptbr(
                            pan.get("metaLitros") if "metaLitros" in pan else pan.get("meta_litros")
                        ),
                        "pesoComAguaKg": try_parse_decimal_ptbr(
                            pan.get("pesoComAguaKg") if "pesoComAguaKg" in pan else pan.get("peso_com_agua_kg")
                        ),
                    }
                )
            normalized_blocos.append(
                {
                    "obs": str(bloco.get("obs") or ""),
                    "anotador": str(bloco.get("anotador") or "").strip(),
                    "data": str(bloco.get("data") or "").strip(),
                    "panelas": panelas_norm,
                }
            )

        chacrona_norm = []
        raw_chacrona = item.get("chacrona")
        if isinstance(raw_chacrona, list):
            for ch in raw_chacrona:
                if isinstance(ch, dict):
                    chacrona_norm.append(
                        {
                            "nucleo": str(ch.get("nucleo") or ""),
                            "kg": try_parse_decimal_ptbr(ch.get("kg")),
                        }
                    )

        clean_item = {
            "id": reg_id,
            "salvoEm": str(item.get("salvoEm") or now_iso()),
            "nucleo": str(item.get("nucleo") or "Bendito Filho"),
            "data": str(item.get("data") or ""),
            "mestre": str(item.get("mestre") or ""),
            "auxiliar": str(item.get("auxiliar") or ""),
            "respMariri": str(item.get("respMariri") or ""),
            "respChacrona": str(item.get("respChacrona") or ""),
            "respChacrona2": str(item.get("respChacrona2") or ""),
            "mariri": str(item.get("mariri") or ""),
            "maririKg": try_parse_decimal_ptbr(item.get("maririKg")),
            "chacrona": chacrona_norm,
            "obsGeral": str(item.get("obsGeral") or ""),
            "blocos": normalized_blocos,
        }
        save_registro(conn, clean_item, preparo_id)
        importados += 1

    return {
        "importados": importados,
        "jaExistentes": ja_existentes,
        "invalidos": invalidos,
    }
