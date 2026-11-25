"""Motor estatístico progressivo para estimativa de litros na panela e ponto exato de colheita."""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

from .domain import (
    TIPOS_PANELA,
    add_minutes,
    agua_derivada,
    calcular_no_fogo_ha,
    diff_minutes,
    estado_panela,
    normalizar_tipo,
    try_parse_decimal_ptbr,
)

# Priors físicos por categoria:
# alpha = litros esperados por kg de mariri + chacrona na panela (L / kg de delta_peso = cheia − seca);
# é só o ponto de partida: o modelo reestima esse fator com os preparos já colhidos
# r_prior = taxa de evaporação média inicial (L / min)
PRIORS_POR_TIPO: dict[str, tuple[float, float]] = {
    "1ª vez": (0.72, 2.4 / 60.0),
    "2ª vez": (0.80, 2.5 / 60.0),
    "3ª vez": (0.85, 2.6 / 60.0),
    "APURO": (0.98, 3.0 / 60.0),
}
DEFAULT_PRIOR = (0.80, 2.5 / 60.0)

MIN_RATE_L_PER_MIN = 0.005  # 0,3 L/h
MAX_RATE_L_PER_MIN = 0.500  # 30,0 L/h
MIN_ALPHA = 0.15
MAX_ALPHA = 1.15
MIN_AMOSTRAS_AGUA = 6  # amostras com água informada para o modelo passar a usá-la
MIN_BETA_AGUA, MAX_BETA_AGUA = -0.5, 2.0  # litros de líquido por litro de água; o ponto de partida é 0 (sem efeito)

# Fator de fornalha do bloco: razão entre o tempo real e o previsto para cada panela já colhida.
FATOR_PRIOR_PANELAS = 2.0  # peso do prior "fogo normal" (fator 1); com poucas colhidas o fator fica perto de 1
FATOR_POR_PANELA_LIMITE = (0.5, 2.0)
FATOR_FORNALHA_LIMITE = (0.6, 1.6)


@dataclass(frozen=True)
class HistoricalSample:
    tipo: str
    t_ferv: float
    litros: float
    peso_seca: float | None
    peso_cheia: float | None
    agua: float | None = None  # litros de água = peso c − peso b (ver agua_derivada)

    @property
    def has_weights(self) -> bool:
        return (
            self.peso_seca is not None
            and self.peso_cheia is not None
            and self.peso_cheia > self.peso_seca
        )

    @property
    def delta_peso(self) -> float:
        assert self.peso_cheia is not None and self.peso_seca is not None
        return self.peso_cheia - self.peso_seca


def load_historical_samples(conn: sqlite3.Connection, preparo_id: str) -> list[HistoricalSample]:
    """Carrega todas as panelas colhidas válidas do SQLite para calibração estatística."""
    rows = conn.execute(
        """
        SELECT p.tipo, p.fervura, p.colhida, p.litros, p.peso_seca_kg, p.peso_cheia_kg, p.peso_com_agua_kg
        FROM panelas p
        JOIN blocos b ON p.bloco_id = b.id
        JOIN registros r ON b.registro_id = r.id
        WHERE r.excluido = 0
          AND r.preparo_id = ?
          AND p.fervura != ''
          AND p.colhida != ''
          AND p.litros IS NOT NULL
          AND p.litros > 0
        """,
        (preparo_id,),
    ).fetchall()

    samples: list[HistoricalSample] = []
    for row in rows:
        t_ferv = diff_minutes(row["fervura"], row["colhida"])
        if t_ferv is None or t_ferv < 1 or t_ferv > 960:
            continue
        tipo = normalizar_tipo(row["tipo"])
        litros = float(row["litros"])
        peso_seca = float(row["peso_seca_kg"]) if row["peso_seca_kg"] is not None else None
        peso_cheia = float(row["peso_cheia_kg"]) if row["peso_cheia_kg"] is not None else None
        agua = agua_derivada(peso_cheia, row["peso_com_agua_kg"])
        samples.append(
            HistoricalSample(
                tipo=tipo,
                t_ferv=float(t_ferv),
                litros=litros,
                peso_seca=peso_seca,
                peso_cheia=peso_cheia,
                agua=agua,
            )
        )
    return samples


