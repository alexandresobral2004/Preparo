import React from "react";
import type { PesoSugestao, PreparoDraft } from "../types";
import { formatPtBr, tryParseDecimal } from "../domain/format";
import { avaliarPesos, avaliarProporcaoChacrona } from "../domain/calc";

interface CabecalhoViewProps {
  draft: PreparoDraft;
  onChange: (updated: PreparoDraft) => void;
  dataInputRef: React.RefObject<HTMLInputElement | null>;
  pesosSugestoes: PesoSugestao[];
  /** Acompanhante: o fieldset desabilita tudo lá dentro (campos e botões). */
  somenteLeitura?: boolean;
}

export const CabecalhoView: React.FC<CabecalhoViewProps> = ({
  draft,
  onChange,
  dataInputRef,
  pesosSugestoes,
  somenteLeitura = false,
}) => {
  const updateField = <K extends keyof PreparoDraft>(key: K, value: PreparoDraft[K]) => {
    onChange({ ...draft, [key]: value });
  };

  const pesos = avaliarPesos(draft);

  const totalChacrona = draft.chacrona.reduce((acc, item) => {
    const val = tryParseDecimal(item.kg);
    return val !== null && val > 0 ? acc + val : acc;
  }, 0);

  const proporcao = avaliarProporcaoChacrona(draft.maririKg, totalChacrona);

  const updateChacrona = (idx: number, key: "nucleo" | "kg", value: string) => {
    const next = draft.chacrona.map((item, i) =>
      i === idx ? { ...item, [key]: value } : item
    );
    updateField("chacrona", next);
  };

  const addChacrona = () => {
    updateField("chacrona", [...draft.chacrona, { nucleo: "", kg: "" }]);
  };

  const removeChacrona = (idx: number) => {
    if (draft.chacrona.length <= 1) {
      updateField("chacrona", [{ nucleo: "", kg: "" }]);
      return;
    }
    updateField(
      "chacrona",
      draft.chacrona.filter((_, i) => i !== idx)
    );
  };

  return (
    <fieldset disabled={somenteLeitura} style={{ border: 0, margin: 0, padding: 0, minWidth: 0, display: "flex", flexDirection: "column", gap: "14px" }}>
      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Dados do preparo</h2>
        </div>

        <div className="field-grid two-cols">
          <div className="field">
            <label className="field-label" htmlFor="cab-nucleo">
              Núcleo
            </label>
            <input
              id="cab-nucleo"
              type="text"
              className="input"
              value={draft.nucleo}
              onChange={(e) => updateField("nucleo", e.target.value)}
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="cab-data">
              Data do preparo
            </label>
            <input
              ref={dataInputRef}
              id="cab-data"
              type="date"
              className="input tabular"
              value={draft.data}
              onChange={(e) => updateField("data", e.target.value)}
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="cab-mestre">
              Mestre do preparo
            </label>
            <input
              id="cab-mestre"
              type="text"
              className="input"
              placeholder="Nome do mestre"
              value={draft.mestre}
              onChange={(e) => updateField("mestre", e.target.value)}
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="cab-auxiliar">
              Auxiliar
            </label>
            <input
              id="cab-auxiliar"
              type="text"
              className="input"
              placeholder="Nome do auxiliar"
              value={draft.auxiliar}
              onChange={(e) => updateField("auxiliar", e.target.value)}
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="cab-resp-mariri">
              Responsável pelo Mariri
            </label>
            <input
              id="cab-resp-mariri"
              type="text"
              className="input"
              value={draft.respMariri}
              onChange={(e) => updateField("respMariri", e.target.value)}
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="cab-resp-chacrona1">
              1º Responsável pela Chacrona
            </label>
            <input
              id="cab-resp-chacrona1"
              type="text"
              className="input"
              value={draft.respChacrona}
              onChange={(e) => updateField("respChacrona", e.target.value)}
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="cab-resp-chacrona2">
              2º Responsável pela Chacrona
            </label>
            <input
              id="cab-resp-chacrona2"
              type="text"
              className="input"
              value={draft.respChacrona2}
              onChange={(e) => updateField("respChacrona2", e.target.value)}
            />
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Pesos das panelas</h2>
        </div>
        <p className="muted">As panelas são iguais, então os três pesos valem para o preparo todo e são informados uma vez só. O app estima a relação entre o peso e os litros colhidos usando os padrões estatísticos dos preparos, e vai ajustando a cada panela colhida. A água (peso c − peso b, 1 kg ≈ 1 L) só passa a entrar na estimativa depois que houver preparos suficientes com esse dado.</p>

        <datalist id="pesos-panelas-list">
          {pesosSugestoes.map((item) => (
            <option
              key={item.pesoKg}
              value={String(item.pesoKg).replace(".", ",")}
              label={`${formatPtBr(item.pesoKg, 2)} kg (${item.usos}x)`}
            />
          ))}
        </datalist>

        <div className="field-grid two-cols">
          <div className="field">
            <label className="field-label" htmlFor="cab-peso-seca">
              a) Panela vazia (kg)
            </label>
            <input
              id="cab-peso-seca"
              type="text"
              inputMode="decimal"
              list="pesos-panelas-list"
              className="input tabular"
              placeholder="Ex.: 12,5"
              value={draft.pesoSecaKg}
              onChange={(e) => updateField("pesoSecaKg", e.target.value)}
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="cab-peso-cheia">
              b) Panela + mariri e chacrona (kg)
            </label>
            <input
              id="cab-peso-cheia"
              type="text"
              inputMode="decimal"
              className={`input tabular ${pesos.materialInvalido ? "invalid" : ""}`}
              placeholder="Ex.: 38,0"
              value={draft.pesoCheiaKg}
              onChange={(e) => updateField("pesoCheiaKg", e.target.value)}
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="cab-peso-com-agua">
              c) Panela + mariri, chacrona e água (kg)
            </label>
            <input
              id="cab-peso-com-agua"
              type="text"
              inputMode="decimal"
              className={`input tabular ${pesos.aguaInvalida ? "invalid" : ""}`}
              placeholder="Ex.: 58,5"
              value={draft.pesoComAguaKg}
              onChange={(e) => updateField("pesoComAguaKg", e.target.value)}
            />
          </div>
        </div>

        {pesos.material !== null && (
          <div className={pesos.material > 0 ? "muted tabular" : "alert-box alert-danger"}>
            {pesos.material > 0
              ? `Mariri + chacrona na panela (b − a): ${formatPtBr(pesos.material, 2)} kg`
              : "O peso b (com mariri e chacrona) deve ser maior que o peso a (panela vazia)."}
          </div>
        )}
        {pesos.agua !== null && (
          <div className={pesos.agua > 0 ? "muted tabular" : "alert-box alert-danger"}>
            {pesos.agua > 0
              ? `Água na panela (c − b): ${formatPtBr(pesos.agua, 2)} kg ≈ ${formatPtBr(pesos.agua, 2)} L`
              : "O peso c (com água) deve ser maior que o peso b (sem água)."}
          </div>
        )}
      </section>

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Mariri</h2>
        </div>

        <div className="field-grid two-cols">
          <div className="field">
            <label className="field-label" htmlFor="cab-mariri-proc">
              Procedência
            </label>
            <input
              id="cab-mariri-proc"
              type="text"
              className="input"
              placeholder="Ex.: Tucunacá, Caupuri..."
              value={draft.mariri}
              onChange={(e) => updateField("mariri", e.target.value)}
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="cab-mariri-kg">
              Quantidade (Kg)
            </label>
            <input
              id="cab-mariri-kg"
              type="text"
              inputMode="decimal"
              className="input tabular"
              placeholder="Ex.: 120,5"
              value={draft.maririKg}
              onChange={(e) => updateField("maririKg", e.target.value)}
            />
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Chacrona por núcleo</h2>
          <span className="pill pill-no_fogo tabular">
            Total: {formatPtBr(totalChacrona, 2)} Kg
          </span>
        </div>

        {proporcao && (
          <div className={proporcao.foraDaProporcao ? "alert-box alert-warn" : "muted tabular"}>
            {proporcao.foraDaProporcao
              ? `Total de chacrona fora da proporção usual (~10 kg de mariri para 1 kg de chacrona): esperado cerca de ${formatPtBr(proporcao.esperadoKg, 1)} kg. Confira os valores.`
              : `Proporção usual (10:1): cerca de ${formatPtBr(proporcao.esperadoKg, 1)} kg de chacrona.`}
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {draft.chacrona.map((item, idx) => (
            <div className="chacrona-row" key={idx}>
              <input
                type="text"
                className="input"
                aria-label={`Núcleo de origem da chacrona ${idx + 1}`}
                placeholder={`Núcleo de origem ${idx + 1}`}
                value={item.nucleo}
                onChange={(e) => updateChacrona(idx, "nucleo", e.target.value)}
              />
              <input
                type="text"
                inputMode="decimal"
                className="input tabular"
                aria-label={`Quantidade de chacrona ${idx + 1} em Kg`}
                placeholder="Kg"
                value={item.kg}
                onChange={(e) => updateChacrona(idx, "kg", e.target.value)}
              />
              <button
                type="button"
                className="btn btn-icon"
                onClick={() => removeChacrona(idx)}
                aria-label={`Remover linha de chacrona ${idx + 1}`}
                title="Remover linha"
              >
                ×
              </button>
            </div>
          ))}
        </div>

        <button type="button" className="btn" onClick={addChacrona}>
          + Adicionar linha de chacrona
        </button>
      </section>

      <section className="card">
        <div className="field">
          <label className="field-label" htmlFor="cab-obs">
            Observações gerais do preparo
          </label>
          <textarea
            id="cab-obs"
            className="textarea"
            placeholder="Anotações gerais, condições do fogo, observações..."
            value={draft.obsGeral}
            onChange={(e) => updateField("obsGeral", e.target.value)}
          />
        </div>
      </section>
    </fieldset>
  );
};
