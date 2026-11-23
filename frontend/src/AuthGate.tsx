import React, { useCallback, useEffect, useState } from "react";
import { App } from "./App";
import { fetchMe, limparCachesDeDados, limparDadosLocais, listarPreparos, sair } from "./api/auth";
import { EVENTO_SESSAO_EXPIRADA, LS_KEYS, setPreparoAtivo } from "./api/client";
import { LoginView } from "./views/LoginView";
import { PreparosView } from "./views/PreparosView";
import type { PreparoResumo, Usuario } from "./types";

type Fase = "carregando" | "login" | "preparos" | "app";

function lerLocal<T>(chave: string): T | null {
  try {
    const raw = localStorage.getItem(chave);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function gravarLocal(chave: string, valor: unknown): void {
  try {
    localStorage.setItem(chave, JSON.stringify(valor));
  } catch {
    // ignore
  }
}

export const AuthGate: React.FC = () => {
  const [fase, setFase] = useState<Fase>("carregando");
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [preparo, setPreparo] = useState<PreparoResumo | null>(null);
  const [cadastrosPendentes, setCadastrosPendentes] = useState(0);

  const escolherPreparo = useCallback((p: PreparoResumo) => {
    // Os dados em cache são do preparo anterior: só reaproveita se for o mesmo.
    const anterior = lerLocal<string>(LS_KEYS.preparoAtivo);
    if (anterior !== p.id) limparCachesDeDados();
    setPreparoAtivo(p.id);
    gravarLocal(LS_KEYS.preparoAtivo, p.id);
    gravarLocal(LS_KEYS.preparoAtivo + "_resumo", p);
    setPreparo(p);
    setFase("app");
  }, []);

  /** Depois de autenticado: reabre o último preparo, se ainda participa; senão pede a escolha. */
  const aposAutenticar = useCallback(
    async (u: Usuario, pendentes: number) => {
      setUsuario(u);
      setCadastrosPendentes(pendentes);
      gravarLocal(LS_KEYS.usuario, u);
      const ultimo = lerLocal<string>(LS_KEYS.preparoAtivo);
      try {
        const lista = await listarPreparos();
        const ativo = lista.find((p) => p.id === ultimo && p.minhaSituacao === "aprovado");
        if (ativo) return escolherPreparo(ativo);
      } catch {
        // sem rede ou sessão caiu: cai na escolha
      }
      setFase("preparos");
    },
    [escolherPreparo]
  );

  /** Login não devolve a contagem de pendentes; o /me devolve (só para admin). */
  const aposLogin = useCallback(
    async (u: Usuario) => {
      const sessao = await fetchMe().catch(() => null);
      await aposAutenticar(u, sessao?.cadastrosPendentes ?? 0);
    },
    [aposAutenticar]
  );

  useEffect(() => {
    let ativo = true;
    (async () => {
      try {
        const sessao = await fetchMe();
        if (!ativo) return;
        if (sessao) await aposAutenticar(sessao.usuario, sessao.cadastrosPendentes);
        else setFase("login");
      } catch {
        // Sem rede: abre com o último usuário/preparo deste aparelho, usando os dados em cache.
        if (!ativo) return;
        const u = lerLocal<Usuario>(LS_KEYS.usuario);
        const p = lerLocal<PreparoResumo>(LS_KEYS.preparoAtivo + "_resumo");
        if (u && p) {
          setUsuario(u);
          setPreparoAtivo(p.id);
          setPreparo(p);
          setFase("app");
        } else {
          setFase("login");
        }
      }
    })();
    return () => {
      ativo = false;
    };
  }, [aposAutenticar]);

  // O servidor respondeu 401 (sessão venceu ou foi encerrada): volta ao login sem apagar o rascunho local.
  useEffect(() => {
    const aoExpirar = () => {
      setUsuario(null);
      setFase("login");
    };
    window.addEventListener(EVENTO_SESSAO_EXPIRADA, aoExpirar);
    return () => window.removeEventListener(EVENTO_SESSAO_EXPIRADA, aoExpirar);
  }, []);

  const aoSair = async () => {
    await sair();
    limparDadosLocais();
    try {
      localStorage.removeItem(LS_KEYS.preparoAtivo + "_resumo");
    } catch {
      // ignore
    }
    if ("caches" in window) await caches.keys().then((ks) => Promise.all(ks.map((k) => caches.delete(k)))).catch(() => undefined);
    setPreparoAtivo(null);
    setUsuario(null);
    setPreparo(null);
    setFase("login");
  };

  const aoTrocarPreparo = () => {
    limparCachesDeDados();
    setPreparoAtivo(null);
    setPreparo(null);
    try {
      localStorage.removeItem(LS_KEYS.preparoAtivo);
    } catch {
      // ignore
    }
    setFase("preparos");
  };

  if (fase === "carregando") return <div className="auth-screen"><p className="muted">Carregando...</p></div>;
  if (fase === "login" || !usuario) return <LoginView onEntrou={(u) => void aposLogin(u)} />;
  if (fase === "preparos" || !preparo) {
    return <PreparosView usuario={usuario} onEscolher={escolherPreparo} onSair={() => void aoSair()} />;
  }
  return (
    <App
      key={preparo.id}
      usuario={usuario}
      preparo={preparo}
      cadastrosPendentes={cadastrosPendentes}
      onCadastrosPendentes={setCadastrosPendentes}
      onUsuarioAtualizado={(atualizado) => {
        setUsuario(atualizado);
        gravarLocal(LS_KEYS.usuario, atualizado);
      }}
      onTrocarPreparo={aoTrocarPreparo}
      onSair={() => void aoSair()}
    />
  );
};