@dataclass
class CalibratedModel:
    nivel: str  # "inicial" | "aprendendo" | "calibrado"
    amostras_usadas: int
    escopo: str
    beta0: float
    beta_delta_p: float
    beta_p_seca: float
    rate_l_per_min: float
    gamma_por_tipo: dict[str, float]
    mae_litros: float | None
    rmse_litros: float | None
    mae_minutos: float | None
    r2: float | None
    uses_weights: bool = True
    # Água: só entra depois de haver amostras suficientes com água informada (ver MIN_AMOSTRAS_AGUA).
    uses_agua: bool = False
    beta_agua: float = 0.0
    agua_ref: float = 0.0  # média da água nas amostras do ajuste; a coluna é centrada nela

    def initial_volume(
        self, tipo: str, delta_peso: float, peso_seca: float, agua: float | None = None
    ) -> float:
        gamma = self.gamma_por_tipo.get(tipo, 0.0)
        v0 = self.beta0 + self.beta_delta_p * delta_peso + self.beta_p_seca * peso_seca + gamma
        if self.uses_agua and agua is not None:
            v0 += self.beta_agua * (agua - self.agua_ref)
        return max(1.0, v0)

    def predict_liters_at(
        self, tipo: str, delta_peso: float, peso_seca: float, t_ferv_min: float, agua: float | None = None
    ) -> float:
        v0 = self.initial_volume(tipo, delta_peso, peso_seca, agua)
        return max(0.0, v0 - self.rate_l_per_min * max(0.0, t_ferv_min))

    def predict_target_minutes(
        self, tipo: str, delta_peso: float, peso_seca: float, meta_litros: float, agua: float | None = None
    ) -> float:
        v0 = self.initial_volume(tipo, delta_peso, peso_seca, agua)
        if v0 <= meta_litros:
            return 0.0
        return (v0 - meta_litros) / max(self.rate_l_per_min, MIN_RATE_L_PER_MIN)


