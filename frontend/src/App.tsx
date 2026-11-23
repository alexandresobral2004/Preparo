import React, { useCallback, useEffect, useRef, useState } from "react";
import type {
  ConfigAvisos,
  LembreteItem,
  PesoSugestao,
  PredictResponse,
  PreparoDraft,
  PreparoResumo,
  RegistroSaved,
  TabKey,
  Usuario,
} from "./types";
import {
  ConflitoRascunhoError,
  LS_KEYS,
  checkHealth,
  clearRascunho,
  createLembrete,
  deleteLembrete,
  deleteRegistro,
  fetchConfig,
  fetchExportJson,
  fetchLembretes,
  fetchPesosPanelas,
  fetchRascunho,
  fetchRegistros,
  importRegistrosJson,
  loadCachedRegistros,
  predictBlocos,
  saveRascunho,
  saveRegistro,
  toggleLembrete,
  updateConfig,
} from "./api/client";
import {
  createEmptyPreparo,
  draftFromSavedRegistro,
  estadoPanela,
} from "./domain/calc";
import { TopBar, type StatusSalvamento } from "./components/TopBar";
import { BottomNav } from "./components/BottomNav";
import { Toast, type ToastMessage } from "./components/Toast";
import { CabecalhoView } from "./views/CabecalhoView";
import { PanelasView } from "./views/PanelasView";
import { AndamentoView } from "./views/AndamentoView";
import { RegistrosView } from "./views/RegistrosView";
import { CalcPiView } from "./views/CalcPiView";
import { ContaView } from "./views/ContaView";
import { UsuariosView } from "./views/UsuariosView";
import { mesclarRespostaDoRascunho } from "./domain/auth";

const VALID_TABS: TabKey[] = ["cabecalho", "panelas", "andamento", "registros", "calc", "conta", "usuarios"];

function getInitialTab(): TabKey {
  try {
    const saved = localStorage.getItem(LS_KEYS.ultimaTela) as TabKey | null;
    if (saved && VALID_TABS.includes(saved)) return saved;
  } catch {
    // ignore
  }
  return "cabecalho";
}

