"""Testes do motor estatístico progressivo de fervura e predição de colheita."""

from datetime import datetime

import pytest

from app.domain import add_minutes
from app.stats import HistoricalSample, fit_model_for_type, predict_panela


def test_cold_start_com_pesos_e_meta_10_15() -> None:
    panela = {
        "tipo": "2ª vez",
        "entrada": "22:30",
        "fervura": "23:10",
        "pesoSecaKg": 12.0,
        "pesoCheiaKg": 32.0,  # delta = 20 kg -> prior 0.80 => V0 = 16.0 L
    }
    now = datetime(2026, 11, 22, 0, 10)  # 60 min de fervura desde 23:10
    pred = predict_panela(
        panela,
        "2026-11-21",
        samples=[],
        meta_litros_padrao=10.15,
        now_dt=now,
    )
    assert pred["disponivel"] is True
    assert pred["usaPesos"] is True
    assert pred["modeloNivel"] == "inicial"
    assert pred["litrosIniciaisEstimados"] == pytest.approx(16.0, abs=0.1)
    assert pred["tempoFervuraAtualMin"] == 60
    assert pred["litrosAtuaisEstimados"] < pred["litrosIniciaisEstimados"]
    assert pred["horarioRetiradaPrevisto"] is not None


def test_tier2_calibra_com_tres_amostras() -> None:
    # Processo real tem taxa ~0.06 L/min (3.6 L/h), maior que prior 2.5 L/h
    samples = [
        HistoricalSample("2ª vez", t_ferv=100, litros=18.0, peso_seca=12.0, peso_cheia=42.0),  # 24 - 6 = 18
        HistoricalSample("2ª vez", t_ferv=150, litros=15.0, peso_seca=12.0, peso_cheia=42.0),  # 24 - 9 = 15
        HistoricalSample("2ª vez", t_ferv=120, litros=13.0, peso_seca=10.0, peso_cheia=35.0),  # 20 - 7.2 = 12.8
    ]
    model = fit_model_for_type(samples, "2ª vez")
    assert model.nivel == "aprendendo"
    assert model.amostras_usadas == 3
    # Taxa deve ter subido acima do prior (2.5/60 = 0.0417)
    assert model.rate_l_per_min > 0.045


def test_tier3_multivariado_converge_com_ruido_e_outlier() -> None:
    # Gerar 15 amostras realistas: V = 0.84 * delta_p - 0.055 * t_ferv (+ leve efeito P_seca)
    samples: list[HistoricalSample] = []
    for i in range(14):
        p_seca = 10.0 + (i % 4) * 1.5
        delta_p = 24.0 + (i % 5) * 4.0
        t_ferv = 90.0 + (i % 6) * 25.0
        noise = ((i % 3) - 1) * 0.22
        litros = round(0.84 * delta_p + 0.04 * p_seca - 0.055 * t_ferv + noise, 2)
        samples.append(
            HistoricalSample(
                tipo="2ª vez",
                t_ferv=t_ferv,
                litros=litros,
                peso_seca=p_seca,
                peso_cheia=p_seca + delta_p,
            )
        )
    # 1 outlier grosseiro (erro de digitação)
    samples.append(
        HistoricalSample("2ª vez", t_ferv=120.0, litros=39.0, peso_seca=12.0, peso_cheia=40.0)
    )

    model = fit_model_for_type(samples, "2ª vez")
    assert model.nivel == "calibrado"
    assert model.amostras_usadas == 15
    assert model.mae_litros is not None and model.mae_litros < 1.2
    assert 0.045 <= model.rate_l_per_min <= 0.068

    # Monotonicidade física: mais fervura -> menos litros
    l_60 = model.predict_liters_at("2ª vez", delta_peso=28.0, peso_seca=12.0, t_ferv_min=60)
    l_120 = model.predict_liters_at("2ª vez", delta_peso=28.0, peso_seca=12.0, t_ferv_min=120)
    assert l_120 < l_60

    # Mais carga líquida -> mais tempo até 10,15 L
    t_menor = model.predict_target_minutes("2ª vez", delta_peso=22.0, peso_seca=12.0, meta_litros=10.15)
    t_maior = model.predict_target_minutes("2ª vez", delta_peso=34.0, peso_seca=12.0, meta_litros=10.15)
    assert t_maior > t_menor

    # Previsão no alvo deve reproduzir 10,15 L
    l_at_target = model.predict_liters_at("2ª vez", delta_peso=28.0, peso_seca=12.0, t_ferv_min=t_maior if False else model.predict_target_minutes("2ª vez", 28.0, 12.0, 10.15))
    assert l_at_target == pytest.approx(10.15, abs=0.05)