def _fit_constrained_ridge(
    samples: list[HistoricalSample],
    target_tipo: str,
    include_type_dummies: bool,
    include_agua: bool = False,
) -> CalibratedModel:
    """Ajusta regressão multivariada Ridge com restrições físicas e IRLS Huber.

    Com `include_agua`, todas as amostras precisam ter água informada; a coluna é centrada na média.
    """
    n = len(samples)
    alpha_prior, r_prior = PRIORS_POR_TIPO.get(target_tipo, DEFAULT_PRIOR)

    y = np.array([s.litros for s in samples], dtype=np.float64)
    delta_p = np.array([s.delta_peso for s in samples], dtype=np.float64)
    p_seca = np.array([s.peso_seca or 0.0 for s in samples], dtype=np.float64)
    t_ferv = np.array([s.t_ferv for s in samples], dtype=np.float64)

    # Colunas: [intercepto, delta_p, p_seca, -t_ferv, (água − média)?, dummy_1a, dummy_2a, dummy_3a, dummy_apuro]
    active_tipos = list(TIPOS_PANELA) if include_type_dummies else []
    k_dummies = len(active_tipos)
    off = 5 if include_agua else 4  # primeira coluna das dummies
    ncol = off + k_dummies

    agua_ref = 0.0
    X = np.zeros((n, ncol), dtype=np.float64)
    X[:, 0] = 1.0
    X[:, 1] = delta_p
    X[:, 2] = p_seca
    X[:, 3] = -t_ferv
    if include_agua:
        agua_vals = np.array([s.agua for s in samples], dtype=np.float64)
        agua_ref = float(np.mean(agua_vals))
        X[:, 4] = agua_vals - agua_ref
    for d_idx, t_name in enumerate(active_tipos):
        X[:, off + d_idx] = [1.0 if s.tipo == t_name else 0.0 for s in samples]

    theta = np.zeros(ncol, dtype=np.float64)
    theta[1] = alpha_prior
    theta[3] = r_prior

    priors = np.zeros(ncol, dtype=np.float64)
    priors[1] = alpha_prior
    priors[3] = r_prior

    # Ridge suave centrado nos priors físicos (garante estabilidade se P_seca for constante)
    lambdas = np.zeros(ncol, dtype=np.float64)
    lambdas[0] = 0.05
    lambdas[1] = 0.50
    lambdas[2] = 5.00
    lambdas[3] = 5.00
    if include_agua:
        lambdas[4] = 1.00  # prior 0: sem dados que mostrem efeito, a água não mexe na previsão
    for d_idx in range(k_dummies):
        lambdas[off + d_idx] = 1.00

    lower = np.full(ncol, -np.inf, dtype=np.float64)
    upper = np.full(ncol, np.inf, dtype=np.float64)
    lower[0], upper[0] = -15.0, 25.0
    lower[1], upper[1] = MIN_ALPHA, MAX_ALPHA
    lower[2], upper[2] = -0.35, 0.35
    lower[3], upper[3] = MIN_RATE_L_PER_MIN, MAX_RATE_L_PER_MIN
    if include_agua:
        lower[4], upper[4] = MIN_BETA_AGUA, MAX_BETA_AGUA
    for d_idx in range(k_dummies):
        lower[off + d_idx], upper[off + d_idx] = -10.0, 10.0

    weights = np.ones(n, dtype=np.float64)
    irls_rounds = 6 if n >= 8 else 1

    for irls_step in range(irls_rounds):
        for _ in range(250):
            y_pred = X @ theta
            for j in range(len(theta)):
                col = X[:, j]
                # Resíduo parcial removendo apenas a contribuição da coluna j
                res_no_j = (y - y_pred) + theta[j] * col
                denom = float(np.sum(weights * col * col) + lambdas[j])
                if denom <= 1e-12:
                    continue
                numer = float(np.sum(weights * col * res_no_j) + lambdas[j] * priors[j])
                new_val = float(np.clip(numer / denom, lower[j], upper[j]))
                y_pred = y_pred + (new_val - theta[j]) * col
                theta[j] = new_val

        if irls_step < irls_rounds - 1:
            residuals = y - (X @ theta)
            med = float(np.median(residuals))
            mad = float(np.median(np.abs(residuals - med)))
            scale = max(1.4826 * mad, 0.45)
            delta = 1.5 * scale
            abs_res = np.abs(residuals)
            weights = np.where(abs_res <= delta, 1.0, delta / np.maximum(abs_res, 1e-9))

    gamma_por_tipo: dict[str, float] = {}
    for d_idx, t_name in enumerate(active_tipos):
        gamma_por_tipo[t_name] = float(theta[off + d_idx])

    y_hat = X @ theta
    residuals = y - y_hat

    # Métricas usando pesos finais do Huber para evitar que um único erro de digitação distorça a calibração reportada,
    # mas preservando fidelidade quando não há outliers.
    w_norm = weights / np.sum(weights)
    mae_litros = float(np.sum(w_norm * np.abs(residuals)))
    rmse_litros = float(np.sqrt(np.sum(w_norm * (residuals**2))))

    ss_res = float(np.sum(weights * (residuals**2)))
    y_mean_w = float(np.sum(w_norm * y))
    ss_tot = float(np.sum(weights * ((y - y_mean_w) ** 2)))
    r2 = float(max(0.0, min(1.0, 1.0 - ss_res / ss_tot))) if ss_tot > 1e-6 else None

    v0_samples = y_hat + theta[3] * t_ferv
    t_hat = np.maximum(0.0, (v0_samples - y) / max(theta[3], MIN_RATE_L_PER_MIN))
    mae_minutos = float(np.sum(w_norm * np.abs(t_ferv - t_hat)))

    return CalibratedModel(
        nivel="calibrado",
        amostras_usadas=n,
        escopo=target_tipo if (not include_type_dummies and target_tipo) else "geral",
        beta0=float(theta[0]),
        beta_delta_p=float(theta[1]),
        beta_p_seca=float(theta[2]),
        rate_l_per_min=float(theta[3]),
        gamma_por_tipo=gamma_por_tipo,
        mae_litros=round(mae_litros, 2),
        rmse_litros=round(rmse_litros, 2),
        mae_minutos=round(mae_minutos, 1),
        r2=round(r2, 3) if r2 is not None else None,
        uses_weights=True,
        uses_agua=include_agua,
        beta_agua=float(theta[4]) if include_agua else 0.0,
        agua_ref=agua_ref,
    )


