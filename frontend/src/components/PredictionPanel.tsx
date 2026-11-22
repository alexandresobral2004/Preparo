import React from "react";
import type { PanelaPrediction } from "../types";
import { formatDurationMin, formatPtBr } from "../domain/format";

interface PredictionPanelProps {
  predicao: PanelaPrediction;
  compact?: boolean;
}

const NIVEL_LABEL: Record<string, string> = {
  inicial: "Calibração inicial",
  aprendendo: "Aprendendo",
  calibrado: "Modelo calibrado",
};

export const PredictionPanel: React.FC<PredictionPanelProps> = ({
  predicao,
  compact = false,
}) => {
  if (!predicao.disponivel) {
    if (compact || !predicao.motivo) return null;
    return <div className="muted">{predicao.motivo}</div>;
  }

  const overdue = Boolean(predicao.passouDoPonto);
  const metaTxt = formatPtBr(predicao.metaLitros, 2);
  const atuaisTxt = formatPtBr(predicao.litrosAtuaisEstimados, 1);

  if (compact) {
    if (predicao.aguardandoFervura) {
      return (
        <div className="prediction-strip tabular">
          <div className="prediction-highlight">
            <span>
              Início estimado: <strong>~{formatPtBr(predicao.litrosIniciaisEstimados, 1)} L</strong>
            </span>
            <span className="muted">
              Fervura p/ {metaTxt} L: ~{formatDurationMin(predicao.tempoFervuraAlvoMin)}
            </span>
          </div>
        </div>
      );
    }

    return (
      <div className="prediction-strip tabular">
        <div className="prediction-highlight">
          <span>
            Agora: <strong>~{atuaisTxt} L</strong>
          </span>
          <span className={`prediction-time ${overdue ? "overdue" : ""}`}>
            {overdue
              ? "Passou do ponto"
              : predicao.horarioRetiradaPrevisto
              ? `Tirar ~${predicao.horarioRetiradaPrevisto} (${metaTxt} L)`
              : `Meta ${metaTxt} L`}
          </span>
        </div>
        {predicao.progressoPercentual !== undefined && (
          <div className="progress-track" aria-hidden="true">
            <div
              className={`progress-fill ${overdue ? "overdue" : ""}`}
              style={{ width: `${Math.min(100, Math.max(0, predicao.progressoPercentual))}%` }}
            />
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="prediction-strip tabular">
      <div className="prediction-highlight">
        <span>
          Volume estimado agora:{" "}
          <strong>~{atuaisTxt} L</strong>
          {predicao.margemErroLitros !== undefined && (
            <span className="muted"> (±{formatPtBr(predicao.margemErroLitros, 1)} L)</span>
          )}
        </span>
        <span className="pill pill-vazia">
          {NIVEL_LABEL[predicao.modeloNivel || "inicial"]}
          {predicao.amostrasUsadas ? ` · n=${predicao.amostrasUsadas}` : ""}
        </span>
      </div>

      {!predicao.aguardandoFervura ? (
        <>
          <div className="prediction-highlight">
            <span>
              Ponto para <strong>{metaTxt} L</strong>:
            </span>
            <span className={`prediction-time ${overdue ? "overdue" : ""}`}>
              {overdue
                ? "Já passou do ponto estimado"
                : `${predicao.horarioRetiradaPrevisto || "—"} (faltam ~${formatDurationMin(
                    predicao.minutosRestantes
                  )})`}
            </span>
          </div>
          {predicao.progressoPercentual !== undefined && (
            <div className="progress-track" aria-label={`Progresso até ${metaTxt} L`}>
              <div
                className={`progress-fill ${overdue ? "overdue" : ""}`}
                style={{ width: `${Math.min(100, Math.max(0, predicao.progressoPercentual))}%` }}
              />
            </div>
          )}
          <div className="muted">
            Taxa: ~{formatPtBr(predicao.taxaEvaporacaoLh, 2)} L/h
            {predicao.margemErroMinutos !== undefined && ` · Margem ±${predicao.margemErroMinutos} min`}
            {predicao.litrosIniciaisEstimados != null &&
              ` · Inicial ~${formatPtBr(predicao.litrosIniciaisEstimados, 1)} L`}
          </div>
        </>
      ) : (
        <div className="muted">
          Carga inicial ~{formatPtBr(predicao.litrosIniciaisEstimados, 1)} L · Tempo previsto de fervura:{" "}
          {formatDurationMin(predicao.tempoFervuraAlvoMin)}. Marque a fervura para prever a hora de tirar.
        </div>
      )}

      {predicao.aviso && <div className="muted">{predicao.aviso}</div>}
    </div>
  );
};
