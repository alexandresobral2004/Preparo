import React, { useCallback, useEffect, useRef, useState } from "react";
import { criarUsuario, editarUsuario, excluirUsuario, listarUsuarios, type CamposUsuario } from "../api/auth";
import { ConfirmButton } from "../components/ConfirmButton";
import {
  GRAUS,
  filtrarPorSituacao,
  normalizarEmail,
  ordenarUsuarios,
  rotuloGrau,
  validarEmail,
  validarNovaSenha,
  type FiltroSituacao,
} from "../domain/auth";
import type { Usuario } from "../types";

const FILTROS: { valor: FiltroSituacao; rotulo: string }[] = [
  { valor: "pendente", rotulo: "Pendentes" },
  { valor: "ativo", rotulo: "Ativos" },
  { valor: "inativo", rotulo: "Inativos" },
  { valor: "todos", rotulo: "Todos" },
];

const SITUACAO_TEXTO: Record<Usuario["situacao"], string> = { pendente: "Pendente", ativo: "Ativo", inativo: "Inativo" };

const sobreErro = (err: unknown): string => {
  if (err instanceof TypeError) return "Sem conexão com o servidor.";
  return err instanceof Error ? err.message : "Algo deu errado. Tente de novo.";
};

// Conversão de valor de <select> sem cast: qualquer valor fora da lista cai no padrão seguro.
const papelDe = (valor: string): Usuario["papel"] => (valor === "admin" ? "admin" : "usuario");
const situacaoDe = (valor: string): Usuario["situacao"] =>
  valor === "ativo" || valor === "inativo" ? valor : "pendente";

/** null = novo usuário; objeto = editar. */
type Alvo = Usuario | null;

interface UsuariosViewProps {
  usuarioLogado: Usuario;
  onVoltar: () => void;
  onNotify: (msg: string, kind?: "error" | "info") => void;
  onPendentes: (quantidade: number) => void;
}