def _fit_bayesian_tier2(
    samples: list[HistoricalSample],
    target_tipo: str,
) -> CalibratedModel:
    """Calibração bayesiana empírica para 2 <= n < 6 amostras com pesos."""
    alpha_prior, r_prior = PRIORS_POR_TIPO.get(target_tipo, DEFAULT_PRIOR)
    k_shrink = 2.0

    r_obs: list[float] = []
    for s in samples:
        a_s, _ = PRIORS_POR_TIPO.get(s.tipo, DEFAULT_PRIOR)
        r_i = (a_s * s.delta_peso - s.litros) / s.t_ferv
        if MIN_RATE_L_PER_MIN <= r_i <= MAX_RATE_L_PER_MIN:
            r_obs.append(r_i)

    if r_obs:
        r_med = float(np.median(r_obs))
        r_hat = (k_shrink * r_prior + len(r_obs) * r_med) / (k_shrink + len(r_obs))
    else:
        r_hat = r_prior

    r_hat = float(np.clip(r_hat, MIN_RATE_L_PER_MIN, MAX_RATE_L_PER_MIN))

    alpha_obs: list[float] = []
    for s in samples:
        v0_implied = s.litros + r_hat * s.t_ferv
        a_i = v0_implied / s.delta_peso
        if 0.35 <= a_i <= 1.15:
            alpha_obs.append(a_i)

    if alpha_obs:
        a_med = float(np.median(alpha_obs))
        alpha_hat = (k_shrink * alpha_prior + len(alpha_obs) * a_med) / (k_shrink + len(alpha_obs))
    else:
        alpha_hat = alpha_prior

    alpha_hat = float(np.clip(alpha_hat, MIN_ALPHA, MAX_ALPHA))

    # Calcular erro nos dados observados
    preds = [max(0.0, alpha_hat * s.delta_peso - r_hat * s.t_ferv) for s in samples]
    res = [abs(s.litros - p) for s, p in zip(samples, preds)]
    t_errs = [
        abs(s.t_ferv - max(0.0, (alpha_hat * s.delta_peso - s.litros) / r_hat))
        for s in samples
    ]

    return CalibratedModel(
        nivel="aprendendo",
        amostras_usadas=len(samples),
        escopo=target_tipo or "geral",
        beta0=0.0,
        beta_delta_p=alpha_hat,
        beta_p_seca=0.0,
        rate_l_per_min=r_hat,
        gamma_por_tipo={},
        mae_litros=round(float(np.mean(res)), 2),
        rmse_litros=round(float(np.sqrt(np.mean(np.square(res)))), 2),
        mae_minutos=round(float(np.mean(t_errs)), 1),
        r2=None,
        uses_weights=True,
    )


