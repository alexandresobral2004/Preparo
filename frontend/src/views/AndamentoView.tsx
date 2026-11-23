import React, { useState } from "react";
import {
  TIPOS_PANELA,
  type ConfigAvisos,
  type LembreteItem,
  type PanelaEstado,
  type PredictResponse,
  type PreparoDraft,
} from "../types";
import {
  calcularNoFogoHa,
  diffMinutes,
  estadoPanela,
  estadoPassaFiltro,
  validarPanelaLocal,
  type FiltroAndamento,
} from "../domain/calc";

const OPCOES_FILTRO: { valor: FiltroAndamento; rotulo: string }[] = [
  { valor: "todas", rotulo: "Todas" },
  { valor: "no_fogo", rotulo: "No fogo" },
  { valor: "colhida", rotulo: "Colhidas" },
];

const MENSAGEM_FILTRO_VAZIO: Record<FiltroAndamento, string> = {
  todas: "",
  no_fogo: "Nenhuma panela no fogo no momento.",
  colhida: "Nenhuma panela colhida ainda.",
};
import {
  formatDurationMin,
  formatPtBr,
  nowHhmmLocal,
  parseDecimalPtBr,
} from "../domain/format";
import { PredictionPanel } from "../components/PredictionPanel";

interface AndamentoViewProps {
  draft: PreparoDraft;
  prediction: PredictResponse | null;
  config: ConfigAvisos;
  lembretes: LembreteItem[];
  onSaveConfig: (partial: Partial<ConfigAvisos>) => Promise<void>;
  onAddLembrete: (texto: string, horario: string) => Promise<void>;
  onToggleLembrete: (id: string, feito: boolean) => Promise<void>;
  onDeleteLembrete: (id: string) => Promise<void>;
  onGoToPanelas: () => void;
  /** Acompanhante: sem ajustes de aviso, sem lembrete novo, sem marcar nem excluir. */
  somenteLeitura?: boolean;
}

const ESTADO_TEXT: Record<PanelaEstado, string> = {
  vazia: "Vazia",
  sem_entrada: "Sem entrada",
  no_fogo: "No fogo",
  fervendo: "Fervendo",
  colhida: "✓ Colhida",
};

