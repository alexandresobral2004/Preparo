import React, { useState } from "react";
import { multiplyByPiExact } from "../domain/calc";

const DECIMALS_OPTIONS = [2, 4, 6, 10, 15] as const;

interface CalcPiViewProps {
  onNotify: (text: string, kind?: "info" | "error") => void;
}

export const CalcPiView: React.FC<CalcPiViewProps> = ({ onNotify }) => {
  const [valor, setValor] = useState("");
  const [casas, setCasas] = useState<number>(4);

  const result = multiplyByPiExact(valor, casas);

  const handleCopy = async () => {
    if (!result.ok) return;
    try {
      await navigator.clipboard.writeText(result.formatted);
      onNotify("Resultado copiado");
    } catch {
      onNotify("Não foi possível copiar automaticamente. Selecione o número acima.", "error");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Multiplicação por π</h2>
        </div>

        <div className="field">
          <label className="field-label" htmlFor="calc-pi-input">
            Valor decimal (aceita vírgula ou ponto)
          </label>
          <input
            id="calc-pi-input"
            type="text"
            inputMode="decimal"
            className={`input tabular ${!result.ok && !result.empty ? "invalid" : ""}`}
            placeholder="Ex.: 10,5"
            value={valor}
            onChange={(e) => setValor(e.target.value)}
          />
        </div>

        <div className="field">
          <span className="field-label">Casas decimais</span>
          <div className="segmented" role="group" aria-label="Casas decimais">
            {DECIMALS_OPTIONS.map((opt) => (
              <button
                key={opt}
                type="button"
                className={`seg-btn tabular ${casas === opt ? "active" : ""}`}
                onClick={() => setCasas(opt)}
                aria-pressed={casas === opt}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>

        {!result.ok && !result.empty && result.error && (
          <div className="alert-box alert-danger" role="alert">
            {result.error}
          </div>
        )}

        <div className="calc-result tabular" aria-live="polite">
          <div className="muted">
            {valor.trim() ? `${valor.trim()} × π` : "Digite um valor acima"}
          </div>
          <div className="calc-result-value">
            {result.ok ? result.formatted : "—"}
          </div>
        </div>

        <button
          type="button"
          className="btn btn-primary"
          disabled={!result.ok}
          onClick={handleCopy}
        >
          Copiar resultado
        </button>
      </section>
    </div>
  );
};
