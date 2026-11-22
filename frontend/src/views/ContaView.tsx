import React, { useCallback, useEffect, useState } from "react";
import {
  decidirMembro,
  editarUsuario,
  listarMembros,
  listarUsuarios,
  trocarSenha,
} from "../api/auth";
import { validarNovaSenha } from "../domain/auth";
import type { MembroPreparo, PreparoResumo, Usuario } from "../types";

interface ContaViewProps {
  usuario: Usuario;
  preparo: PreparoResumo;
  onTrocarPreparo: () => void;
  onSair: () => void;
  onNotify: (msg: string, kind?: "error" | "info") => void;
}

const SITUACAO_USUARIO: Record<Usuario["situacao"], string> = { pendente: "Pendente", ativo: "Ativo", inativo: "Inativo" };

export const ContaView: React.FC<ContaViewProps> = ({ usuario, preparo, onTrocarPreparo, onSair, onNotify }) => {
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [confirma, setConfirma] = useState("");
  const [erroSenha, setErroSenha] = useState("");

  const [membros, setMembros] = useState<MembroPreparo[]>([]);
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [novaSenhaDe, setNovaSenhaDe] = useState<{ id: number; senha: string } | null>(null);

  const ehDono = preparo.meuPapel === "dono";
  const ehAdmin = usuario.papel === "admin";

  const carregar = useCallback(async () => {
    try {
      if (ehDono) setMembros(await listarMembros(preparo.id));
      if (ehAdmin) setUsuarios(await listarUsuarios());
    } catch (err) {
      onNotify((err as Error).message, "error");
    }
  }, [ehDono, ehAdmin, preparo.id, onNotify]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const agir = async (acao: () => Promise<unknown>, ok: string) => {
    try {
      await acao();
      onNotify(ok, "info");
      await carregar();
    } catch (err) {
      onNotify((err as Error).message, "error");
    }
  };

  const enviarSenha = async (e: React.FormEvent) => {
    e.preventDefault();
    const problema = validarNovaSenha(nova, confirma);
    setErroSenha(problema ?? "");
    if (problema) return;
    try {
      await trocarSenha(atual, nova);
      setAtual("");
      setNova("");
      setConfirma("");
      onNotify("Senha alterada. Os outros aparelhos precisarão entrar de novo.", "info");
    } catch (err) {
      setErroSenha((err as Error).message);
    }
  };

  const pendentesDoPreparo = membros.filter((m) => m.situacao === "pendente");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
      <section className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">{usuario.nome}</h2>
            <p className="muted">
              {usuario.login} · {usuario.papel === "admin" ? "administrador" : "usuário"} · preparo: <strong>{preparo.nome}</strong>
            </p>
          </div>
        </div>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          <button type="button" className="btn" onClick={onTrocarPreparo}>Trocar de preparo</button>
          <button type="button" className="btn" onClick={onSair}>Sair</button>
        </div>
      </section>

      {ehDono && (
        <section className="card">
          <h2 className="card-title">Participantes do preparo</h2>
          {pendentesDoPreparo.length === 0 && <p className="muted">Nenhum pedido aguardando.</p>}
          {membros.map((m) => (
            <div key={m.usuarioId} className="list-row static">
              <span>
                <strong>{m.nome}</strong> <span className="muted">· {m.login} · {m.papel === "dono" ? "dono" : m.situacao}</span>
              </span>
              {m.papel !== "dono" && m.situacao !== "aprovado" && (
                <button type="button" className="btn btn-primary" onClick={() => agir(() => decidirMembro(preparo.id, m.usuarioId, "aprovado"), `${m.nome} aprovado(a).`)}>
                  Aprovar
                </button>
              )}
              {m.papel !== "dono" && m.situacao !== "recusado" && (
                <button type="button" className="btn" onClick={() => agir(() => decidirMembro(preparo.id, m.usuarioId, "recusado"), `${m.nome} removido(a).`)}>
                  {m.situacao === "aprovado" ? "Remover" : "Recusar"}
                </button>
              )}
            </div>
          ))}
        </section>
      )}

      <form className="card" onSubmit={enviarSenha}>
        <h2 className="card-title">Alterar minha senha</h2>
        {erroSenha && <div className="alert-box alert-danger" role="alert">{erroSenha}</div>}
        <div className="field">
          <label className="field-label" htmlFor="senha-atual">Senha atual</label>
          <input id="senha-atual" className="input" type="password" autoComplete="current-password" value={atual} onChange={(e) => setAtual(e.target.value)} required />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="senha-nova">Nova senha</label>
          <input id="senha-nova" className="input" type="password" autoComplete="new-password" value={nova} onChange={(e) => setNova(e.target.value)} required />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="senha-confirma">Repita a nova senha</label>
          <input id="senha-confirma" className="input" type="password" autoComplete="new-password" value={confirma} onChange={(e) => setConfirma(e.target.value)} required />
        </div>
        <button type="submit" className="btn btn-primary">Salvar nova senha</button>
      </form>

      {ehAdmin && (
        <section className="card">
          <h2 className="card-title">Usuários do sistema</h2>
          {usuarios.map((u) => (
            <div key={u.id} className="list-row static" style={{ flexWrap: "wrap" }}>
              <span>
                <strong>{u.nome}</strong> <span className="muted">· {u.login} · {u.papel} · {SITUACAO_USUARIO[u.situacao]}</span>
              </span>
              <span style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                {u.situacao !== "ativo" && (
                  <button type="button" className="btn btn-primary" onClick={() => agir(() => editarUsuario(u.id, { situacao: "ativo" }), `${u.nome} liberado(a).`)}>
                    {u.situacao === "pendente" ? "Aprovar" : "Reativar"}
                  </button>
                )}
                {u.situacao === "ativo" && u.id !== usuario.id && (
                  <button type="button" className="btn" onClick={() => agir(() => editarUsuario(u.id, { situacao: "inativo" }), `${u.nome} desativado(a).`)}>
                    Desativar
                  </button>
                )}
                <button type="button" className="btn" onClick={() => setNovaSenhaDe({ id: u.id, senha: "" })}>Nova senha</button>
              </span>
              {novaSenhaDe?.id === u.id && (
                <form
                  style={{ display: "flex", gap: "6px", width: "100%" }}
                  onSubmit={(e) => {
                    e.preventDefault();
                    void agir(() => editarUsuario(u.id, { senha: novaSenhaDe.senha }), `Senha de ${u.nome} redefinida.`).then(() => setNovaSenhaDe(null));
                  }}
                >
                  <input
                    className="input"
                    type="password"
                    autoComplete="new-password"
                    aria-label={`Nova senha de ${u.nome}`}
                    placeholder="Nova senha (mín. 8)"
                    value={novaSenhaDe.senha}
                    onChange={(e) => setNovaSenhaDe({ id: u.id, senha: e.target.value })}
                  />
                  <button type="submit" className="btn btn-primary" disabled={novaSenhaDe.senha.length < 8}>Salvar</button>
                </form>
              )}
            </div>
          ))}
        </section>
      )}
    </div>
  );
};
