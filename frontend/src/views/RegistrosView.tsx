import React, { useEffect, useState } from "react";
import { TIPOS_PANELA, type RegistroSaved } from "../types";
import { formatDateBr, formatPtBr } from "../domain/format";
import { ConfirmButton } from "../components/ConfirmButton";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

interface RegistrosViewProps {
  registros: RegistroSaved[];
  onOpenRegistro: (reg: RegistroSaved) => void;
  onDeleteRegistro: (id: string) => Promise<void>;
  onImportJson: (rawText: string) => Promise<void>;
  onRescueJson: () => Promise<string>;
  /** Acompanhante: sem excluir, importar nem resgatar; abrir e exportar continuam. */
  somenteLeitura?: boolean;
}

export const RegistrosView: React.FC<RegistrosViewProps> = ({
  registros,
  onOpenRegistro,
  onDeleteRegistro,
  onImportJson,
  onRescueJson,
  somenteLeitura = false,
}) => {
  const [importText, setImportText] = useState("");
  const [erroExclusao, setErroExclusao] = useState<{ id: string; msg: string } | null>(null);
  const [rescueText, setRescueText] = useState("");
  const [deferredPrompt, setDeferredPrompt] =
    useState<BeforeInstallPromptEvent | null>(null);
  const [isStandalone, setIsStandalone] = useState(false);
  const [isIos, setIsIos] = useState(false);

  useEffect(() => {
    const standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      Boolean((window.navigator as unknown as { standalone?: boolean }).standalone);
    setIsStandalone(standalone);
    setIsIos(/iphone|ipad|ipod/i.test(window.navigator.userAgent));

    const handler = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  const handleInstallClick = async () => {
    if (!deferredPrompt) return;
    await deferredPrompt.prompt();
    await deferredPrompt.userChoice;
    setDeferredPrompt(null);
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    await onImportJson(text);
    e.target.value = "";
  };

  const handleDownloadJson = async () => {
    const res = await fetch("/api/registros/export/json");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "preparo-vegetal-registros.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleRescue = async () => {
    const txt = await onRescueJson();
    setRescueText(txt);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
      {/* Cartão Instalar app (RF-25 / RP-04 / RP-05) */}
      {!isStandalone && (
        <section className="card">
          <div className="card-header">
            <h2 className="card-title">Instalar app no celular</h2>
          </div>
          {deferredPrompt ? (
            <>
              <p className="muted" style={{ margin: 0 }}>
                Instale o Preparo de Vegetal na tela inicial para abrir em tela cheia e usar offline.
              </p>
              <button type="button" className="btn btn-primary" onClick={handleInstallClick}>
                Instalar app
              </button>
            </>
          ) : isIos ? (
            <p className="muted" style={{ margin: 0 }}>
              No iPhone (Safari): toque em <strong>Compartilhar</strong> (ícone de quadrado com seta)
              e escolha <strong>Adicionar à Tela de Início</strong>.
            </p>
          ) : (
            <p className="muted" style={{ margin: 0 }}>
              No menu do navegador (Chrome/Edge), toque em <strong>Instalar app</strong> ou{" "}
              <strong>Adicionar à tela inicial</strong>.
            </p>
          )}
        </section>
      )}

      {/* Lista de registros salvos */}
      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Registros salvos ({registros.length})</h2>
        </div>

        {registros.length === 0 ? (
          <div className="empty-state">
            Nenhum registro salvo. Preencha o Cabeçalho e as Panelas e toque em Salvar.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {registros.map((reg) => (
              <article
                key={reg.id}
                style={{
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-sm)",
                  padding: "12px",
                  background: "var(--bg-elevated)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "10px",
                }}
              >
                <div className="card-header">
                  <div>
                    <strong className="tabular">
                      {formatDateBr(reg.data)} · {reg.nucleo || "Bendito Filho"}
                    </strong>
                    <div className="muted">
                      Mestre: {reg.mestre || "—"}
                    </div>
                  </div>
                  <span className="pill pill-no_fogo tabular">
                    {formatPtBr(reg.totalLitros, 2)} L
                  </span>
                </div>

                <div className="metrics-grid tabular">
                  <div className="metric-box">
                    <div className="metric-label">Mariri</div>
                    <div className="metric-value">
                      {reg.maririKg != null ? `${formatPtBr(reg.maririKg, 2)} Kg` : "—"}
                    </div>
                  </div>
                  <div className="metric-box">
                    <div className="metric-label">Chacrona</div>
                    <div className="metric-value">
                      {reg.chacronaTotalKg > 0
                        ? `${formatPtBr(reg.chacronaTotalKg, 2)} Kg`
                        : "—"}
                    </div>
                  </div>
                </div>

                <div className="type-breakdown tabular">
                  {TIPOS_PANELA.map((tipo) => (
                    <div className="type-chip" key={tipo}>
                      <span>{tipo}</span>
                      <strong>{formatPtBr(reg.totaisPorTipo?.[tipo] ?? 0, 2)} L</strong>
                    </div>
                  ))}
                </div>

                {erroExclusao?.id === reg.id && (
                  <div className="alert-box alert-danger" role="alert">{erroExclusao.msg}</div>
                )}
                <div className="row-actions">
                  <button
                    type="button"
                    className="btn btn-primary"
                    aria-label={`Abrir registro de ${formatDateBr(reg.data)}`}
                    onClick={() => onOpenRegistro(reg)}
                  >
                    Abrir
                  </button>
                  {!somenteLeitura && (
                    <ConfirmButton
                      label="Excluir"
                      contexto={`registro de ${formatDateBr(reg.data)}`}
                      onConfirm={() => {
                        setErroExclusao(null);
                        onDeleteRegistro(reg.id).catch((err: unknown) =>
                          setErroExclusao({ id: reg.id, msg: err instanceof Error ? err.message : "Erro ao excluir registro." }),
                        );
                      }}
                    />
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {/* Exportação, Importação e Resgate (RF-22 a RF-24) */}
      <section className="card">
        <div className="card-header">
          <h2 className="card-title">{somenteLeitura ? "Exportar" : "Exportar, importar e resgatar"}</h2>
        </div>

        <div className="row-actions">
          <a
            href="/api/registros/export/csv"
            download="preparo-vegetal-registros.csv"
            className="btn"
            style={{ textDecoration: "none" }}
          >
            Exportar CSV
          </a>
          <button type="button" className="btn" onClick={handleDownloadJson}>
            Exportar JSON
          </button>
          {!somenteLeitura && (
            <button type="button" className="btn" onClick={handleRescue}>
              Resgatar dados
            </button>
          )}
        </div>

        {rescueText && (
          <div className="field">
            <label className="field-label" htmlFor="reg-rescue-box">
              JSON dos registros (cópia pronta)
            </label>
            <textarea
              id="reg-rescue-box"
              className="textarea tabular"
              readOnly
              value={rescueText}
              onFocus={(e) => e.currentTarget.select()}
            />
          </div>
        )}

        {!somenteLeitura && (
          <>
            <div className="field">
              <label className="field-label" htmlFor="reg-import-file">
                Importar arquivo JSON
              </label>
              <input
                id="reg-import-file"
                type="file"
                accept=".json,application/json"
                className="input"
                onChange={handleFileChange}
              />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="reg-import-text">
                Ou colar texto JSON
              </label>
              <textarea
                id="reg-import-text"
                className="textarea tabular"
                placeholder="Cole aqui o JSON exportado ou resgatado..."
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
              />
            </div>

            <button
              type="button"
              className="btn btn-primary"
              disabled={!importText.trim()}
              onClick={async () => {
                await onImportJson(importText);
                setImportText("");
              }}
            >
              Importar JSON colado
            </button>
          </>
        )}
      </section>
    </div>
  );
};
