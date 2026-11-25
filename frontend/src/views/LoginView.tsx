import React, { useState } from "react";
import { cadastrar, entrar } from "../api/auth";
import { GRAUS, normalizarEmail, validarEmail, validarEntrar, validarNovaSenha } from "../domain/auth";
import type { Usuario } from "../types";

interface LoginViewProps {
  onEntrou: (usuario: Usuario) => void;
}

const FUNCIONALIDADES = [
  { titulo: "Panelas e blocos", texto: "Registre entrada, fervura e colheita de até 5 panelas por bloco, com pesos e litros." },
  { titulo: "Previsão de colheita", texto: "Litros estimados agora, horário previsto de retirada e projeção a cada 30 minutos de fervura." },
  { titulo: "Aprendizado", texto: "A previsão melhora a cada colheita e se ajusta ao fogo de cada bloco." },
  { titulo: "Alertas", texto: "Aponta o que falta preencher e panelas sem fervura ou sem colheita há muito tempo." },
  { titulo: "Equipe", texto: "Vários preparos, com dono, membros e permissão de editar ou só acompanhar." },
  { titulo: "Andamento e lembretes", texto: "Acompanhe o dia, crie lembretes e defina a meta de litros." },
  { titulo: "Uso no dia a dia", texto: "Rascunho automático, exportação em CSV e JSON e instalação como app, com uso offline." },
];

