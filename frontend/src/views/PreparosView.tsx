import React, { useCallback, useEffect, useState } from "react";
import { criarPreparo, listarPreparos, solicitarEntrada } from "../api/auth";
import type { PreparoResumo, Usuario } from "../types";

interface PreparosViewProps {
  usuario: Usuario;
  onEscolher: (preparo: PreparoResumo) => void;
  onSair: () => void;
}

export const PreparosView: React.FC<PreparosViewProps> = ({ usuario, onEscolher, onSair }) => {
  const [preparos, setPreparos] = useState<PreparoResumo[] | null>(null);
  const [novoNome, setNovoNome] = useState("");
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      setPreparos(await listarPreparos());
    } catch (err) {
      setErro((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const executar = async (acao: () => Promise<unknown>) => {
    setErro("");
    setOcupado(true);
    try {
      await acao();
      await carregar();
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  const meus = (preparos ?? []).filter((p) => p.minhaSituacao === "aprovado");
  const pendentes = (preparos ?? []).filter((p) => p.minhaSituacao === "pendente");
  const outros = (preparos ?? []).filter((p) => p.minhaSituacao === null);

  return (
    <div className="auth-screen">
      <div className="auth-card auth-wide" style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
        <div className="card">
          <div className="card-header">
            <div>
              <h1 className="card-title">Escolha o preparo</h1>
              <p className="muted">Olá, {usuario.nome}.</p>
            </div>
            <button type="button" className="btn" onClick={onSair}>Sair</button>
          </div>
          {erro && <div className="alert-box alert-danger" role="alert">{erro}</div>}
          {preparos === null && !erro && <p className="muted">Carregando...</p>}

          {meus.length > 0 && (
            <div className="list-stack">
              {meus.map((p) => (
                <button key={p.id} type="button" className="list-row" onClick={() => onEscolher(p)}>
                  <span>
                    <strong>{p.nome}</strong>
                    <span className="muted"> · {p.meuPapel === "dono" ? "você é o dono" : `dono: ${p.donoNome}`}</span>
                  </span>
                  {p.pendentes > 0 && <span className="pill pill-fervendo">{p.pendentes} pedido(s)</span>}
                </button>
              ))}
            </div>
          )}
          {preparos !== null && meus.length === 0 && (
            <p className="muted">Você ainda não participa de nenhum preparo. Crie um ou peça para entrar em outro.</p>
          )}
        </div>

        {pendentes.length > 0 && (
          <div className="card">
            <h2 className="card-title">Aguardando aprovação</h2>
            {pendentes.map((p) => (
              <div key={p.id} className="list-row static">
                <span><strong>{p.nome}</strong> <span className="muted">· aguardando {p.donoNome}</span></span>
              </div>
            ))}
          </div>
        )}

        {outros.length > 0 && (
          <div className="card">
            <h2 className="card-title">Pedir para participar</h2>
            {outros.map((p) => (
              <div key={p.id} className="list-row static">
                <span><strong>{p.nome}</strong> <span className="muted">· dono: {p.donoNome}</span></span>
                <button type="button" className="btn" disabled={ocupado} onClick={() => executar(() => solicitarEntrada(p.id))}>
                  Pedir para entrar
                </button>
              </div>
            ))}
          </div>
        )}

        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            const nome = novoNome.trim();
            if (!nome) return;
            void executar(async () => {
              await criarPreparo(nome);
              setNovoNome("");
            });
          }}
        >
          <h2 className="card-title">Criar um novo preparo</h2>
          <div className="field">
            <label className="field-label" htmlFor="novo-preparo">Nome do preparo</label>
            <input id="novo-preparo" className="input" value={novoNome} onChange={(e) => setNovoNome(e.target.value)} placeholder="Ex.: Bendito Filho" maxLength={80} />
          </div>
          <button type="submit" className="btn btn-primary" disabled={ocupado || !novoNome.trim()}>Criar e ser o dono</button>
        </form>
      </div>
    </div>
  );
};