def test_horario_previsto_cruza_meia_noite() -> None:
    assert add_minutes("23:10", 110) == "01:00"
    panela = {
        "tipo": "APURO",
        "entrada": "22:30",
        "fervura": "23:10",
        "pesoSecaKg": 10.0,
        "pesoCheiaKg": 26.0,
    }
    pred = predict_panela(
        panela,
        "2026-11-22",
        samples=[],
        meta_litros_padrao=10.15,
        now_dt=datetime(2026, 11, 22, 23, 30),
    )
    assert pred["disponivel"] is True
    expected_hhmm = add_minutes("23:10", pred["tempoFervuraAlvoMin"])
    assert pred["horarioRetiradaPrevisto"] == expected_hhmm
    # 16 kg * 0.98 = 15.68 L -> reduzir 5.53 L a 0.05 L/min = ~111 min -> 01:01 (passa da 00:00)
    assert pred["horarioRetiradaPrevisto"].startswith("01:")


def _amostras(n: int, com_agua: bool) -> list[HistoricalSample]:
    """V0 = 0,8·ΔP + 0,9·água; cada litro de água a mais vira ~0,9 L de líquido no início."""
    out: list[HistoricalSample] = []
    for i in range(n):
        p_seca = 10.0 + (i % 4) * 1.5
        delta_p = 24.0 + (i % 5) * 4.0
        t_ferv = 90.0 + (i % 6) * 25.0
        agua = 15.0 + (i % 4) * 5.0
        litros = round(0.8 * delta_p + 0.9 * agua - 0.055 * t_ferv, 2)
        out.append(
            HistoricalSample(
                tipo="2ª vez", t_ferv=t_ferv, litros=litros, peso_seca=p_seca,
                peso_cheia=p_seca + delta_p, agua=agua if com_agua else None,
            )
        )
    return out


def test_agua_entra_no_calculo_quando_ha_amostras_suficientes() -> None:
    model = fit_model_for_type(_amostras(12, com_agua=True), "2ª vez")
    assert model.nivel == "calibrado" and model.uses_agua
    assert 0.6 < model.beta_agua < 1.1
    mais = model.initial_volume("2ª vez", 30.0, 12.0, agua=30.0)
    menos = model.initial_volume("2ª vez", 30.0, 12.0, agua=20.0)
    assert mais - menos == pytest.approx(10 * model.beta_agua, abs=1e-6)
    assert mais - menos > 6.0


def test_sem_amostras_com_agua_o_campo_nao_altera_a_previsao() -> None:
    model = fit_model_for_type(_amostras(12, com_agua=False), "2ª vez")
    assert not model.uses_agua
    assert model.initial_volume("2ª vez", 30.0, 12.0, agua=40.0) == model.initial_volume("2ª vez", 30.0, 12.0)


def test_poucas_amostras_com_agua_nao_ativam_o_efeito() -> None:
    mistas = _amostras(5, com_agua=True) + _amostras(10, com_agua=False)
    model = fit_model_for_type(mistas, "2ª vez")
    assert not model.uses_agua  # exige 6 amostras com água; o resto não pode ser tratado como "água = 0"


def test_predicao_usa_a_agua_informada_na_panela() -> None:
    samples = _amostras(12, com_agua=True)
    base = {"tipo": "2ª vez", "entrada": "06:00", "fervura": "06:30", "pesoSecaKg": 12.0, "pesoCheiaKg": 42.0}
    agora = datetime(2026, 11, 22, 8, 0)
    # c) panela + mariri + chacrona + água; a água é c − b (1 kg ≈ 1 L)
    pouca = predict_panela({**base, "pesoComAguaKg": 42.0 + 15}, "2026-11-22", samples, now_dt=agora)
    muita = predict_panela({**base, "pesoComAguaKg": 42.0 + 30}, "2026-11-22", samples, now_dt=agora)
    assert pouca["usaAgua"] and muita["usaAgua"]
    assert muita["litrosIniciaisEstimados"] - pouca["litrosIniciaisEstimados"] > 8.0
    assert muita["tempoFervuraAlvoMin"] > pouca["tempoFervuraAlvoMin"]  # mais líquido, mais tempo até a meta
    sem = predict_panela(base, "2026-11-22", samples, now_dt=agora)
    assert sem["usaAgua"] is False  # sem informar a água, usa o modelo sem esse termo


def test_agua_das_amostras_vem_da_diferenca_entre_os_pesos(tmp_path) -> None:
    from app.database import _upsert_registro_conn, db_session, init_db
    from app.stats import load_historical_samples

    db = tmp_path / "amostras.db"
    init_db(db)
    pan = {"tipo": "1ª", "entrada": "06:00", "fervura": "06:30", "colhida": "10:00", "litros": 12,
           "pesoSecaKg": 12, "pesoCheiaKg": 30}
    com_agua = {**pan, "numero": 1, "pesoComAguaKg": 50}   # água = 50 − 30 = 20 kg ≈ 20 L
    sem_agua = {**pan, "numero": 2}                         # não informado: nunca vira 0
    invalida = {**pan, "numero": 3, "pesoComAguaKg": 28}    # menor que b: ignorada
    with db_session(db) as conn:
        _upsert_registro_conn(
            conn,
            {"id": "r1", "data": "2026-11-22", "blocos": [{"panelas": [com_agua, sem_agua, invalida]}]},
            preparo_id="p1",
        )
        aguas = sorted((s.agua is None, s.agua) for s in load_historical_samples(conn, "p1"))
    assert aguas == [(False, 20.0), (True, None), (True, None)]