export const AndamentoView: React.FC<AndamentoViewProps> = ({
  draft,
  prediction,
  config,
  lembretes,
  onSaveConfig,
  onAddLembrete,
  onToggleLembrete,
  onDeleteLembrete,
  somenteLeitura = false,
  onGoToPanelas,
}) => {
  const [filtro, setFiltro] = useState<FiltroAndamento>("todas");
  const [showCalib, setShowCalib] = useState(false);

  const [metaInput, setMetaInput] = useState(
    String(config.metaLitrosPadrao).replace(".", ",")
  );
  const [minFervInput, setMinFervInput] = useState(String(config.minSemFervura));
  const [horasColInput, setHorasColInput] = useState(
    String(config.horasSemColheita).replace(".", ",")
  );

  const [lemTexto, setLemTexto] = useState("");
  const [lemHorario, setLemHorario] = useState("");

  // Constrói lista combinando estado local em tempo real + predição estatística do backend SQLite
  const items = draft.blocos.flatMap((bloco, bIdx) =>
    bloco.panelas
      .map((pan, pIdx) => {
        const estado = estadoPanela(pan);
        const serverItem = prediction?.blocos?.[bIdx]?.panelas?.[pIdx];
        const alertas =
          serverItem?.alertas ||
          validarPanelaLocal(
            pan,
            draft.data,
            config.minSemFervura,
            config.horasSemColheita
          );
        const predicao = serverItem?.predicao;
        const noFogoMin =
          estado === "no_fogo" || estado === "fervendo"
            ? calcularNoFogoHa(pan.entrada, draft.data)
            : null;
        const totalMin =
          estado === "colhida" && pan.entrada && pan.colhida
            ? diffMinutes(pan.entrada, pan.colhida)
            : null;

        return {
          blocoNum: bIdx + 1,
          pan,
          estado,
          alertas,
          predicao,
          noFogoMin,
          totalMin,
        };
      })
      .filter((item) => item.estado !== "vazia")
  );

  const noFogoCount = items.filter(
    (i) => i.estado === "no_fogo" || i.estado === "fervendo"
  ).length;
  const colhidasCount = items.filter((i) => i.estado === "colhida").length;
  const pendenciasCount = items.filter(
    (i) => i.alertas.faltando.length > 0 || i.alertas.conferir.length > 0
  ).length;

  const visibleItems = items.filter((i) => estadoPassaFiltro(i.estado, filtro));

  const handleApplyConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    const meta = parseDecimalPtBr(metaInput);
    const minFerv = Number(minFervInput);
    const horasCol = parseDecimalPtBr(horasColInput);
    await onSaveConfig({
      metaLitrosPadrao: meta.valid && meta.value ? meta.value : config.metaLitrosPadrao,
      minSemFervura: Number.isFinite(minFerv) && minFerv >= 1 ? Math.round(minFerv) : config.minSemFervura,
      horasSemColheita:
        horasCol.valid && horasCol.value ? horasCol.value : config.horasSemColheita,
    });
    setShowCalib(false);
  };

  const handleAddLembrete = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!lemTexto.trim()) return;
    await onAddLembrete(lemTexto.trim(), lemHorario.trim());
    setLemTexto("");
    setLemHorario("");
  };

  const currentHhmm = nowHhmmLocal();
  const modelSummary = prediction?.modelo;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
      {/* Resumo e Filtro */}
      <section className="card">
        <div className="metrics-grid tabular">
          <div className="metric-box">
            <div className="metric-label">No fogo</div>
            <div className="metric-value">{noFogoCount}</div>
          </div>
          <div className="metric-box">
            <div className="metric-label">Colhidas</div>
            <div className="metric-value">{colhidasCount}</div>
          </div>
          <div className="metric-box">
            <div className="metric-label">Pendências</div>
            <div className="metric-value">{pendenciasCount}</div>
          </div>
        </div>

        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
          {OPCOES_FILTRO.map((op) => (
            <button
              key={op.valor}
              type="button"
              className={`filter-toggle ${filtro === op.valor ? "active" : ""}`}
              onClick={() => setFiltro(op.valor)}
              aria-pressed={filtro === op.valor}
            >
              {op.rotulo}
            </button>
          ))}

          {!somenteLeitura && (
            <button
              type="button"
              className="btn"
              onClick={() => {
                setMetaInput(String(config.metaLitrosPadrao).replace(".", ","));
                setMinFervInput(String(config.minSemFervura));
                setHorasColInput(String(config.horasSemColheita).replace(".", ","));
                setShowCalib((s) => !s);
              }}
            >
              {showCalib ? "Fechar ajustes" : "Ajustes & Estatística"}
            </button>
          )}
        </div>

        {showCalib && !somenteLeitura && (
          <form
            onSubmit={handleApplyConfig}
            style={{
              borderTop: "1px solid var(--border-subtle)",
              paddingTop: "12px",
              display: "flex",
              flexDirection: "column",
              gap: "12px",
            }}
          >
            {modelSummary && (
              <div className="prediction-strip tabular">
                <div className="prediction-highlight">
                  <strong>Base histórica no SQLite</strong>
                  <span>
                    {modelSummary.totalPanelasColhidas} colhidas ({modelSummary.totalComPesos} com pesos)
                  </span>
                </div>
                <div className="muted">
                  Nível geral: <strong>{modelSummary.modeloGeralNivel}</strong>
                  {modelSummary.maeLitrosGeral != null &&
                    ` · MAE ${formatPtBr(modelSummary.maeLitrosGeral, 2)} L / ${formatPtBr(
                      modelSummary.maeMinutosGeral,
                      0
                    )} min`}
                  {modelSummary.r2Geral != null && ` · R² ${formatPtBr(modelSummary.r2Geral, 2)}`}
                </div>
                <div className="type-breakdown">
                  {TIPOS_PANELA.map((t) => {
                    const st = modelSummary.porTipo[t];
                    return (
                      <div className="type-chip" key={t}>
                        <span>{t}</span>
                        <span>
                          {st.comPesos}p · {formatPtBr(st.taxaEvaporacaoLh, 1)} L/h
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="field-grid two-cols">
              <div className="field">
                <label className="field-label" htmlFor="cfg-meta">
                  Meta padrão de colheita (L)
                </label>
                <input
                  id="cfg-meta"
                  type="text"
                  inputMode="decimal"
                  className="input tabular"
                  value={metaInput}
                  onChange={(e) => setMetaInput(e.target.value)}
                />
              </div>

              <div className="field">
                <label className="field-label" htmlFor="cfg-ferv">
                  Aviso sem fervura (min)
                </label>
                <input
                  id="cfg-ferv"
                  type="number"
                  min={1}
                  className="input tabular"
                  value={minFervInput}
                  onChange={(e) => setMinFervInput(e.target.value)}
                />
              </div>

              <div className="field">
                <label className="field-label" htmlFor="cfg-col">
                  Aviso sem colheita (horas)
                </label>
                <input
                  id="cfg-col"
                  type="text"
                  inputMode="decimal"
                  className="input tabular"
                  value={horasColInput}
                  onChange={(e) => setHorasColInput(e.target.value)}
                />
              </div>
            </div>

            <button type="submit" className="btn btn-primary">
              Salvar ajustes
            </button>
          </form>
        )}
      </section>

      {/* Cartões das panelas em andamento */}
      {visibleItems.length === 0 ? (
        <div className="empty-state">
          <p>
            {items.length === 0
              ? "Nenhuma panela preenchida ainda. Preencha os dados na tela Panelas para acompanhar o andamento."
              : MENSAGEM_FILTRO_VAZIO[filtro]}
          </p>
          {items.length === 0 && (
            <button type="button" className="btn btn-primary" onClick={onGoToPanelas}>
              Ir para Panelas
            </button>
          )}
        </div>
      ) : (
        visibleItems.map(({ blocoNum, pan, estado, alertas, predicao, noFogoMin, totalMin }) => (
          <article className={`pan-card estado-${estado}`} key={pan.numero}>
            <div className="pan-card-top">
              <div>
                <span className="pan-number tabular">
                  Bloco {blocoNum} · Panela {pan.numero}
                </span>
                <div className="muted">{pan.tipo || "Tipo não informado"}</div>
              </div>
              <span className={`pill pill-${estado}`}>{ESTADO_TEXT[estado]}</span>
            </div>

            <div className="metrics-grid tabular">
              <div className="metric-box">
                <div className="metric-label">Entrada</div>
                <div className="metric-value">{pan.entrada || "—"}</div>
              </div>
              <div className="metric-box">
                <div className="metric-label">Fervura</div>
                <div className="metric-value">{pan.fervura || "—"}</div>
              </div>
              <div className="metric-box">
                <div className="metric-label">
                  {estado === "colhida" ? "Colhida / Litros" : "No fogo há"}
                </div>
                <div className="metric-value">
                  {estado === "colhida"
                    ? `${pan.colhida} (${pan.litros || "—"} L)`
                    : noFogoMin !== null
                    ? formatDurationMin(noFogoMin)
                    : "—"}
                </div>
              </div>
              {totalMin !== null && (
                <div className="metric-box">
                  <div className="metric-label">Tempo total</div>
                  <div className="metric-value">{formatDurationMin(totalMin)}</div>
                </div>
              )}
            </div>

            {alertas.faltando.length > 0 && (
              <div className="alert-box alert-danger" role="alert">
                {alertas.faltando.map((msg, idx) => (
                  <div key={idx}>! {msg}</div>
                ))}
              </div>
            )}

            {alertas.conferir.length > 0 && (
              <div className="alert-box alert-warn">
                {alertas.conferir.map((msg, idx) => (
                  <div key={idx}>Conferir: {msg}</div>
                ))}
              </div>
            )}

            {predicao && estado !== "colhida" && (
              <PredictionPanel predicao={predicao} />
            )}
          </article>
        ))
      )}

      {/* Lembretes (RF-15) */}
      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Lembretes</h2>
        </div>

        {!somenteLeitura && (
          <form onSubmit={handleAddLembrete} className="field-grid">
            <div className="field">
              <label className="field-label" htmlFor="lem-texto">
                Novo lembrete
              </label>
              <input
                id="lem-texto"
                type="text"
                className="input"
                placeholder="Ex.: Conferir lenha da fornalha"
                value={lemTexto}
                onChange={(e) => setLemTexto(e.target.value)}
              />
            </div>

            <div className="pan-cols">
              <div className="field">
                <label className="field-label" htmlFor="lem-hora">
                  Horário (opcional)
                </label>
                <input
                  id="lem-hora"
                  type="time"
                  className="input tabular"
                  value={lemHorario}
                  onChange={(e) => setLemHorario(e.target.value)}
                />
              </div>

              <div className="field" style={{ justifyContent: "flex-end" }}>
                <button type="submit" className="btn btn-primary">
                  Adicionar
                </button>
              </div>
            </div>
          </form>
        )}

        {lembretes.length === 0 ? (
          <div className="muted">Nenhum lembrete adicionado.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {lembretes.map((lem) => {
              const overdue = Boolean(
                !lem.feito && lem.horario && lem.horario < currentHhmm
              );
              return (
                <div
                  key={lem.id}
                  className={`reminder-item ${overdue ? "overdue" : ""} ${
                    lem.feito ? "done" : ""
                  }`}
                >
                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                      flex: 1,
                      cursor: "pointer",
                    }}
                  >
                    <input
                      type="checkbox"
                      className="reminder-check"
                      disabled={somenteLeitura}
                      checked={lem.feito}
                      onChange={(e) => onToggleLembrete(lem.id, e.target.checked)}
                    />
                    <span>
                      <strong>{lem.texto}</strong>
                      {lem.horario && (
                        <span className="tabular"> · {lem.horario}</span>
                      )}
                      {overdue && <strong> · Atrasado</strong>}
                    </span>
                  </label>

                  {!somenteLeitura && (
                    <button
                      type="button"
                      className="btn btn-sm"
                      onClick={() => onDeleteLembrete(lem.id)}
                      aria-label={`Excluir lembrete ${lem.texto}`}
                    >
                      Excluir
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
};
