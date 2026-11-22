import React, { useRef, useState } from "react";
import {
  TIPOS_PANELA,
  type PanelaDraft,
  type PanelaEstado,
  type PanelaPrediction,
  type TipoPanela,
} from "../types";
import { estadoPanela } from "../domain/calc";
import { nowHhmmLocal, parseDecimalPtBr } from "../domain/format";
import { PencilIcon } from "./Icons";
import { PredictionPanel } from "./PredictionPanel";

interface PanCardProps {
  panela: PanelaDraft;
  predicao?: PanelaPrediction;
  onChange: (updated: PanelaDraft) => void;
}

const ESTADO_LABELS: Record<PanelaEstado, string> = {
  vazia: "Vazia",
  sem_entrada: "Sem entrada",
  no_fogo: "No fogo",
  fervendo: "Fervendo",
  colhida: "✓ Colhida",
};

export const PanCard: React.FC<PanCardProps> = ({ panela, predicao, onChange }) => {
  const [litrosErro, setLitrosErro] = useState<string | null>(null);
  const litrosInputRef = useRef<HTMLInputElement | null>(null);
  const estado = estadoPanela(panela);

  const updateField = <K extends keyof PanelaDraft>(key: K, value: PanelaDraft[K]) => {
    onChange({ ...panela, [key]: value });
  };

  const handleAgora = (field: "entrada" | "fervura" | "colhida") => {
    if (panela[field].trim() !== "") return;
    updateField(field, nowHhmmLocal());
  };

  const handleLitrosChange = (val: string) => {
    if (litrosErro) setLitrosErro(null);
    onChange({ ...panela, litros: val });
  };

  const handleLitrosBlur = () => {
    const raw = panela.litros.trim();
    if (!raw) {
      setLitrosErro(null);
      if (panela.litrosLocked) {
        onChange({ ...panela, litrosLocked: false });
      }
      return;
    }
    const parsed = parseDecimalPtBr(raw);
    if (!parsed.valid || parsed.value === null || parsed.value < 0) {
      setLitrosErro("Digite apenas números (use vírgula ou ponto).");
      return;
    }
    setLitrosErro(null);
    onChange({ ...panela, litrosLocked: true });
  };

  const handleUnlockLitros = () => {
    onChange({ ...panela, litrosLocked: false });
    window.setTimeout(() => litrosInputRef.current?.focus(), 0);
  };

  return (
    <article className={`pan-card estado-${estado}`} aria-label={`Panela ${panela.numero}`}>
      <div className="pan-card-top">
        <span className="pan-number tabular">Panela {panela.numero}</span>
        <span className={`pill pill-${estado}`}>{ESTADO_LABELS[estado]}</span>
      </div>

      <div className="pan-cols">
        <div className="field">
          <div className="field-label-row">
            <label className="field-label" htmlFor={`pan-${panela.numero}-tipo`}>
              Tipo
            </label>
          </div>
          <select
            id={`pan-${panela.numero}-tipo`}
            className="select"
            value={panela.tipo}
            onChange={(e) => updateField("tipo", e.target.value as TipoPanela | "")}
          >
            <option value="">Selecione...</option>
            {TIPOS_PANELA.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <div className="field-label-row">
            <label className="field-label" htmlFor={`pan-${panela.numero}-entrada`}>
              Entrada
            </label>
            <button
              type="button"
              className="btn-agora"
              disabled={panela.entrada.trim() !== ""}
              onClick={() => handleAgora("entrada")}
              aria-label={`Marcar horário atual na entrada da panela ${panela.numero}`}
            >
              Agora
            </button>
          </div>
          <input
            id={`pan-${panela.numero}-entrada`}
            type="time"
            className="input tabular"
            value={panela.entrada}
            onChange={(e) => updateField("entrada", e.target.value)}
          />
        </div>

        <div className="field">
          <div className="field-label-row">
            <label className="field-label" htmlFor={`pan-${panela.numero}-fervura`}>
              Fervura
            </label>
            <button
              type="button"
              className="btn-agora"
              disabled={panela.fervura.trim() !== ""}
              onClick={() => handleAgora("fervura")}
              aria-label={`Marcar horário atual na fervura da panela ${panela.numero}`}
            >
              Agora
            </button>
          </div>
          <input
            id={`pan-${panela.numero}-fervura`}
            type="time"
            className="input tabular"
            value={panela.fervura}
            onChange={(e) => updateField("fervura", e.target.value)}
          />
        </div>

        <div className="field">
          <div className="field-label-row">
            <label className="field-label" htmlFor={`pan-${panela.numero}-colhida`}>
              Colhida
            </label>
            <button
              type="button"
              className="btn-agora"
              disabled={panela.colhida.trim() !== ""}
              onClick={() => handleAgora("colhida")}
              aria-label={`Marcar horário atual na colhida da panela ${panela.numero}`}
            >
              Agora
            </button>
          </div>
          <input
            id={`pan-${panela.numero}-colhida`}
            type="time"
            className="input tabular"
            value={panela.colhida}
            onChange={(e) => updateField("colhida", e.target.value)}
          />
        </div>

        <div className="field">
          <div className="field-label-row">
            <label className="field-label" htmlFor={`pan-${panela.numero}-litros`}>
              Litros
            </label>
            {panela.litrosLocked && (
              <button
                type="button"
                className="btn-agora btn-agora-icon"
                onClick={handleUnlockLitros}
                aria-label={`Editar litros da panela ${panela.numero}`}
                title="Editar litros"
              >
                <PencilIcon />
              </button>
            )}
          </div>
          <input
            ref={litrosInputRef}
            id={`pan-${panela.numero}-litros`}
            type="text"
            inputMode="decimal"
            readOnly={panela.litrosLocked}
            className={`input tabular ${panela.litrosLocked ? "locked" : ""} ${
              litrosErro ? "invalid" : ""
            }`}
            placeholder="10,15"
            value={panela.litros}
            onChange={(e) => handleLitrosChange(e.target.value)}
            onBlur={handleLitrosBlur}
          />
        </div>
      </div>

      {litrosErro && <span className="alert-box alert-danger">{litrosErro}</span>}

      {predicao?.disponivel && estado !== "colhida" && (
        <PredictionPanel predicao={predicao} compact />
      )}
    </article>
  );
};
