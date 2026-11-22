"""Regras de domínio, normalização de tipos da v1, validações e cálculos do Preparo."""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any

TIPOS_PANELA: tuple[str, ...] = ("1ª vez", "2ª vez", "3ª vez", "APURO")

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def normalizar_tipo(raw: Any) -> str:
    """Unifica variações de tipo da v1/v2 para as 4 categorias fixas."""
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""

    norm = _strip_accents(text).lower()
    norm = norm.replace("º", "a").replace("ª", "a").replace("°", "a")
    norm = re.sub(r"\s+", " ", norm).strip()

    if norm in {"1", "1a", "1a vez", "1 vez", "1vez", "primeira", "primeira vez"}:
        return "1ª vez"
    if norm in {"2", "2a", "2a vez", "2 vez", "2vez", "segunda", "segunda vez"}:
        return "2ª vez"
    if norm in {"3", "3a", "3a vez", "3 vez", "3vez", "terceira", "terceira vez"}:
        return "3ª vez"
    if "apuro" in norm or "apurac" in norm:
        return "APURO"

    # Fallback numérico caso venha "1ª Vez (algo)"
    if norm.startswith("1"):
        return "1ª vez"
    if norm.startswith("2"):
        return "2ª vez"
    if norm.startswith("3"):
        return "3ª vez"

    return ""


def parse_decimal_ptbr(val: Any) -> float | None:
    """Converte número pt-BR (vírgula ou ponto) para float. Rejeita texto inválido."""
    if val is None:
        return None
    if isinstance(val, bool):
        raise ValueError("Valor booleano não é número.")
    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            raise ValueError("Número inválido.")
        return float(val)

    s = str(val).strip()
    if not s:
        return None

    # Se contiver pontos de milhar e vírgula decimal (ex.: 1.234,56)
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")

    if not re.fullmatch(r"[+-]?(\d+(\.\d+)?|\.\d+)", s):
        raise ValueError(f"Valor numérico inválido: {val}")
    num = float(s)
    if math.isnan(num) or math.isinf(num):
        raise ValueError("Número inválido.")
    return num


def try_parse_decimal_ptbr(val: Any) -> float | None:
    try:
        return parse_decimal_ptbr(val)
    except ValueError:
        return None