def fit_model_for_type(
    samples: list[HistoricalSample],
    target_tipo: str,
) -> CalibratedModel:
    """Seleciona automaticamente a melhor camada estatística conforme dados no SQLite."""
    tipo = normalizar_tipo(target_tipo)
    alpha_prior, r_prior = PRIORS_POR_TIPO.get(tipo, DEFAULT_PRIOR)

    with_weights = [s for s in samples if s.has_weights]
    same_type_weights = [s for s in with_weights if s.tipo == tipo] if tipo else []

    # Água: só com amostras que a informaram (nunca tratar "sem informação" como "zero litros").
    same_type_agua = [s for s in same_type_weights if s.agua is not None]
    with_agua = [s for s in with_weights if s.agua is not None]

    if len(same_type_agua) >= MIN_AMOSTRAS_AGUA:
        return _fit_constrained_ridge(same_type_agua, tipo, include_type_dummies=False, include_agua=True)
    if len(same_type_weights) >= 6:
        return _fit_constrained_ridge(same_type_weights, tipo, include_type_dummies=False)
    if len(with_agua) >= MIN_AMOSTRAS_AGUA:
        return _fit_constrained_ridge(with_agua, tipo, include_type_dummies=True, include_agua=True)
    if len(with_weights) >= 6:
        return _fit_constrained_ridge(with_weights, tipo, include_type_dummies=True)
    if len(same_type_weights) >= 2:
        return _fit_bayesian_tier2(same_type_weights, tipo)
    if len(with_weights) >= 2:
        return _fit_bayesian_tier2(with_weights, tipo)

    return CalibratedModel(
        nivel="inicial",
        amostras_usadas=len(with_weights),
        escopo=tipo or "geral",
        beta0=0.0,
        beta_delta_p=alpha_prior,
        beta_p_seca=0.0,
        rate_l_per_min=r_prior,
        gamma_por_tipo={},
        mae_litros=None,
        rmse_litros=None,
        mae_minutos=None,
        r2=None,
        uses_weights=True,
    )


def _compute_fervura_elapsed_min(
    entrada: str,
    fervura: str,
    data_preparo: str,
    now_dt: datetime,
) -> float | None:
    """Calcula minutos em fervura com suporte a virada de meia-noite."""
    if not fervura:
        return None

    if entrada:
        no_fogo_total = calcular_no_fogo_ha(entrada, data_preparo, now_dt)
        ent_to_ferv = diff_minutes(entrada, fervura)
        if no_fogo_total is not None and ent_to_ferv is not None:
            elapsed = no_fogo_total - ent_to_ferv
            if elapsed >= 0:
                return float(elapsed)

    ferv_elapsed = calcular_no_fogo_ha(fervura, data_preparo, now_dt)
    return float(ferv_elapsed) if ferv_elapsed is not None else None


def fator_fornalha(panelas_bloco: list[dict[str, Any]], samples: list[HistoricalSample]) -> float:
    """Quanto o fogo deste bloco está mais rápido (<1) ou mais lento (>1) que o modelo.

    Compara o tempo real de cada panela já colhida com o tempo que o modelo previa para
    tirar os mesmos litros. A média é geométrica e encolhida para 1 quando há poucas panelas.
    """
    logs: list[float] = []
    modelos: dict[str, CalibratedModel] = {}
    for pan in panelas_bloco:
        if estado_panela(pan) != "colhida":
            continue
        tipo = normalizar_tipo(pan.get("tipo"))
        peso_seca = try_parse_decimal_ptbr(pan.get("pesoSecaKg"))
        peso_cheia = try_parse_decimal_ptbr(pan.get("pesoCheiaKg"))
        litros = try_parse_decimal_ptbr(pan.get("litros"))
        if peso_seca is None or peso_cheia is None or peso_cheia <= peso_seca or not litros:
            continue
        t_real = diff_minutes(pan.get("fervura"), pan.get("colhida"))
        if t_real is None or t_real < 1:
            continue
        if tipo not in modelos:
            modelos[tipo] = fit_model_for_type(samples, tipo)
        agua = agua_derivada(peso_cheia, try_parse_decimal_ptbr(pan.get("pesoComAguaKg")))
        t_previsto = modelos[tipo].predict_target_minutes(
            tipo, peso_cheia - peso_seca, peso_seca, litros, agua
        )
        if t_previsto <= 0:
            continue
        razao = min(max(t_real / t_previsto, FATOR_POR_PANELA_LIMITE[0]), FATOR_POR_PANELA_LIMITE[1])
        logs.append(math.log(razao))
    if not logs:
        return 1.0
    fator = math.exp(sum(logs) / (len(logs) + FATOR_PRIOR_PANELAS))
    return min(max(fator, FATOR_FORNALHA_LIMITE[0]), FATOR_FORNALHA_LIMITE[1])


