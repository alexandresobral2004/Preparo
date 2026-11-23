import React, { useState } from "react";
import { cadastrar, entrar } from "../api/auth";
import { GRAUS, validarLogin, validarNovaSenha } from "../domain/auth";
import type { Usuario } from "../types";

interface LoginViewProps {
  onEntrou: (usuario: Usuario) => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onEntrou }) => {
  const [modo, setModo] = useState<"entrar" | "cadastrar">("entrar");
  const [login, setLogin] = useState("");
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
    setAviso("");
    setSenha("");
    setConfirmacao("");
  };

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    setErro("");
    setAviso("");
    if (modo === "cadastrar") {
      const problemaLogin = validarLogin(login.trim());
      if (problemaLogin) return setErro(problemaLogin);
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
        const mensagem = await cadastrar({ login: login.trim(), nome: nome.trim(), grau, nucleo: nucleo.trim(), senha });
        trocarModo("entrar");
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
      <form className="card auth-card" onSubmit={enviar}>
        <h1 className="card-title">Preparo de Vegetal</h1>
        <p className="muted">{modo === "entrar" ? "Entre com seu login e senha." : "Crie sua conta para participar."}</p>

        {aviso && <div className="alert-box alert-warn" role="status">{aviso}</div>}
        {erro && <div className="alert-box alert-danger" role="alert">{erro}</div>}

        <div className="field">
          <label className="field-label" htmlFor="auth-login">Login</label>
          <input
            id="auth-login"
            className="input"
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            value={login}
            onChange={(e) => setLogin(e.target.value)}
            required
          />
        </div>

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
          {enviando ? "Aguarde..." : modo === "entrar" ? "Entrar" : "Enviar cadastro"}
        </button>
        <button type="button" className="btn" onClick={() => trocarModo(modo === "entrar" ? "cadastrar" : "entrar")}>
          {modo === "entrar" ? "Criar conta" : "Já tenho conta"}
        </button>
      </form>
    </div>
  );
};
