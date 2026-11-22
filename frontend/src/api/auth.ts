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

export async function cadastrar(login: string, nome: string, senha: string): Promise<string> {
  const r = await apiFetch<{ mensagem: string }>("/api/auth/cadastro", post({ login, nome, senha }), SEM_EVENTO);
  return r.mensagem;
}

/** Usuário da sessão atual; null se não há sessão. Erro de rede é repassado (modo offline). */
export async function fetchMe(): Promise<Usuario | null> {
  try {
    const r = await apiFetch<{ usuario: Usuario }>("/api/auth/me", undefined, SEM_EVENTO);
    return r.usuario;
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
export const editarUsuario = (id: number, campos: Partial<Pick<Usuario, "nome" | "papel" | "situacao">> & { senha?: string }) =>
  apiFetch<Usuario>(`/api/usuarios/${id}`, patch(campos));

export const listarPreparos = () => apiFetch<PreparoResumo[]>("/api/preparos");
export const criarPreparo = (nome: string) => apiFetch<{ id: string; nome: string }>("/api/preparos", post({ nome }));
export const solicitarEntrada = (id: string) => apiFetch<{ situacao: string }>(`/api/preparos/${id}/solicitar`, post({}));
export const listarMembros = (id: string) => apiFetch<MembroPreparo[]>(`/api/preparos/${id}/membros`);
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