export const UsuariosView: React.FC<UsuariosViewProps> = ({ usuarioLogado, onVoltar, onNotify, onPendentes }) => {
  const [lista, setLista] = useState<Usuario[] | null>(null);
  const [erroCarga, setErroCarga] = useState("");
  const [filtro, setFiltro] = useState<FiltroSituacao>("todos");
  const [edicao, setEdicao] = useState<{ alvo: Alvo } | null>(null);
  const [erroAprovar, setErroAprovar] = useState<{ id: number; msg: string } | null>(null);
  const primeiraCarga = useRef(true);

  // onPendentes deve ser uma função estável (setState do pai), senão este carregar se repete.
  const carregar = useCallback(async () => {
    setErroCarga("");
    try {
      const todos = await listarUsuarios();
      setLista(todos);
      onPendentes(todos.filter((u) => u.situacao === "pendente").length);
      if (primeiraCarga.current) {
        primeiraCarga.current = false;
        setFiltro(todos.some((u) => u.situacao === "pendente") ? "pendente" : "todos");
      }
    } catch (err) {
      setErroCarga(sobreErro(err));
    }
  }, [onPendentes]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const aposGravar = async (mensagem: string) => {
    onNotify(mensagem, "info");
    setEdicao(null);
    await carregar();
  };

  const aprovar = async (u: Usuario) => {
    setErroAprovar(null);
    try {
      await editarUsuario(u.id, { situacao: "ativo" });
      await aposGravar(`${u.nome} liberado(a).`);
    } catch (err) {
      const msg = sobreErro(err);
      setErroAprovar({ id: u.id, msg });
      onNotify(msg, "error");
    }
  };

  if (edicao) {
    return (
      <FormularioUsuario
        alvo={edicao.alvo}
        usuarioLogado={usuarioLogado}
        onCancelar={() => setEdicao(null)}
        onGravado={(mensagem) => void aposGravar(mensagem)}
        onExcluido={(anonimizado) =>
          void aposGravar(
            anonimizado ? "Usuário removido; o histórico foi mantido de forma anônima." : "Usuário excluído."
          )
        }
      />
    );
  }

  const visiveis = lista ? ordenarUsuarios(filtrarPorSituacao(lista, filtro)) : [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
      <button type="button" className="btn" onClick={onVoltar}>Voltar para Conta</button>

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Usuários do sistema</h2>
          <button type="button" className="btn btn-primary" onClick={() => setEdicao({ alvo: null })}>
            Novo usuário
          </button>
        </div>

        <div className="segmented" role="group" aria-label="Filtrar por situação" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
          {FILTROS.map((f) => (
            <button
              key={f.valor}
              type="button"
              className={`seg-btn${filtro === f.valor ? " active" : ""}`}
              aria-pressed={filtro === f.valor}
              onClick={() => setFiltro(f.valor)}
            >
              {f.rotulo}
            </button>
          ))}
        </div>

        {erroCarga && (
          <div className="alert-box alert-danger" role="alert">
            <p>Não foi possível carregar os usuários: {erroCarga}</p>
            <button type="button" className="btn" onClick={() => void carregar()}>Tentar de novo</button>
          </div>
        )}

        {!erroCarga && lista === null && <p className="muted">Carregando usuários...</p>}

        {lista !== null && visiveis.length === 0 && (
          <p className="muted">
            {filtro === "pendente" ? "Nenhum cadastro aguardando aprovação." : "Nenhum usuário neste filtro."}
          </p>
        )}

        {visiveis.length > 0 && (
          <div className="list-stack">
            {visiveis.map((u) => (
              <div key={u.id} className="usuario-linha">
                <button type="button" className="list-row" onClick={() => setEdicao({ alvo: u })}>
                  <span>
                    <strong>{u.nome}</strong>
                    <span className="muted" style={{ display: "block" }}>
                      {u.email ?? u.login} · {rotuloGrau(u.grau)} · {u.nucleo || "Sem núcleo"}
                    </span>
                  </span>
                  <span className="muted">
                    {SITUACAO_TEXTO[u.situacao]}
                    {u.papel === "admin" ? " · admin" : ""}
                  </span>
                </button>
                {u.situacao === "pendente" && (
                  <button
                    type="button"
                    className="btn"
                    aria-label={`Aprovar ${u.nome}`}
                    onClick={() => void aprovar(u)}
                  >
                    Aprovar
                  </button>
                )}
                {erroAprovar?.id === u.id && (
                  <div className="alert-box alert-danger" role="alert">{erroAprovar.msg}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};

interface FormularioUsuarioProps {
  alvo: Alvo;
  usuarioLogado: Usuario;
  onCancelar: () => void;
  onGravado: (mensagem: string) => void;
  onExcluido: (anonimizado: boolean) => void;
}

const FormularioUsuario: React.FC<FormularioUsuarioProps> = ({ alvo, usuarioLogado, onCancelar, onGravado, onExcluido }) => {
  const [nome, setNome] = useState(alvo?.nome ?? "");
  const [email, setEmail] = useState(alvo?.email ?? "");
  const [grau, setGrau] = useState(alvo?.grau ?? "");
  const [nucleo, setNucleo] = useState(alvo?.nucleo ?? "Bendito Filho");
  const [papel, setPapel] = useState<Usuario["papel"]>(alvo?.papel ?? "usuario");
  const [situacao, setSituacao] = useState<Usuario["situacao"]>(alvo?.situacao ?? "ativo");
  const [redefinir, setRedefinir] = useState(false);
  const [senha, setSenha] = useState("");
  const [confirma, setConfirma] = useState("");
  const [erro, setErro] = useState("");
  const [erroExclusao, setErroExclusao] = useState("");
  const [enviando, setEnviando] = useState(false);

  const ehSelf = alvo !== null && alvo.id === usuarioLogado.id;
  const querSenha = alvo === null || redefinir;

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    setErro("");
    if (!nome.trim()) return setErro("Informe o nome.");
    if (!grau) return setErro("Escolha o grau.");
    if (!nucleo.trim()) return setErro("Informe o núcleo.");
    // Na criação o e-mail é obrigatório; na edição, em branco significa "não mexer" (conta antiga sem e-mail).
    const emailInformado = email.trim() !== "";
    if (alvo === null || emailInformado) {
      const problemaEmail = validarEmail(email);
      if (problemaEmail) return setErro(problemaEmail);
    }
    if (querSenha) {
      const problema = validarNovaSenha(senha, confirma);
      if (problema) return setErro(problema);
    }
    setEnviando(true);
    try {
      if (alvo === null) {
        await criarUsuario({ email: normalizarEmail(email), nome: nome.trim(), grau, nucleo: nucleo.trim(), senha, papel });
        onGravado("Usuário criado.");
      } else {
        const campos: CamposUsuario = { nome: nome.trim(), grau, nucleo: nucleo.trim(), papel, situacao };
        if (emailInformado) campos.email = normalizarEmail(email);
        if (redefinir) campos.senha = senha;
        await editarUsuario(alvo.id, campos);
        onGravado("Alterações salvas.");
      }
    } catch (err) {
      setErro(sobreErro(err));
    } finally {
      setEnviando(false);
    }
  };

  const excluir = async () => {
    if (alvo === null) return;
    setErroExclusao("");
    try {
      const { anonimizado } = await excluirUsuario(alvo.id);
      onExcluido(anonimizado);
    } catch (err) {
      setErroExclusao(sobreErro(err));
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
      <form className="card" onSubmit={enviar} noValidate>
        <h2 className="card-title">{alvo === null ? "Novo usuário" : `Editar ${alvo.nome}`}</h2>
        {erro && <div className="alert-box alert-danger" role="alert">{erro}</div>}

        <div className="field">
          <label className="field-label" htmlFor="usr-nome">Nome</label>
          <input id="usr-nome" className="input" maxLength={120} value={nome} onChange={(e) => setNome(e.target.value)} required />
        </div>

        <div className="field">
          <label className="field-label" htmlFor="usr-email">E-mail</label>
          <input
            id="usr-email"
            className="input"
            type="email"
            inputMode="email"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            autoComplete="off"
            maxLength={254}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required={alvo === null}
          />
          {alvo !== null && !alvo.email && (
            <p className="muted">Opcional nesta conta antiga: informe um e-mail para ser encontrado por outras pessoas.</p>
          )}
        </div>

        <div className="field">
          <label className="field-label" htmlFor="usr-grau">Grau</label>
          <select id="usr-grau" className="select" value={grau} onChange={(e) => setGrau(e.target.value)} required>
            <option value="" disabled>Selecione</option>
            {GRAUS.map((g) => (
              <option key={g.valor} value={g.valor}>{g.rotulo}</option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field-label" htmlFor="usr-nucleo">Núcleo</label>
          <input id="usr-nucleo" className="input" autoComplete="off" maxLength={80} value={nucleo} onChange={(e) => setNucleo(e.target.value)} required />
        </div>

        <div className="field">
          <label className="field-label" htmlFor="usr-papel">Papel</label>
          <select
            id="usr-papel"
            className="select"
            value={papel}
            onChange={(e) => setPapel(papelDe(e.target.value))}
            disabled={ehSelf}
          >
            <option value="usuario">Usuário</option>
            <option value="admin">Administrador</option>
          </select>
        </div>

        {alvo !== null && (
          <div className="field">
            <label className="field-label" htmlFor="usr-situacao">Situação</label>
            <select
              id="usr-situacao"
              className="select"
              value={situacao}
              onChange={(e) => setSituacao(situacaoDe(e.target.value))}
              disabled={ehSelf}
            >
              <option value="pendente">Pendente</option>
              <option value="ativo">Ativo</option>
              <option value="inativo">Inativo</option>
            </select>
          </div>
        )}
        {ehSelf && <p className="muted">Você não pode alterar o próprio papel ou situação.</p>}

        {(alvo === null || redefinir) && (
          <>
            <div className="field">
              <label className="field-label" htmlFor="usr-senha">Senha</label>
              <input
                id="usr-senha"
                className="input"
                type="password"
                autoComplete="new-password"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="usr-confirma">Repita a senha</label>
              <input
                id="usr-confirma"
                className="input"
                type="password"
                autoComplete="new-password"
                value={confirma}
                onChange={(e) => setConfirma(e.target.value)}
                required
              />
            </div>
          </>
        )}

        {/* Redefinir a própria senha derruba as sessões do admin; isso fica na Conta. */}
        {alvo !== null && !ehSelf && !redefinir && (
          <button type="button" className="btn" onClick={() => setRedefinir(true)}>Redefinir senha</button>
        )}
        {alvo !== null && redefinir && (
          <button
            type="button"
            className="btn"
            onClick={() => {
              setRedefinir(false);
              setSenha("");
              setConfirma("");
            }}
          >
            Não redefinir a senha
          </button>
        )}

        <div className="row-actions">
          <button type="button" className="btn" onClick={onCancelar} disabled={enviando}>Cancelar</button>
          <button type="submit" className="btn btn-primary" disabled={enviando}>
            {enviando ? "Salvando..." : alvo === null ? "Criar usuário" : "Salvar alterações"}
          </button>
        </div>
      </form>

      {alvo !== null && !ehSelf && (
        <section className="card">
          <h2 className="card-title">Excluir usuário</h2>
          <p className="muted">
            Se ele já participou de preparos ou registrou dados, a conta é anonimizada: o histórico fica, sem o nome.
          </p>
          {erroExclusao && <div className="alert-box alert-danger" role="alert">{erroExclusao}</div>}
          <ConfirmButton
            label="Excluir usuário"
            confirmLabel="Toque de novo para excluir"
            onConfirm={() => void excluir()}
          />
        </section>
      )}
    </div>
  );
};
