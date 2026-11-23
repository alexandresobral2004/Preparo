import type { BlocoAutoria, PreparoDraft, Usuario } from "../types";

export const SENHA_MIN = 8;

export const GRAUS = [
  { valor: "socio", rotulo: "Quadro de Sócios" },
  { valor: "instrutivo", rotulo: "Corpo Instrutivo" },
  { valor: "conselho", rotulo: "Corpo do Conselho" },
  { valor: "mestre", rotulo: "Quadro de Mestres" },
] as const;

export type FiltroSituacao = "todos" | Usuario["situacao"];

export function rotuloGrau(valor: string): string {
  return GRAUS.find((g) => g.valor === valor)?.rotulo ?? "Não informado";
}

/** Pendentes primeiro (são os que pedem ação); depois por nome, sem diferenciar acento nem caixa. */
export function ordenarUsuarios(lista: readonly Usuario[]): Usuario[] {
  const peso = (u: Usuario) => (u.situacao === "pendente" ? 0 : 1);
  return [...lista].sort(
    (a, b) => peso(a) - peso(b) || a.nome.localeCompare(b.nome, "pt-BR", { sensitivity: "base" })
  );
}

export function filtrarPorSituacao(lista: readonly Usuario[], filtro: FiltroSituacao): Usuario[] {
  return filtro === "todos" ? [...lista] : lista.filter((u) => u.situacao === filtro);
}

/** Mesma regra do backend (schemas.py): e-mail é guardado sem espaços e em minúsculas. */
export function normalizarEmail(email: string): string {
  return email.trim().toLowerCase();
}

const REGRA_EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const EMAIL_MAX = 254;
const PREFIXO_RESERVADO = "removido-"; // espelha PREFIXO_USUARIO_REMOVIDO do backend

export function validarEmail(email: string): string | null {
  const e = normalizarEmail(email);
  if (e.length > EMAIL_MAX || !REGRA_EMAIL.test(e)) return "Informe um e-mail válido.";
  if (e.startsWith(PREFIXO_RESERVADO)) return "Esse e-mail é reservado.";
  return null;
}

/** Entrar: só confere se os campos foram preenchidos; o formato do login fica com o servidor. */
export function validarEntrar(login: string, senha: string): string | null {
  if (!login.trim()) return "Informe seu e-mail ou login.";
  if (!senha) return "Informe sua senha.";
  return null;
}

export function validarNovaSenha(nova: string, confirmacao: string): string | null {
  if (nova.length < SENHA_MIN) return `A senha precisa ter pelo menos ${SENHA_MIN} caracteres.`;
  if (nova !== confirmacao) return "As senhas não conferem.";
  return null;
}

function hhmm(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** Texto exibido acima do bloco: quem criou e quem editou por último. */
export function descreverAutoria(autoria: BlocoAutoria | null | undefined): string {
  if (!autoria) return "";
  const criado = `Criado por ${autoria.criadoPorNome} às ${hhmm(autoria.criadoEm)}`;
  if (!autoria.editadoPorNome || !autoria.editadoEm) return criado;
  return `${criado} · editado por ${autoria.editadoPorNome} às ${hhmm(autoria.editadoEm)}`;
}

/**
 * Depois de gravar o rascunho, incorpora do servidor só a versão e a autoria dos blocos.
 * O resto do que a pessoa digitou enquanto a gravação ia e voltava não pode ser sobrescrito.
 */
export function mesclarRespostaDoRascunho(local: PreparoDraft, doServidor: PreparoDraft): PreparoDraft {
  const mudouVersao = local._versao !== doServidor._versao;
  let mudouAutoria = false;
  const blocos = local.blocos.map((bloco, i) => {
    const autoria = doServidor.blocos[i]?.autoria;
    if (autoria === undefined || JSON.stringify(autoria) === JSON.stringify(bloco.autoria)) return bloco;
    mudouAutoria = true;
    return { ...bloco, autoria };
  });
  if (!mudouVersao && !mudouAutoria) return local;
  return { ...local, _versao: doServidor._versao, blocos };
}