def predict_panela(
    panela: dict[str, Any],
    data_preparo: str,
    samples: list[HistoricalSample],
    *,
    meta_litros_padrao: float = 10.15,
    now_dt: datetime | None = None,
    fator_fornalha: float = 1.0,
) -> dict[str, Any]:
    """Gera a predição completa em tempo real para uma panela.

    fator_fornalha < 1 significa fogo mais rápido que o modelo: o tempo até o alvo encurta
    na mesma proporção. Tempo real vira tempo do modelo dividindo pelo fator.
    """
    now = now_dt or datetime.now()
    estado = estado_panela(panela)
    tipo = normalizar_tipo(panela.get("tipo"))
    entrada = str(panela.get("entrada") or "").strip()
    fervura = str(panela.get("fervura") or "").strip()
    peso_seca = try_parse_decimal_ptbr(panela.get("pesoSecaKg"))
    peso_cheia = try_parse_decimal_ptbr(panela.get("pesoCheiaKg"))
    agua = agua_derivada(peso_cheia, try_parse_decimal_ptbr(panela.get("pesoComAguaKg")))
    meta_litros = try_parse_decimal_ptbr(panela.get("metaLitros")) or meta_litros_padrao

    if estado in {"vazia", "colhida"}:
        return {
            "disponivel": False,
            "motivo": "Panela já colhida" if estado == "colhida" else "Panela vazia",
            "metaLitros": round(meta_litros, 2),
        }

    has_weights = (
        peso_seca is not None and peso_cheia is not None and peso_cheia > peso_seca
    )

    if has_weights:
        assert peso_seca is not None and peso_cheia is not None
        delta_p = peso_cheia - peso_seca
        model = fit_model_for_type(samples, tipo)

        v0 = model.initial_volume(tipo, delta_p, peso_seca, agua)
        t_alvo = model.predict_target_minutes(tipo, delta_p, peso_seca, meta_litros, agua) * fator_fornalha
        t_ferv_atual = _compute_fervura_elapsed_min(entrada, fervura, data_preparo, now)

        t_for_eval = t_ferv_atual if t_ferv_atual is not None else 0.0
        litros_atuais = model.predict_liters_at(
            tipo, delta_p, peso_seca, t_for_eval / fator_fornalha, agua
        )
        minutos_restantes = round(t_alvo - t_for_eval) if t_ferv_atual is not None else round(t_alvo)
        horario_previsto = add_minutes(fervura, t_alvo) if fervura else None

        margem_litros = (
            max(0.5, round(1.25 * model.mae_litros, 2))
            if model.mae_litros is not None
            else round(max(1.2, 0.12 * v0), 2)
        )
        margem_minutos = (
            max(5, round(1.25 * model.mae_minutos))
            if model.mae_minutos is not None
            else max(12, round(0.15 * max(t_alvo, 60)))
        )

        denom = max(v0 - meta_litros, 0.5)
        progresso = 0.0
        if t_ferv_atual is not None:
            progresso = max(0.0, min(100.0, ((v0 - litros_atuais) / denom) * 100.0))

        # Projeção em marcos de 30 min de fervura: litros previstos antes de a panela chegar ao ponto
        ate_min = max(t_alvo * 1.15, 60.0)
        projecao = [
            {
                "minutos": m,
                "litros": round(model.predict_liters_at(tipo, delta_p, peso_seca, m / fator_fornalha, agua), 2),
            }
            for m in range(30, int(math.ceil(ate_min / 30.0)) * 30 + 1, 30)
        ]

        # Curva de redução de 7 pontos para gráfico compacto
        horizon = max(t_alvo * 1.15, (t_for_eval + 30.0) if t_ferv_atual else t_alvo, 60.0)
        curva = [
            {
                "min": round(horizon * i / 6.0),
                "litros": round(
                    model.predict_liters_at(tipo, delta_p, peso_seca, horizon * i / 6.0 / fator_fornalha, agua), 2
                ),
            }
            for i in range(7)
        ]

        return {
            "disponivel": True,
            "usaPesos": True,
            "usaAgua": bool(model.uses_agua and agua is not None),
            "aguardandoFervura": not bool(fervura),
            "passouDoPonto": (t_ferv_atual is not None and minutos_restantes <= 0),
            "metaLitros": round(meta_litros, 2),
            "pesoLiquidoInicialKg": round(delta_p, 2),
            "litrosIniciaisEstimados": round(v0, 2),
            "litrosAtuaisEstimados": round(litros_atuais, 2),
            "taxaEvaporacaoLh": round(model.rate_l_per_min * 60.0 / fator_fornalha, 2),
            "fatorFornalha": round(fator_fornalha, 2),
            "tempoFervuraAtualMin": round(t_ferv_atual) if t_ferv_atual is not None else None,
            "tempoFervuraAlvoMin": round(t_alvo),
            "minutosRestantes": minutos_restantes,
            "horarioRetiradaPrevisto": horario_previsto,
            "margemErroLitros": margem_litros,
            "margemErroMinutos": margem_minutos,
            "progressoPercentual": round(progresso, 1),
            "modeloNivel": model.nivel,
            "amostrasUsadas": model.amostras_usadas,
            "maeLitros": model.mae_litros,
            "maeMinutos": model.mae_minutos,
            "r2": model.r2,
            "curva": curva,
            "projecao": projecao,
            "aviso": (
                "Já passou do ponto estimado"
                if (t_ferv_atual is not None and minutos_restantes <= 0)
                else (
                    "Falta marcar o início da fervura"
                    if not fervura
                    else None
                )
            ),
        }

    # Camada 1: sem pesos nesta panela, mas há histórico por tempo (n >= 2)
    same_type_time = [s for s in samples if s.tipo == tipo] if tipo else []
    time_pool = same_type_time if len(same_type_time) >= 2 else samples
    if len(time_pool) >= 2 and fervura:
        med_t = float(np.median([s.t_ferv for s in time_pool]))
        med_l = float(np.median([s.litros for s in time_pool]))
        t_ferv_atual = _compute_fervura_elapsed_min(entrada, fervura, data_preparo, now)
        # Ajuste leve caso meta seja diferente da mediana histórica
        taxa_media = PRIORS_POR_TIPO.get(tipo, DEFAULT_PRIOR)[1]
        t_alvo = max(15.0, med_t + (med_l - meta_litros) / max(taxa_media, 0.02))
        minutos_restantes = round(t_alvo - t_ferv_atual) if t_ferv_atual is not None else round(t_alvo)
        horario_previsto = add_minutes(fervura, t_alvo)
        progresso = (
            max(0.0, min(100.0, (t_ferv_atual / max(t_alvo, 1.0)) * 100.0))
            if t_ferv_atual is not None
            else 0.0
        )
        return {
            "disponivel": True,
            "usaPesos": False,
            "aguardandoFervura": False,
            "passouDoPonto": (t_ferv_atual is not None and minutos_restantes <= 0),
            "metaLitros": round(meta_litros, 2),
            "pesoLiquidoInicialKg": None,
            "litrosIniciaisEstimados": None,
            "litrosAtuaisEstimados": round(med_l + max(0.0, t_alvo - (t_ferv_atual or 0.0)) * taxa_media, 2),
            "taxaEvaporacaoLh": round(taxa_media * 60.0, 2),
            "tempoFervuraAtualMin": round(t_ferv_atual) if t_ferv_atual is not None else None,
            "tempoFervuraAlvoMin": round(t_alvo),
            "minutosRestantes": minutos_restantes,
            "horarioRetiradaPrevisto": horario_previsto,
            "margemErroLitros": 2.5,
            "margemErroMinutos": 25,
            "progressoPercentual": round(progresso, 1),
            "modeloNivel": "aprendendo",
            "amostrasUsadas": len(time_pool),
            "maeLitros": None,
            "maeMinutos": None,
            "r2": None,
            "curva": [],
            "aviso": "Estimativa apenas por tempo histórico. Informe peso seca e cheia para alta precisão.",
        }

    return {
        "disponivel": False,
        "usaPesos": False,
        "metaLitros": round(meta_litros, 2),
        "motivo": "Informe peso seca, peso cheia e início da fervura para estimar o ponto de colheita.",
    }