function getInitialTheme(): "light" | "dark" {
  try {
    const saved = localStorage.getItem(LS_KEYS.tema);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // ignore
  }
  if (typeof window !== "undefined" && window.matchMedia) {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return "light";
}

function loadLocalDraftFallback(anotador: string): PreparoDraft {
  try {
    const raw = localStorage.getItem(LS_KEYS.draft);
    if (raw) return JSON.parse(raw) as PreparoDraft;
  } catch {
    // ignore
  }
  return createEmptyPreparo(anotador);
}

const INTERVALO_ATUALIZACAO_RASCUNHO_MS = 15000;

interface AppProps {
  usuario: Usuario;
  preparo: PreparoResumo;
  cadastrosPendentes: number;
  onCadastrosPendentes: (quantidade: number) => void;
  onUsuarioAtualizado: (usuario: Usuario) => void;
  onTrocarPreparo: () => void;
  onSair: () => void;
}

export const App: React.FC<AppProps> = ({
  usuario,
  preparo,
  cadastrosPendentes,
  onCadastrosPendentes,
  onUsuarioAtualizado,
  onTrocarPreparo,
  onSair,
}) => {
  const ehAdmin = usuario.papel === "admin";
  // Usuários é só do admin: se a última aba salva era essa e quem entra não é admin, abre a Conta.
  const [tab, setTab] = useState<TabKey>(() => {
    const salva = getInitialTab();
    return salva === "usuarios" && !ehAdmin ? "conta" : salva;
  });
  const [theme, setTheme] = useState<"light" | "dark">(getInitialTheme);
  const [online, setOnline] = useState(true);
  const [hydrated, setHydrated] = useState(false);

  const [draft, setDraft] = useState<PreparoDraft>(() => loadLocalDraftFallback(usuario.nome));
  const [registros, setRegistros] = useState<RegistroSaved[]>(loadCachedRegistros);
  const [lembretes, setLembretes] = useState<LembreteItem[]>([]);
  const [config, setConfig] = useState<ConfigAvisos>({
    minSemFervura: 30,
    horasSemColheita: 5,
    metaLitrosPadrao: 10.15,
  });
  const [pesosSugestoes, setPesosSugestoes] = useState<PesoSugestao[]>([]);
  const [prediction, setPrediction] = useState<PredictResponse | null>(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<ToastMessage | null>(null);

  const dataInputRef = useRef<HTMLInputElement | null>(null);
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const dirtyRef = useRef(false);
  const [statusSalvamento, setStatusSalvamento] = useState<StatusSalvamento>("salvo");
  // Só a resposta do salvamento mais recente atualiza o indicador.
  const salvamentoSeqRef = useRef(0);

  const notify = useCallback((text: string, kind: "info" | "error" = "info") => {
    const id = Date.now();
    setToast({ id, text, kind });
    window.setTimeout(() => {
      setToast((curr) => (curr?.id === id ? null : curr));
    }, kind === "error" ? 6000 : 3200);
  }, []);

  // Tema claro/escuro (RU-09)
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(LS_KEYS.tema, theme);
    } catch {
      // ignore
    }
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute("content", theme === "dark" ? "#0f1713" : "#1d5c36");
    }
  }, [theme]);

  // Lembrar última tela aberta (RU-10)
  useEffect(() => {
    try {
      localStorage.setItem(LS_KEYS.ultimaTela, tab);
    } catch {
      // ignore
    }
  }, [tab]);

  const refreshPrediction = useCallback(
    async (targetDraft: PreparoDraft, metaLitros?: number) => {
      try {
        const res = await predictBlocos(targetDraft, metaLitros);
        setPrediction(res);
        setOnline(true);
      } catch {
        setOnline(false);
      }
    },
    []
  );

  // Carga inicial do SQLite
  useEffect(() => {
    let active = true;
    (async () => {
      const ok = await checkHealth();
      if (!active) return;
      setOnline(ok);
      if (!ok) {
        setHydrated(true);
        return;
      }

      try {
        const [regs, cfg, lems, pesos, serverDraft] = await Promise.all([
          fetchRegistros(),
          fetchConfig(),
          fetchLembretes(),
          fetchPesosPanelas(),
          fetchRascunho(),
        ]);
        if (!active) return;
        setRegistros(regs);
        setConfig(cfg);
        setLembretes(lems);
        setPesosSugestoes(pesos);
        if (serverDraft && Array.isArray(serverDraft.blocos)) {
          setDraft(serverDraft);
        }
      } catch {
        if (active) setOnline(false);
      } finally {
        if (active) setHydrated(true);
      }
    })();

    return () => {
      active = false;
    };
  }, []);

  // Auto-save do rascunho no SQLite + atualização de predições estatísticas
  useEffect(() => {
    if (!hydrated) return;
    try {
      localStorage.setItem(LS_KEYS.draft, JSON.stringify(draft));
    } catch {
      // ignore
    }
    dirtyRef.current = true;
    const seq = ++salvamentoSeqRef.current;
    setStatusSalvamento("salvando");
    const marcar = (status: StatusSalvamento) => {
      if (seq === salvamentoSeqRef.current) setStatusSalvamento(status);
    };
    const timer = window.setTimeout(() => {
      void saveRascunho(draft)
        .then((doServidor) => {
          dirtyRef.current = false;
          marcar("salvo");
          // Só versão e autoria vêm do servidor; o que foi digitado nesse meio tempo fica.
          setDraft((atual) => mesclarRespostaDoRascunho(atual, doServidor));
        })
        .catch((err) => {
          if (err instanceof ConflitoRascunhoError) {
            dirtyRef.current = false;
            if (err.atual) {
              marcar("salvo");
              setDraft(err.atual);
              notify("Outra pessoa alterou o preparo. A tela foi atualizada com a versão mais recente.", "error");
            } else {
              // o rascunho foi finalizado/apagado por outra pessoa: recomeça a versão e regrava
              setDraft((atual) => ({ ...atual, _versao: undefined }));
            }
            return;
          }
          marcar("erro");
          setOnline(false);
        });
      void refreshPrediction(draft, config.metaLitrosPadrao);
    }, 400);
    return () => window.clearTimeout(timer);
  }, [draft, config.metaLitrosPadrao, hydrated, refreshPrediction, notify]);

  // Traz o que os outros participantes digitaram (só quando não há edição minha pendente)
  useEffect(() => {
    if (!hydrated) return;
    const atualizar = async () => {
      if (dirtyRef.current || document.visibilityState !== "visible") return;
      try {
        const doServidor = await fetchRascunho();
        if (dirtyRef.current) return;
        const local = draftRef.current;
        if (doServidor && Array.isArray(doServidor.blocos)) {
          if ((doServidor._versao ?? 0) > (local._versao ?? 0)) setDraft(doServidor);
        } else if (local._versao !== undefined) {
          setDraft(createEmptyPreparo(usuario.nome));
          notify("O preparo foi finalizado ou reiniciado por outra pessoa.", "info");
        }
      } catch {
        // sem rede: tenta no próximo ciclo
      }
    };
    const id = window.setInterval(() => void atualizar(), INTERVALO_ATUALIZACAO_RASCUNHO_MS);
    return () => window.clearInterval(id);
  }, [hydrated, notify, usuario.nome]);

  // Atualização periódica de 30s + visibilitychange (RF-17)
  useEffect(() => {
    const tick = () => {
      void refreshPrediction(draftRef.current, config.metaLitrosPadrao);
    };
    const interval = window.setInterval(tick, 30000);
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        tick();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [config.metaLitrosPadrao, refreshPrediction]);

  // Contagem de panelas no fogo em tempo real (No fogo + Fervendo) para badge da chama (RF-17)
  const noFogoBadgeCount = draft.blocos.reduce(
    (sum, b) =>
      sum +
      b.panelas.filter((p) => {
        const est = estadoPanela(p);
        return est === "no_fogo" || est === "fervendo";
      }).length,
    0
  );

  const handleSaveRegistro = async () => {
    if (!draft.data.trim()) {
      setTab("cabecalho");
      window.setTimeout(() => dataInputRef.current?.focus(), 80);
      notify("Informe a data do preparo no Cabeçalho antes de salvar.", "error");
      return;
    }

    setSaving(true);
    try {
      const saved = await saveRegistro(draft);
      setDraft({ ...draftFromSavedRegistro(saved), _versao: draftRef.current._versao });
      const [regs, pesos] = await Promise.all([
        fetchRegistros(),
        fetchPesosPanelas(),
      ]);
      setRegistros(regs);
      setPesosSugestoes(pesos);
      await refreshPrediction(draftFromSavedRegistro(saved), config.metaLitrosPadrao);
      setOnline(true);
      notify("Registro salvo");
    } catch (err) {
      notify(err instanceof Error ? err.message : "Erro ao salvar registro.", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleNewPreparo = async () => {
    const fresh = createEmptyPreparo(usuario.nome);
    setDraft(fresh);
    try {
      await clearRascunho();
    } catch {
      // ignore offline
    }
    notify("Novo preparo iniciado");
  };

  const handleOpenRegistro = (reg: RegistroSaved) => {
    setDraft({ ...draftFromSavedRegistro(reg), _versao: draftRef.current._versao });
    setTab("panelas");
    notify("Registro aberto para edição");
  };

  const handleDeleteRegistro = async (id: string) => {
    try {
      await deleteRegistro(id);
      const regs = await fetchRegistros();
      setRegistros(regs);
      await refreshPrediction(draft, config.metaLitrosPadrao);
      notify("Registro excluído");
    } catch (err) {
      notify(err instanceof Error ? err.message : "Erro ao excluir registro.", "error");
      throw err;
    }
  };

  const handleImportJson = async (rawText: string) => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(rawText);
    } catch {
      notify("JSON inválido. Confira o texto ou arquivo escolhido.", "error");
      return;
    }
    try {
      const res = await importRegistrosJson(parsed);
      const [regs, pesos] = await Promise.all([
        fetchRegistros(),
        fetchPesosPanelas(),
      ]);
      setRegistros(regs);
      setPesosSugestoes(pesos);
      await refreshPrediction(draft, config.metaLitrosPadrao);
      const extra = res.invalidos > 0 ? ` · ${res.invalidos} inválidos` : "";
      notify(`${res.importados} importados · ${res.jaExistentes} já existentes${extra}`);
    } catch (err) {
      notify(err instanceof Error ? err.message : "Erro ao importar JSON.", "error");
    }
  };

  const handleRescueJson = async (): Promise<string> => {
    try {
      const data = await fetchExportJson();
      const txt = JSON.stringify(data, null, 2);
      try {
        await navigator.clipboard.writeText(txt);
        notify("Dados copiados para a área de transferência");
      } catch {
        notify("JSON exibido abaixo para cópia manual");
      }
      return txt;
    } catch {
      const txt = JSON.stringify(registros, null, 2);
      notify("Sem conexão com o servidor; exibindo cache local");
      return txt;
    }
  };

  const handleSaveConfig = async (partial: Partial<ConfigAvisos>) => {
    try {
      const next = await updateConfig(partial);
      setConfig(next);
      await refreshPrediction(draft, next.metaLitrosPadrao);
      notify("Ajustes salvos");
    } catch (err) {
      notify(err instanceof Error ? err.message : "Erro ao salvar ajustes.", "error");
    }
  };

  const handleAddLembrete = async (texto: string, horario: string) => {
    try {
      const created = await createLembrete(texto, horario);
      setLembretes((prev) => [created, ...prev]);
      notify("Lembrete adicionado");
    } catch (err) {
      notify(err instanceof Error ? err.message : "Erro ao adicionar lembrete.", "error");
    }
  };

  const handleToggleLembrete = async (id: string, feito: boolean) => {
    try {
      const updated = await toggleLembrete(id, feito);
      setLembretes((prev) => prev.map((l) => (l.id === id ? updated : l)));
    } catch (err) {
      notify(err instanceof Error ? err.message : "Erro ao atualizar lembrete.", "error");
    }
  };

  const handleDeleteLembrete = async (id: string) => {
    try {
      await deleteLembrete(id);
      setLembretes((prev) => prev.filter((l) => l.id !== id));
      notify("Lembrete excluído");
    } catch (err) {
      notify(err instanceof Error ? err.message : "Erro ao excluir lembrete.", "error");
    }
  };

  return (
    <div className="app-shell">
      <TopBar
        tab={tab}
        dataPreparo={draft.data}
        mestre={draft.mestre}
        online={online}
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
        onSave={handleSaveRegistro}
        saving={saving}
        statusSalvamento={statusSalvamento}
        onSair={() => {
          if (
            statusSalvamento !== "salvo" &&
            !window.confirm("Há alterações que ainda não foram salvas no servidor e serão perdidas. Sair mesmo assim?")
          ) {
            return;
          }
          onSair();
        }}
      />

      <main className="app-main">
        {tab === "cabecalho" && (
          <CabecalhoView
            draft={draft}
            onChange={setDraft}
            dataInputRef={dataInputRef}
            pesosSugestoes={pesosSugestoes}
          />
        )}

        {tab === "panelas" && (
          <PanelasView
            draft={draft}
            prediction={prediction}
            onChange={setDraft}
            onSave={handleSaveRegistro}
            anotadorPadrao={usuario.nome}
            saving={saving}
          />
        )}

        {tab === "andamento" && (
          <AndamentoView
            draft={draft}
            prediction={prediction}
            config={config}
            lembretes={lembretes}
            onSaveConfig={handleSaveConfig}
            onAddLembrete={handleAddLembrete}
            onToggleLembrete={handleToggleLembrete}
            onDeleteLembrete={handleDeleteLembrete}
            onGoToPanelas={() => setTab("panelas")}
          />
        )}

        {tab === "registros" && (
          <RegistrosView
            registros={registros}
            onOpenRegistro={handleOpenRegistro}
            onDeleteRegistro={handleDeleteRegistro}
            onImportJson={handleImportJson}
            onRescueJson={handleRescueJson}
          />
        )}

        {tab === "calc" && <CalcPiView onNotify={notify} />}

        {tab === "conta" && (
          <ContaView
            usuario={usuario}
            preparo={preparo}
            cadastrosPendentes={cadastrosPendentes}
            onTrocarPreparo={onTrocarPreparo}
            onSair={onSair}
            onAbrirUsuarios={() => setTab("usuarios")}
            onNovoPreparo={async () => {
              await handleNewPreparo();
              setTab("panelas");
            }}
            onUsuarioAtualizado={onUsuarioAtualizado}
            onNotify={notify}
          />
        )}

        {tab === "usuarios" && ehAdmin && (
          <UsuariosView
            usuarioLogado={usuario}
            onVoltar={() => setTab("conta")}
            onNotify={notify}
            onPendentes={onCadastrosPendentes}
          />
        )}
      </main>

      <Toast toast={toast} />

      <BottomNav
        activeTab={tab === "usuarios" ? "conta" : tab}
        onSelect={setTab}
        noFogoCount={noFogoBadgeCount}
        registrosCount={registros.length}
        contaBadge={(preparo.meuPapel === "dono" ? preparo.pendentes : 0) + (ehAdmin ? cadastrosPendentes : 0)}
      />
    </div>
  );
};