export const LoginView: React.FC<LoginViewProps> = ({ onEntrou }) => {
  const [modo, setModo] = useState<"entrar" | "cadastrar">("entrar");
  const [login, setLogin] = useState("");
  const [email, setEmail] = useState("");
  const [erroEmail, setErroEmail] = useState("");
  const [nome, setNome] = useState("");
  const [grau, setGrau] = useState("");
  const [nucleo, setNucleo] = useState("Bendito Filho");
  const [senha, setSenha] = useState("");
  const [confirmacao, setConfirmacao] = useState("");
  const [mostrar, setMostrar] = useState(false);
  const [erro, setErro] = useState("");
  const [aviso, setAviso] = useState("");
  const [enviando, setEnviando] = useState(false);

  const trocarModo = (novo: "entrar" | "cadastrar") => {
    setModo(novo);
    setErro("");
    setErroEmail("");
    setAviso("");
    setSenha("");
    setConfirmacao("");
  };

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    setErro("");
    setErroEmail("");
    setAviso("");
    if (modo === "entrar") {
      const problemaEntrar = validarEntrar(login, senha);
      if (problemaEntrar) return setErro(problemaEntrar);
    } else {
      const problemaEmail = validarEmail(email);
      if (problemaEmail) return setErroEmail(problemaEmail);
      if (!grau) return setErro("Escolha o seu grau.");
      if (!nucleo.trim()) return setErro("Informe o núcleo.");
      const problema = validarNovaSenha(senha, confirmacao);
      if (problema) return setErro(problema);
    }
    setEnviando(true);
    try {
      if (modo === "entrar") {
        onEntrou(await entrar(login.trim(), senha));
      } else {
        const emailNormalizado = normalizarEmail(email);
        const mensagem = await cadastrar({ email: emailNormalizado, nome: nome.trim(), grau, nucleo: nucleo.trim(), senha });
        trocarModo("entrar");
        setLogin(emailNormalizado);
        setAviso(mensagem);
      }
    } catch (err) {
      setErro(err instanceof TypeError ? "Sem conexão com o servidor." : (err as Error).message);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="auth-screen">
      <div className="auth-topo">
        <section className="auth-hero" aria-labelledby="auth-hero-titulo">
          <img className="auth-hero-foto" src="/img/login-lago.jpg" alt="" aria-hidden="true" />
          <div className="auth-hero-texto">
            <h1 id="auth-hero-titulo" className="auth-hero-titulo">Monitor de Preparo</h1>
            <p className="auth-hero-lead">
              Acompanhe cada panela, da entrada no fogo até a colheita, e saiba quantos litros ela terá e quando tirar.
            </p>
          </div>
        </section>

        <div className="auth-form-col">
          <form className="card auth-card" onSubmit={enviar} noValidate>
        <h2 className="card-title">{modo === "entrar" ? "Entrar" : "Criar conta"}</h2>
        <p className="muted">{modo === "entrar" ? "Entre com seu e-mail ou login e senha." : "Crie sua conta para participar."}</p>

        {aviso && <div className="alert-box alert-warn" role="status">{aviso}</div>}
        {erro && <div className="alert-box alert-danger" role="alert">{erro}</div>}

        {modo === "entrar" ? (
          <div className="field">
            <label className="field-label" htmlFor="auth-login">E-mail ou login</label>
            <input
              id="auth-login"
              className="input"
              type="text"
              inputMode="email"
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              aria-describedby="auth-login-dica"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              required
            />
            <p id="auth-login-dica" className="muted">Contas antigas entram com o login de sempre.</p>
          </div>
        ) : (
          <div className="field">
            <label className="field-label" htmlFor="auth-email">E-mail</label>
            <input
              id="auth-email"
              className="input"
              type="email"
              inputMode="email"
              autoComplete="email"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              aria-describedby={erroEmail ? "auth-email-erro" : undefined}
              aria-invalid={erroEmail ? true : undefined}
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setErroEmail("");
              }}
              required
            />
            {erroEmail && <p id="auth-email-erro" className="alert-box alert-danger" role="alert">{erroEmail}</p>}
          </div>
        )}

        {modo === "cadastrar" && (
          <div className="field">
            <label className="field-label" htmlFor="auth-nome">Nome (aparece nos registros)</label>
            <input id="auth-nome" className="input" autoComplete="name" value={nome} onChange={(e) => setNome(e.target.value)} required />
          </div>
        )}

        {modo === "cadastrar" && (
          <div className="field">
            <label className="field-label" htmlFor="auth-grau">Grau</label>
            <select id="auth-grau" className="select" value={grau} onChange={(e) => setGrau(e.target.value)} required>
              <option value="" disabled>Selecione</option>
              {GRAUS.map((g) => (
                <option key={g.valor} value={g.valor}>{g.rotulo}</option>
              ))}
            </select>
          </div>
        )}

        {modo === "cadastrar" && (
          <div className="field">
            <label className="field-label" htmlFor="auth-nucleo">Núcleo</label>
            <input
              id="auth-nucleo"
              className="input"
              autoComplete="off"
              maxLength={80}
              value={nucleo}
              onChange={(e) => setNucleo(e.target.value)}
              required
            />
          </div>
        )}

        <div className="field">
          <label className="field-label" htmlFor="auth-senha">Senha</label>
          <div className="pan-litros-row">
            <input
              id="auth-senha"
              className="input"
              type={mostrar ? "text" : "password"}
              autoComplete={modo === "entrar" ? "current-password" : "new-password"}
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              required
            />
            <button type="button" className="btn" onClick={() => setMostrar((v) => !v)} aria-pressed={mostrar}>
              {mostrar ? "Ocultar" : "Mostrar"}
            </button>
          </div>
        </div>

        {modo === "cadastrar" && (
          <div className="field">
            <label className="field-label" htmlFor="auth-confirma">Repita a senha</label>
            <input
              id="auth-confirma"
              className="input"
              type={mostrar ? "text" : "password"}
              autoComplete="new-password"
              value={confirmacao}
              onChange={(e) => setConfirmacao(e.target.value)}
              required
            />
          </div>
        )}

        <button type="submit" className="btn btn-primary" disabled={enviando}>
          {enviando ? "Aguarde..." : modo === "entrar" ? "Entrar" : "Criar conta"}
        </button>
        <button type="button" className="btn" onClick={() => trocarModo(modo === "entrar" ? "cadastrar" : "entrar")}>
          {modo === "entrar" ? "Criar conta" : "Já tenho conta"}
        </button>
          </form>
        </div>
      </div>

      <section className="landing" aria-labelledby="landing-titulo">
        <h2 id="landing-titulo" className="landing-titulo">O que o Monitor de Preparo faz</h2>
        <div className="landing-grade">
          {FUNCIONALIDADES.map((f) => (
            <article key={f.titulo} className="card landing-card">
              <h3 className="landing-card-titulo">{f.titulo}</h3>
              <p className="muted">{f.texto}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
};