def summarize_stats(conn: sqlite3.Connection, preparo_id: str) -> dict[str, Any]:
    """Resumo global do banco histórico e acurácia do modelo por tipo."""
    samples = load_historical_samples(conn, preparo_id)
    with_weights = [s for s in samples if s.has_weights]
    geral_model = fit_model_for_type(samples, "")

    por_tipo: dict[str, Any] = {}
    for tipo in TIPOS_PANELA:
        s_tipo = [s for s in samples if s.tipo == tipo]
        s_tipo_w = [s for s in with_weights if s.tipo == tipo]
        m = fit_model_for_type(samples, tipo)
        por_tipo[tipo] = {
            "totalColhidas": len(s_tipo),
            "comPesos": len(s_tipo_w),
            "taxaEvaporacaoLh": round(m.rate_l_per_min * 60.0, 2),
            "fatorLiquidoInicial": round(m.beta_delta_p, 3),
            "fatorAgua": round(m.beta_agua, 3) if m.uses_agua else None,
            "modeloNivel": m.nivel,
            "maeLitros": m.mae_litros,
            "maeMinutos": m.mae_minutos,
            "r2": m.r2,
        }

    return {
        "totalPanelasColhidas": len(samples),
        "totalComPesos": len(with_weights),
        "totalComAgua": len([s for s in with_weights if s.agua is not None]),
        "modeloGeralNivel": geral_model.nivel,
        "maeLitrosGeral": geral_model.mae_litros,
        "maeMinutosGeral": geral_model.mae_minutos,
        "r2Geral": geral_model.r2,
        "porTipo": por_tipo,
    }


def list_distinct_dry_weights(conn: sqlite3.Connection, preparo_id: str) -> list[dict[str, Any]]:
    """Lista pesos de panela seca mais usados para sugestão rápida no campo."""
    rows = conn.execute(
        """
        SELECT ROUND(p.peso_seca_kg, 2) AS peso, COUNT(*) AS usos
        FROM panelas p
        JOIN blocos b ON p.bloco_id = b.id
        JOIN registros r ON b.registro_id = r.id
        WHERE r.excluido = 0 AND r.preparo_id = ?
          AND p.peso_seca_kg IS NOT NULL AND p.peso_seca_kg > 0
        GROUP BY ROUND(p.peso_seca_kg, 2)
        ORDER BY usos DESC, peso ASC
        LIMIT 12
        """,
        (preparo_id,),
    ).fetchall()
    return [{"pesoKg": float(r["peso"]), "usos": int(r["usos"])} for r in rows]
