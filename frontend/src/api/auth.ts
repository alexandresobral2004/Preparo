import type { MembroPreparo, PreparoResumo, Usuario } from "../types";
import { apiFetch, LS_KEYS } from "./client";

// 401 no login/me é resposta normal (senha errada / sem sessão), não "sessão expirada".
const SEM_EVENTO = { semEventoDeSessao: true } as const;

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });
const patch = (body: unknown): RequestInit => ({ method: "PATCH", body: JSON.stringify(body) });

export async function entrar(login: string, senha: string): Promise<Usuario> {
  const r = await apiFetch<{ usuario: Usuario }>("/api/auth/login", post({ login, senha }), SEM_EVENTO);
  return r.usuario;
}

export interface DadosCadastro {
  email: string;
  nome: string;
  grau: string;
  nucleo: string;
  senha: string;
}

export async function cadastrar(dados: DadosCadastro): Promise<string> {
  const r = await apiFetch<{ mensagem: string }>("/api/auth/cadastro", post(dados), SEM_EVENTO);
  return r.mensagem;
}

export interface SessaoAtual {
  usuario: Usuario;
  /** Só o admin recebe a contagem; para os demais fica 0. */
  cadastrosPendentes: number;
}

/** Sessão atual; null se não há sessão. Erro de rede é repassado (modo offline). */
export async function fetchMe(): Promise<SessaoAtual | null> {
  try {
    const r = await apiFetch<{ usuario: Usuario; cadastrosPendentes?: number }>("/api/auth/me", undefined, SEM_EVENTO);
    return { usuario: r.usuario, cadastrosPendentes: r.cadastrosPendentes ?? 0 };
  } catch (err) {
    if (err instanceof TypeError) throw err; // fetch falhou: sem rede
    return null;
  }
}

export async function sair(): Promise<void> {
  await apiFetch("/api/auth/logout", post({}), SEM_EVENTO).catch(() => undefined);
}

export async function trocarSenha(senhaAtual: string, novaSenha: string): Promise<void> {
  await apiFetch("/api/auth/senha", post({ senhaAtual, novaSenha }));
}

export const listarUsuarios = () => apiFetch<Usuario[]>("/api/usuarios");

export interface DadosUsuarioNovo extends DadosCadastro {
  papel: Usuario["papel"];
}

export type CamposUsuario = Partial<Pick<Usuario, "nome" | "grau" | "nucleo" | "papel" | "situacao" | "email">> & { senha?: string };

export const criarUsuario = (dados: DadosUsuarioNovo) => apiFetch<Usuario>("/api/usuarios", post(dados));
export const editarUsuario = (id: number, campos: CamposUsuario) => apiFetch<Usuario>(`/api/usuarios/${id}`, patch(campos));

/** Apaga o usuário, ou o anonimiza quando ele tem histórico (anonimizado: true). */
export const excluirUsuario = (id: number) =>
  apiFetch<{ anonimizado: boolean }>(`/api/usuarios/${id}`, { method: "DELETE" });

/** Trocar o e-mail exige senhaAtual (o backend recusa com 400 sem ela). */
export const editarPerfil = (campos: { nome?: string; grau?: string; nucleo?: string; email?: string; senhaAtual?: string }) =>
  apiFetch<Usuario>("/api/auth/perfil", patch(campos));

export const listarPreparos = () => apiFetch<PreparoResumo[]>("/api/preparos");
export const criarPreparo = (nome: string) => apiFetch<{ id: string; nome: string }>("/api/preparos", post({ nome }));
export const solicitarEntrada = (id: string) => apiFetch<{ situacao: string }>(`/api/preparos/${id}/solicitar`, post({}));
export const listarMembros = (id: string) => apiFetch<MembroPreparo[]>(`/api/preparos/${id}/membros`);
export const adicionarMembro = (preparoId: string, email: string) =>
  apiFetch<{ usuarioId: number; nome: string; papel: string; situacao: "aprovado" }>(
    `/api/preparos/${preparoId}/membros`,
    post({ email })
  );
export const decidirMembro = (preparoId: string, usuarioId: number, situacao: "aprovado" | "recusado") =>
  apiFetch<{ situacao: string }>(`/api/preparos/${preparoId}/membros/${usuarioId}`, patch({ situacao }));

const CHAVES_DE_DADOS = [LS_KEYS.draft, LS_KEYS.registros, LS_KEYS.lembretes, LS_KEYS.config] as const;

function apagar(chaves: readonly string[]): void {
  for (const chave of chaves) {
    try {
      localStorage.removeItem(chave);
    } catch {
      // ignore
    }
  }
}

/** Dados em cache pertencem a um preparo: apagar ao trocar de preparo para não aparecerem em outro. */
export function limparCachesDeDados(): void {
  apagar(CHAVES_DE_DADOS);
}

/** Remove do aparelho tudo o que é privado (dados, usuário e preparo escolhidos). Mantém o tema. */
export function limparDadosLocais(): void {
  apagar([...CHAVES_DE_DADOS, LS_KEYS.usuario, LS_KEYS.preparoAtivo, LS_KEYS.ultimaTela]);
}
