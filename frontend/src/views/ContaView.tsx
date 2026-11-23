import React, { useCallback, useEffect, useState } from "react";
import { adicionarMembro, decidirMembro, editarPerfil, listarMembros, trocarSenha } from "../api/auth";
import { ConfirmButton } from "../components/ConfirmButton";
import { GRAUS, normalizarEmail, podeEditar, validarEmail, validarNovaSenha } from "../domain/auth";
import type { MembroPreparo, PermissaoMembro, PreparoResumo, Usuario } from "../types";

const ROTULO_PERMISSAO: Record<PermissaoMembro, string> = {
  editar: "pode editar",
  acompanhar: "só acompanha",
};

interface ContaViewProps {
  usuario: Usuario;
  preparo: PreparoResumo;
  cadastrosPendentes: number;
  onTrocarPreparo: () => void;
  onSair: () => void;
  onAbrirUsuarios: () => void;
  /** Zera o rascunho de panelas em andamento e começa um preparo novo. */
  onNovoPreparo: () => void;
  onUsuarioAtualizado: (usuario: Usuario) => void;
  onNotify: (msg: string, kind?: "error" | "info") => void;
}

export const ContaView: React.FC<ContaViewProps> = ({
  usuario,
  preparo,
  cadastrosPendentes,
  onTrocarPreparo,
  onSair,
  onAbrirUsuarios,
  onNovoPreparo,
  onUsuarioAtualizado,
  onNotify,
}) => {
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [confirma, setConfirma] = useState("");
  const [erroSenha, setErroSenha] = useState("");
  const [perfil, setPerfil] = useState({ nome: usuario.nome, grau: usuario.grau, nucleo: usuario.nucleo, email: usuario.email ?? "" });
  const [senhaAtualPerfil, setSenhaAtualPerfil] = useState("");
  const [erroPerfil, setErroPerfil] = useState("");

  const [membros, setMembros] = useState<MembroPreparo[]>([]);
  const [erroMembros, setErroMembros] = useState("");
  const [emailParticipante, setEmailParticipante] = useState("");
  // Sem valor pré-marcado: o dono precisa escolher de propósito.
  const [permissaoParticipante, setPermissaoParticipante] = useState<PermissaoMembro | "">("");
  const [enviandoParticipante, setEnviandoParticipante] = useState(false);

  const ehDono = preparo.meuPapel === "dono";
  const ehAdmin = usuario.papel === "admin";
  const emailMudou = normalizarEmail(perfil.email) !== normalizarEmail(usuario.email ?? "");

  const carregar = useCallback(async () => {
    try {
      if (ehDono) setMembros(await listarMembros(preparo.id));
    } catch (err) {
      onNotify((err as Error).message, "error");
    }
  }, [ehDono, preparo.id, onNotify]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const agir = async (acao: () => Promise<unknown>, ok: string) => {
    setErroMembros("");
    try {
      await acao();
      onNotify(ok, "info");
      await carregar();
    } catch (err) {
      const msg = (err as Error).message;
      setErroMembros(msg);
      onNotify(msg, "error");
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

  const salvarPerfil = async (e: React.FormEvent) => {
    e.preventDefault();
    setErroPerfil("");
    if (!perfil.nome.trim()) return setErroPerfil("Informe o nome.");
    if (!perfil.grau) return setErroPerfil("Escolha o seu grau.");
    if (!perfil.nucleo.trim()) return setErroPerfil("Informe o núcleo.");
    if (emailMudou) {
      const problemaEmail = validarEmail(perfil.email);
      if (problemaEmail) return setErroPerfil(problemaEmail);
      if (!senhaAtualPerfil) return setErroPerfil("Confirme sua senha atual para trocar o e-mail.");
    }
    try {
      const atualizado = await editarPerfil({
        nome: perfil.nome.trim(),
        grau: perfil.grau,
        nucleo: perfil.nucleo.trim(),
        ...(emailMudou ? { email: normalizarEmail(perfil.email), senhaAtual: senhaAtualPerfil } : {}),
      });
      onUsuarioAtualizado(atualizado);
      setSenhaAtualPerfil("");
      onNotify("Perfil salvo.", "info");
    } catch (err) {
      setErroPerfil((err as Error).message);
    }
  };

  const adicionarParticipante = async (e: React.FormEvent) => {
    e.preventDefault();
    setErroMembros("");
    const problema = validarEmail(emailParticipante);
    if (problema) return setErroMembros(problema);
    if (!permissaoParticipante) return setErroMembros("Escolha se a pessoa pode editar ou só acompanhar.");
    setEnviandoParticipante(true);
    try {
      const adicionado = await adicionarMembro(preparo.id, normalizarEmail(emailParticipante), permissaoParticipante);
      setEmailParticipante("");
      setPermissaoParticipante("");
      onNotify(`${adicionado.nome} agora participa deste preparo.`, "info");
      await carregar();
    } catch (err) {
      setErroMembros((err as Error).message);
    } finally {
      setEnviandoParticipante(false);
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
          {podeEditar(preparo) && (
            <ConfirmButton label="Novo preparo" confirmLabel="Toque para zerar o rascunho" onConfirm={onNovoPreparo} />
          )}
          <button type="button" className="btn" onClick={onTrocarPreparo}>Trocar de preparo</button>
          <button type="button" className="btn" onClick={onSair}>Sair</button>
        </div>
      </section>

      <form className="card" onSubmit={salvarPerfil} noValidate>
        <h2 className="card-title">Meu perfil</h2>
        {erroPerfil && <div className="alert-box alert-danger" role="alert">{erroPerfil}</div>}
        <div className="field">
          <label className="field-label" htmlFor="perfil-nome">Nome (aparece nos registros)</label>
          <input id="perfil-nome" className="input" autoComplete="name" maxLength={120} value={perfil.nome} onChange={(e) => setPerfil({ ...perfil, nome: e.target.value })} required />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="perfil-email">E-mail</label>
          <input
            id="perfil-email"
            className="input"
            type="email"
            inputMode="email"
            autoComplete="email"
            autoCapitalize="none"
            spellCheck={false}
            value={perfil.email}
            onChange={(e) => setPerfil({ ...perfil, email: e.target.value })}
            aria-describedby={!usuario.email ? "perfil-email-dica" : undefined}
          />
          {!usuario.email && <p id="perfil-email-dica" className="muted">Opcional: adicione um e-mail para ser encontrado por outras pessoas.</p>}
        </div>
        {emailMudou && (
          <div className="field">
            <label className="field-label" htmlFor="perfil-senha-atual">Senha atual</label>
            <input
              id="perfil-senha-atual"
              className="input"
              type="password"
              autoComplete="current-password"
              value={senhaAtualPerfil}
              onChange={(e) => setSenhaAtualPerfil(e.target.value)}
              required
            />
          </div>
        )}
        <div className="field">
          <label className="field-label" htmlFor="perfil-grau">Grau</label>
          <select id="perfil-grau" className="select" value={perfil.grau} onChange={(e) => setPerfil({ ...perfil, grau: e.target.value })} required>
            <option value="" disabled>Selecione</option>
            {GRAUS.map((g) => (
              <option key={g.valor} value={g.valor}>{g.rotulo}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="field-label" htmlFor="perfil-nucleo">Núcleo</label>
          <input id="perfil-nucleo" className="input" autoComplete="off" maxLength={80} value={perfil.nucleo} onChange={(e) => setPerfil({ ...perfil, nucleo: e.target.value })} required />
        </div>
        <button type="submit" className="btn btn-primary">Salvar perfil</button>
      </form>

      {ehDono && (
        <section className="card">
          <h2 className="card-title">Participantes do preparo</h2>
          <form onSubmit={adicionarParticipante} noValidate>
            <div className="field">
              <label className="field-label" htmlFor="participante-email">E-mail da pessoa</label>
              <input
                id="participante-email"
                className="input"
                type="email"
                inputMode="email"
                autoComplete="off"
                autoCapitalize="none"
                spellCheck={false}
                value={emailParticipante}
                onChange={(e) => setEmailParticipante(e.target.value)}
                aria-describedby={erroMembros ? "membros-erro" : undefined}
                required
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="participante-permissao">Pode</label>
              <select
                id="participante-permissao"
                className="input"
                value={permissaoParticipante}
                onChange={(e) => setPermissaoParticipante(e.target.value as PermissaoMembro | "")}
                required
              >
                <option value="" disabled>Escolha</option>
                <option value="editar">Editar o preparo</option>
                <option value="acompanhar">Só acompanhar (somente leitura)</option>
              </select>
            </div>
            {erroMembros && <div id="membros-erro" className="alert-box alert-danger" role="alert">{erroMembros}</div>}
            <button type="submit" className="btn btn-primary" disabled={enviandoParticipante || !emailParticipante.trim() || !permissaoParticipante}>
              Adicionar participante
            </button>
          </form>
          {pendentesDoPreparo.length === 0 && <p className="muted">Nenhum pedido aguardando.</p>}
          {membros.map((m) => (
            <div key={m.usuarioId} className="list-row static">
              <span>
                <strong>{m.nome}</strong> <span className="muted">· {m.email ?? m.login} · {m.papel === "dono" ? "dono" : m.situacao}{m.situacao === "aprovado" && m.papel !== "dono" ? ` · ${ROTULO_PERMISSAO[m.permissao]}` : ""}</span>
              </span>
              {m.papel !== "dono" && m.situacao === "aprovado" && (
                <select
                  className="input"
                  aria-label={`Permissão de ${m.nome}`}
                  value={m.permissao}
                  onChange={(e) =>
                    agir(
                      () => decidirMembro(preparo.id, m.usuarioId, { situacao: "aprovado", permissao: e.target.value as PermissaoMembro }),
                      `Permissão de ${m.nome} atualizada.`
                    )
                  }
                >
                  <option value="editar">Pode editar</option>
                  <option value="acompanhar">Só acompanhar</option>
                </select>
              )}
              {m.papel !== "dono" && m.situacao !== "aprovado" && (
                <>
                  <button type="button" className="btn btn-primary" aria-label={`Aprovar ${m.nome} para editar`} onClick={() => agir(() => decidirMembro(preparo.id, m.usuarioId, { situacao: "aprovado", permissao: "editar" }), `${m.nome} aprovado(a) para editar.`)}>
                    Aprovar para editar
                  </button>
                  <button type="button" className="btn" aria-label={`Aprovar ${m.nome} para acompanhar`} onClick={() => agir(() => decidirMembro(preparo.id, m.usuarioId, { situacao: "aprovado", permissao: "acompanhar" }), `${m.nome} aprovado(a) para acompanhar.`)}>
                    Aprovar para acompanhar
                  </button>
                </>
              )}
              {m.papel !== "dono" && m.situacao !== "recusado" && (
                <button type="button" className="btn" aria-label={`${m.situacao === "aprovado" ? "Remover" : "Recusar"} ${m.nome}`} onClick={() => agir(() => decidirMembro(preparo.id, m.usuarioId, { situacao: "recusado" }), `${m.nome} removido(a).`)}>
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
          <p className="muted">
            {cadastrosPendentes > 0
              ? `${cadastrosPendentes} ${cadastrosPendentes === 1 ? "cadastro aguarda" : "cadastros aguardam"} aprovação.`
              : "Nenhum cadastro aguardando aprovação."}
          </p>
          <button type="button" className={cadastrosPendentes > 0 ? "btn btn-primary" : "btn"} onClick={onAbrirUsuarios}>
            Gerenciar usuários
          </button>
        </section>
      )}
    </div>
  );
};
