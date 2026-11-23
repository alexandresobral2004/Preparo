import React from "react";
import {
  TIPOS_PANELA,
  type BlocoDraft,
  type PanelaDraft,
  type PredictResponse,
  type PreparoDraft,
} from "../types";
import {
  calcularMetricasBloco,
  calcularTotaisPorTipo,
  createEmptyBloco,
} from "../domain/calc";
import { formatDurationMin, formatPtBr } from "../domain/format";
import { ConfirmButton } from "../components/ConfirmButton";
import { PanCard } from "../components/PanCard";
import { descreverAutoria } from "../domain/auth";

interface PanelasViewProps {
  draft: PreparoDraft;
  prediction: PredictResponse | null;
  onChange: (updated: PreparoDraft) => void;
  onSave: () => void;
  /** Nome de quem está logado: já vem preenchido em "Quem está anotando" nos blocos novos. */
  anotadorPadrao: string;
  saving: boolean;
  /** Acompanhante: os campos e os botões de bloco ficam desabilitados e o Salvar some. */
  somenteLeitura?: boolean;
}

function renumberBlocos(blocos: BlocoDraft[]): BlocoDraft[] {
  return blocos.map((b, bIdx) => ({
    ...b,
    panelas: b.panelas.map((p, pIdx) => ({
      ...p,
      numero: bIdx * 5 + pIdx + 1,
    })),
  }));
}

export const PanelasView: React.FC<PanelasViewProps> = ({
  draft,
  prediction,
  onChange,
  onSave,
  anotadorPadrao,
  saving,
  somenteLeitura = false,
}) => {
  const totais = calcularTotaisPorTipo(draft.blocos);

  const updateBloco = (bIdx: number, nextBloco: BlocoDraft) => {
    const blocos = draft.blocos.map((b, i) => (i === bIdx ? nextBloco : b));
    onChange({ ...draft, blocos });
  };

  const updatePanela = (bIdx: number, pIdx: number, nextPan: PanelaDraft) => {
    const bloco = draft.blocos[bIdx];
    const nextPanelas = bloco.panelas.map((p, i) => (i === pIdx ? nextPan : p));
    updateBloco(bIdx, { ...bloco, panelas: nextPanelas });
  };

  const addBloco = () => {
    const startNumber = draft.blocos.length * 5 + 1;
    onChange({
      ...draft,
      blocos: [...draft.blocos, createEmptyBloco(startNumber, anotadorPadrao)],
    });
  };

  const removeBloco = (bIdx: number) => {
    if (draft.blocos.length <= 1) {
      onChange({ ...draft, blocos: [createEmptyBloco(1, anotadorPadrao)] });
      return;
    }
    const filtered = draft.blocos.filter((_, i) => i !== bIdx);
    onChange({ ...draft, blocos: renumberBlocos(filtered) });
  };

  return (
    <fieldset disabled={somenteLeitura} style={{ border: 0, margin: 0, padding: 0, minWidth: 0, display: "flex", flexDirection: "column", gap: "16px" }}>
      {draft.blocos.map((bloco, bIdx) => {
        const met = calcularMetricasBloco(bloco);
        const predBloco = prediction?.blocos?.[bIdx];

        return (
          <section className="card" key={bIdx} aria-label={`Bloco ${bIdx + 1}`}>
            <div className="card-header">
              <div>
                <h2 className="card-title">Bloco {bIdx + 1}</h2>
                {bloco.autoria && <div className="muted">{descreverAutoria(bloco.autoria)}</div>}
                <div className="muted tabular">
                  Total do bloco: <strong>{formatPtBr(met.totalLitros, 2)} L</strong>
                </div>
              </div>

              <ConfirmButton
                label={draft.blocos.length <= 1 ? "Limpar bloco" : "Remover bloco"}
                small
                onConfirm={() => removeBloco(bIdx)}
              />
            </div>

            <div className="field-grid two-cols">
              <div className="field">
                <label className="field-label" htmlFor={`bloco-${bIdx}-data`}>
                  Data do bloco
                </label>
                <input
                  id={`bloco-${bIdx}-data`}
                  type="date"
                  className="input tabular"
                  value={bloco.data}
                  onChange={(e) => updateBloco(bIdx, { ...bloco, data: e.target.value })}
                />
              </div>
              <div className="field">
                <label className="field-label" htmlFor={`bloco-${bIdx}-anotador`}>
                  Quem está anotando
                </label>
                <input
                  id={`bloco-${bIdx}-anotador`}
                  type="text"
                  className="input"
                  placeholder="Nome de quem registra"
                  value={bloco.anotador}
                  onChange={(e) => updateBloco(bIdx, { ...bloco, anotador: e.target.value })}
                />
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              {bloco.panelas.map((pan, pIdx) => (
                <PanCard
                  key={pan.numero}
                  panela={pan}
                  predicao={predBloco?.panelas?.[pIdx]?.predicao}
                  onChange={(updated) => updatePanela(bIdx, pIdx, updated)}
                />
              ))}
            </div>

            <div className="field">
              <label className="field-label" htmlFor={`bloco-${bIdx}-obs`}>
                Observações do bloco {bIdx + 1}
              </label>
              <textarea
                id={`bloco-${bIdx}-obs`}
                className="textarea"
                placeholder="Observações específicas deste bloco..."
                value={bloco.obs}
                onChange={(e) => updateBloco(bIdx, { ...bloco, obs: e.target.value })}
              />
            </div>

            <div className="metrics-grid tabular">
              <div className="metric-box">
                <div className="metric-label">Total</div>
                <div className="metric-value">{formatPtBr(met.totalLitros, 2)} L</div>
              </div>
              <div className="metric-box">
                <div className="metric-label">Tempo médio</div>
                <div className="metric-value">{formatDurationMin(met.tempoMedioMin)}</div>
              </div>
              <div className="metric-box">
                <div className="metric-label">Duração bloco</div>
                <div className="metric-value">{formatDurationMin(met.duracaoMin)}</div>
              </div>
              {met.litrosPorHora !== null && (
                <div className="metric-box">
                  <div className="metric-label">L / hora</div>
                  <div className="metric-value">{formatPtBr(met.litrosPorHora, 2)}</div>
                </div>
              )}
              {met.minPorLitro !== null && (
                <div className="metric-box">
                  <div className="metric-label">min / L</div>
                  <div className="metric-value">{formatPtBr(met.minPorLitro, 1)}</div>
                </div>
              )}
            </div>
          </section>
        );
      })}

      <button type="button" className="btn" onClick={addBloco}>
        + Adicionar bloco (+5 panelas)
      </button>

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Total geral colhido</h2>
          <span className="pill pill-no_fogo tabular" style={{ fontSize: "1rem" }}>
            {formatPtBr(totais.totalGeral, 2)} L
          </span>
        </div>

        <div className="type-breakdown tabular">
          {TIPOS_PANELA.map((tipo) => (
            <div className="type-chip" key={tipo}>
              <span>{tipo}</span>
              <strong>{formatPtBr(totais.porTipo[tipo], 2)} L</strong>
            </div>
          ))}
        </div>

        {!somenteLeitura && (
          <div className="row-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={onSave}
              disabled={saving}
            >
              {saving ? "Salvando..." : "Salvar registro"}
            </button>
          </div>
        )}
      </section>
    </fieldset>
  );
};