def parse_hhmm(hhmm: Any) -> int | None:
    """Converte 'HH:MM' em minutos desde 00:00."""
    if not hhmm:
        return None
    s = str(hhmm).strip()
    m = _TIME_RE.match(s)
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def format_hhmm(minutes: int) -> str:
    m = int(round(minutes)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def diff_minutes(start_hhmm: Any, end_hhmm: Any) -> int | None:
    """Diferença em minutos entre dois horários, somando 24h na virada de meia-noite."""
    start = parse_hhmm(start_hhmm)
    end = parse_hhmm(end_hhmm)
    if start is None or end is None:
        return None
    delta = end - start
    if delta < 0:
        delta += 1440
    return delta


def add_minutes(hhmm: Any, delta_min: float) -> str | None:
    start = parse_hhmm(hhmm)
    if start is None:
        return None
    return format_hhmm(start + round(delta_min))


def _has_value(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        return bool(val.strip())
    return True


def estado_panela(panela: dict[str, Any]) -> str:
    """Retorna 'vazia' | 'sem_entrada' | 'no_fogo' | 'fervendo' | 'colhida'."""
    tipo = normalizar_tipo(panela.get("tipo"))
    entrada = str(panela.get("entrada") or "").strip()
    fervura = str(panela.get("fervura") or "").strip()
    colhida = str(panela.get("colhida") or "").strip()
    litros = try_parse_decimal_ptbr(panela.get("litros"))
    peso_seca = try_parse_decimal_ptbr(panela.get("pesoSecaKg"))
    peso_cheia = try_parse_decimal_ptbr(panela.get("pesoCheiaKg"))

    has_any = any(
        [
            bool(tipo),
            bool(entrada),
            bool(fervura),
            bool(colhida),
            litros is not None,
            peso_seca is not None,
            peso_cheia is not None,
        ]
    )
    if not has_any:
        return "vazia"
    if colhida:
        return "colhida"
    if entrada and fervura:
        return "fervendo"
    if entrada:
        return "no_fogo"
    return "sem_entrada"


def agua_derivada(peso_cheia: float | None, peso_com_agua: float | None) -> float | None:
    """Água (L) = peso c (panela + mariri + chacrona + água) − peso b (sem água); 1 kg ≈ 1 L.

    Sem os dois pesos, ou com c <= b, não há água confiável: devolve None (nunca 0).
    """
    if peso_cheia is None or peso_com_agua is None or peso_com_agua <= peso_cheia:
        return None
    return peso_com_agua - peso_cheia


def calcular_no_fogo_ha(
    entrada: Any,
    data_preparo: str,
    now_dt: datetime | None = None,
) -> int | None:
    """Calcula minutos no fogo se data == hoje (ou continuação pós-meia-noite de ontem), máx 16h."""
    ent_min = parse_hhmm(entrada)
    if ent_min is None or not data_preparo:
        return None

    now = now_dt or datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")
    now_min = now.hour * 60 + now.minute

    if data_preparo == today_str:
        delta = now_min - ent_min
        if 0 <= delta <= 16 * 60:
            return delta
        return None

    # Suporte à virada de meia-noite para preparo iniciado ontem à noite
    if data_preparo == yesterday_str and now_min < ent_min:
        delta = (now_min + 1440) - ent_min
        if 0 <= delta <= 16 * 60:
            return delta

    return None


def validar_panela(
    panela: dict[str, Any],
    data_preparo: str,
    now_dt: datetime | None = None,
    min_sem_fervura: int = 30,
    horas_sem_colheita: float = 5.0,
) -> dict[str, list[str]]:
    """Retorna alertas 'faltando' (vermelho) e 'conferir' (amarelo) da panela."""
    estado = estado_panela(panela)
    if estado == "vazia":
        return {"faltando": [], "conferir": []}

    tipo = normalizar_tipo(panela.get("tipo"))
    entrada = str(panela.get("entrada") or "").strip()
    fervura = str(panela.get("fervura") or "").strip()
    colhida = str(panela.get("colhida") or "").strip()
    litros = try_parse_decimal_ptbr(panela.get("litros"))
    peso_seca = try_parse_decimal_ptbr(panela.get("pesoSecaKg"))
    peso_cheia = try_parse_decimal_ptbr(panela.get("pesoCheiaKg"))

    faltando: list[str] = []
    conferir: list[str] = []

    if not tipo:
        faltando.append("Panela sem tipo informado")
    if (fervura or colhida or litros is not None) and not entrada:
        faltando.append("Horário de entrada faltando")
    if (colhida or litros is not None) and not fervura:
        faltando.append("Horário de fervura faltando")
    if litros is not None and not colhida:
        faltando.append("Horário de colheita faltando")
    if colhida and litros is None:
        faltando.append("Litros colhidos não informados")
    if peso_seca is not None and peso_cheia is not None and peso_cheia <= peso_seca:
        faltando.append("Peso da panela com mariri e chacrona deve ser maior que o da panela vazia")
    peso_com_agua = try_parse_decimal_ptbr(panela.get("pesoComAguaKg"))
    if peso_com_agua is not None and peso_cheia is not None and peso_com_agua <= peso_cheia:
        faltando.append("Peso da panela com água deve ser maior que o da panela com mariri e chacrona")

    if entrada and not colhida:
        no_fogo_min = calcular_no_fogo_ha(entrada, data_preparo, now_dt)
        if no_fogo_min is not None:
            if not fervura and no_fogo_min >= min_sem_fervura:
                conferir.append(f"Sem fervura após {min_sem_fervura} min da entrada")
            if no_fogo_min >= round(horas_sem_colheita * 60):
                horas_txt = (
                    str(int(horas_sem_colheita))
                    if float(horas_sem_colheita).is_integer()
                    else str(horas_sem_colheita).replace(".", ",")
                )
                conferir.append(f"Sem colheita após {horas_txt} h da entrada")

    return {"faltando": faltando, "conferir": conferir}


def calcular_metricas_bloco(bloco: dict[str, Any]) -> dict[str, Any]:
    """Calcula litros totais, tempo médio, duração do bloco (com virada de meia-noite), L/h e min/L."""
    panelas = bloco.get("panelas") or []
    total_litros = 0.0
    tempos_panela: list[int] = []

    entradas_validas = [
        m for p in panelas if (m := parse_hhmm(p.get("entrada"))) is not None
    ]

    anchor: int | None = None
    cross_midnight_entries = False
    if entradas_validas:
        if max(entradas_validas) - min(entradas_validas) > 720:
            cross_midnight_entries = True
            evening = [m for m in entradas_validas if m >= 720]
            anchor = min(evening) if evening else min(entradas_validas)
        else:
            anchor = min(entradas_validas)

    colhidas_rel: list[int] = []

    for p in panelas:
        litros = try_parse_decimal_ptbr(p.get("litros"))
        if litros is not None and litros > 0:
            total_litros += litros

        ent = parse_hhmm(p.get("entrada"))
        col = parse_hhmm(p.get("colhida"))
        if ent is not None and col is not None:
            dur = diff_minutes(p.get("entrada"), p.get("colhida"))
            if dur is not None:
                tempos_panela.append(dur)

        if anchor is not None and col is not None:
            if ent is not None:
                ent_rel = (ent - anchor) if ent >= anchor else (ent - anchor + 1440)
                pan_dur = diff_minutes(p.get("entrada"), p.get("colhida")) or 0
                colhidas_rel.append(ent_rel + pan_dur)
            else:
                col_rel = (col - anchor) if col >= anchor else (col - anchor + 1440)
                if cross_midnight_entries and col < 720 and anchor >= 720:
                    col_rel = col - anchor + 1440
                colhidas_rel.append(col_rel)

    duracao_min: int | None = max(colhidas_rel) if colhidas_rel else None
    tempo_medio_min: float | None = (
        sum(tempos_panela) / len(tempos_panela) if tempos_panela else None
    )

    litros_por_hora: float | None = None
    min_por_litro: float | None = None
    if total_litros > 0 and duracao_min is not None and duracao_min > 0:
        horas = duracao_min / 60.0
        litros_por_hora = total_litros / horas
        min_por_litro = duracao_min / total_litros

    return {
        "totalLitros": round(total_litros, 2),
        "tempoMedioMin": round(tempo_medio_min, 1) if tempo_medio_min is not None else None,
        "duracaoMin": duracao_min,
        "litrosPorHora": round(litros_por_hora, 2) if litros_por_hora is not None else None,
        "minPorLitro": round(min_por_litro, 2) if min_por_litro is not None else None,
    }


def calcular_totais_por_tipo(blocos: list[dict[str, Any]]) -> dict[str, Any]:
    por_tipo: dict[str, float] = {t: 0.0 for t in TIPOS_PANELA}
    total_geral = 0.0

    for bloco in blocos:
        for p in bloco.get("panelas") or []:
            litros = try_parse_decimal_ptbr(p.get("litros"))
            if litros is None or litros <= 0:
                continue
            total_geral += litros
            tipo = normalizar_tipo(p.get("tipo"))
            if tipo in por_tipo:
                por_tipo[tipo] += litros

    return {
        "totalGeral": round(total_geral, 2),
        "porTipo": {k: round(v, 2) for k, v in por_tipo.items()},
    }
