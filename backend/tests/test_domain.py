"""Testes das regras de domínio, estados, validações e virada de meia-noite."""

from datetime import datetime

import pytest

from app.domain import (
    TIPOS_PANELA,
    add_minutes,
    calcular_metricas_bloco,
    calcular_no_fogo_ha,
    calcular_totais_por_tipo,
    diff_minutes,
    estado_panela,
    normalizar_tipo,
    parse_decimal_ptbr,
    validar_panela,
)


def test_normalizar_tipo_quatro_categorias() -> None:
    assert TIPOS_PANELA == ("1ª vez", "2ª vez", "3ª vez", "APURO")
    assert normalizar_tipo("1") == "1ª vez"
    assert normalizar_tipo("1a") == "1ª vez"
    assert normalizar_tipo("1ª") == "1ª vez"
    assert normalizar_tipo("1 vez") == "1ª vez"
    assert normalizar_tipo("2") == "2ª vez"
    assert normalizar_tipo("2ª") == "2ª vez"
    assert normalizar_tipo("3") == "3ª vez"
    assert normalizar_tipo("3a vez") == "3ª vez"
    assert normalizar_tipo("apuro") == "APURO"
    assert normalizar_tipo("APURO") == "APURO"
    assert normalizar_tipo("Apuração") == "APURO"
    assert normalizar_tipo("") == ""
    assert normalizar_tipo("Água") == ""


def test_parse_decimal_ptbr() -> None:
    assert parse_decimal_ptbr("10,15") == pytest.approx(10.15)
    assert parse_decimal_ptbr("10.15") == pytest.approx(10.15)
    assert parse_decimal_ptbr("1.234,50") == pytest.approx(1234.50)
    assert parse_decimal_ptbr("") is None
    assert parse_decimal_ptbr(None) is None
    with pytest.raises(ValueError):
        parse_decimal_ptbr("abc")


def test_estados_panela() -> None:
    assert estado_panela({}) == "vazia"
    assert estado_panela({"tipo": "1ª vez"}) == "sem_entrada"
    assert estado_panela({"entrada": "08:00"}) == "no_fogo"
    assert estado_panela({"entrada": "08:00", "fervura": "08:30"}) == "fervendo"
    assert (
        estado_panela({"entrada": "08:00", "fervura": "08:30", "colhida": "12:00"})
        == "colhida"
    )
    assert estado_panela({"colhida": "12:00"}) == "colhida"


def test_virada_meia_noite_panela_e_bloco() -> None:
    assert diff_minutes("22:30", "01:45") == 195
    assert add_minutes("23:10", 110) == "01:00"

    bloco = {
        "panelas": [
            {"tipo": "1ª vez", "entrada": "21:00", "fervura": "21:30", "colhida": "01:00", "litros": 12.0},
            {"tipo": "2ª vez", "entrada": "22:00", "fervura": "22:30", "colhida": "02:30", "litros": 10.5},
        ]
    }
    met = calcular_metricas_bloco(bloco)
    assert met["totalLitros"] == pytest.approx(22.5)
    assert met["duracaoMin"] == 330  # 21:00 até 02:30 = 5h30
    assert met["tempoMedioMin"] == pytest.approx(255.0)  # (240 + 270) / 2
    assert met["litrosPorHora"] == pytest.approx(22.5 / 5.5, abs=0.02)
    assert met["minPorLitro"] == pytest.approx(330 / 22.5, abs=0.02)


def test_l_por_h_so_com_litros_e_duracao_positiva() -> None:
    bloco_sem_litros = {
        "panelas": [{"tipo": "1ª vez", "entrada": "08:00", "fervura": "08:30", "colhida": "12:00"}]
    }
    met = calcular_metricas_bloco(bloco_sem_litros)
    assert met["litrosPorHora"] is None
    assert met["minPorLitro"] is None


def test_validacao_vermelho_e_amarelo() -> None:
    now = datetime(2026, 11, 22, 14, 0)
    hoje = "2026-11-22"

    # Sem tipo, sem entrada, sem fervura, sem colhida
    res_err = validar_panela({"litros": 10.0}, hoje, now)
    assert len(res_err["faltando"]) >= 4

    # Colhida sem litros
    res_col_sem_l = validar_panela(
        {"tipo": "1ª vez", "entrada": "08:00", "fervura": "08:30", "colhida": "12:00"},
        hoje,
        now,
    )
    assert any("Litros" in msg for msg in res_col_sem_l["faltando"])

    # Sem fervura após 30 min (entrada 13:20, agora 14:00 = 40 min)
    res_ferv = validar_panela({"tipo": "1ª vez", "entrada": "13:20"}, hoje, now, min_sem_fervura=30)
    assert any("fervura" in msg.lower() for msg in res_ferv["conferir"])

    # Sem colheita após 5h (entrada 08:30, agora 14:00 = 5h30)
    res_col = validar_panela(
        {"tipo": "2ª vez", "entrada": "08:30", "fervura": "09:00"},
        hoje,
        now,
        horas_sem_colheita=5.0,
    )
    assert any("colheita" in msg.lower() for msg in res_col["conferir"])

    # No fogo há com limite de 16h e continuação pós-meia-noite
    assert calcular_no_fogo_ha("23:00", "2026-11-21", datetime(2026, 11, 22, 1, 30)) == 150
    assert calcular_no_fogo_ha("01:00", "2026-11-22", datetime(2026, 11, 22, 20, 0)) is None


def test_totais_por_tipo() -> None:
    blocos = [
        {
            "panelas": [
                {"tipo": "1", "litros": "10,5"},
                {"tipo": "2ª", "litros": 11.25},
                {"tipo": "apuro", "litros": "8,25"},
            ]
        }
    ]
    tot = calcular_totais_por_tipo(blocos)
    assert tot["totalGeral"] == pytest.approx(30.0)
    assert tot["porTipo"]["1ª vez"] == pytest.approx(10.5)
    assert tot["porTipo"]["2ª vez"] == pytest.approx(11.25)
    assert tot["porTipo"]["3ª vez"] == pytest.approx(0.0)
    assert tot["porTipo"]["APURO"] == pytest.approx(8.25)


def test_peso_com_agua_deve_ser_maior_que_o_peso_com_mariri_e_chacrona() -> None:
    base = {"tipo": "1ª", "entrada": "06:00", "pesoSecaKg": 12, "pesoCheiaKg": 36}
    agora = datetime(2026, 11, 22, 7, 0)
    ok = validar_panela({**base, "pesoComAguaKg": 56}, "2026-11-22", agora)
    ruim = validar_panela({**base, "pesoComAguaKg": 30}, "2026-11-22", agora)
    assert not any("água" in m for m in ok["faltando"])
    assert any("com água" in m for m in ruim["faltando"])
