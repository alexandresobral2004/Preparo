import type {
  ConfigAvisos,
  LembreteItem,
  PesoSugestao,
  PredictResponse,
  PreparoDraft,
  RegistroSaved,
  StatsSummary,
} from "../types";
import { buildPayloadFromDraft } from "../domain/calc";

const LS_KEYS = {
  draft: "preparo_rascunho",
  registros: "preparo_registros_cache",
  lembretes: "preparo_lembretes_cache",
  config: "preparo_avisos_cache",
  ultimaTela: "preparo_ultima_tela",
  tema: "preparo_tema_manual",
  usuario: "preparo_usuario",
  preparoAtivo: "preparo_ativo_id",
} as const;

export { LS_KEYS };

export const EVENTO_SESSAO_EXPIRADA = "preparo:sessao-expirada";

/** Preparo escolhido; vai em todo pedido para o servidor saber de quem são os dados. */
let preparoAtivoId: string | null = null;

export function setPreparoAtivo(id: string | null): void {
  preparoAtivoId = id;
}

/** O rascunho mudou no servidor desde a última leitura; `atual` é a versão mais recente. */
export class ConflitoRascunhoError extends Error {
  constructor(message: string, public readonly atual: PreparoDraft | null) {
    super(message);
  }
}

export async function apiFetch<T>(
  url: string,
  init?: RequestInit,
  opcoes?: { semEventoDeSessao?: boolean }
): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(preparoAtivoId ? { "X-Preparo-Id": preparoAtivoId } : {}),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    let message = `Erro HTTP ${res.status}`;
    let body: { detail?: unknown; atual?: PreparoDraft | null } | null = null;
    try {
      body = await res.json();
      if (body?.detail) message = String(body.detail);
    } catch {
      // ignora parse de erro não JSON
    }
    if (res.status === 401 && !opcoes?.semEventoDeSessao) {
      window.dispatchEvent(new Event(EVENTO_SESSAO_EXPIRADA));
    }
    if (res.status === 409 && body && "atual" in body) {
      throw new ConflitoRascunhoError(message, body.atual ?? null);
    }
    throw new Error(message);
  }
  return (await res.json()) as T;
}

export async function checkHealth(): Promise<boolean> {
  try {
    await apiFetch<{ status: string }>("/api/health");
    return true;
  } catch {
    return false;
  }
}

export async function fetchRegistros(): Promise<RegistroSaved[]> {
  const data = await apiFetch<RegistroSaved[]>("/api/registros");
  try {
    localStorage.setItem(LS_KEYS.registros, JSON.stringify(data));
  } catch {
    // ignore quota
  }
  return data;
}

export function loadCachedRegistros(): RegistroSaved[] {
  try {
    const raw = localStorage.getItem(LS_KEYS.registros);
    return raw ? (JSON.parse(raw) as RegistroSaved[]) : [];
  } catch {
    return [];
  }
}

export async function saveRegistro(draft: PreparoDraft): Promise<RegistroSaved> {
  const body = buildPayloadFromDraft(draft);
  if (draft.id) {
    return await apiFetch<RegistroSaved>(`/api/registros/${encodeURIComponent(draft.id)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  }
  return await apiFetch<RegistroSaved>("/api/registros", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function deleteRegistro(id: string): Promise<void> {
  await apiFetch<{ ok: boolean }>(`/api/registros/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export async function importRegistrosJson(
  payload: unknown
): Promise<{ importados: number; jaExistentes: number; invalidos: number }> {
  return await apiFetch("/api/registros/import", {
    method: "POST",
    body: JSON.stringify({ payload }),
  });
}

export async function fetchExportJson(): Promise<RegistroSaved[]> {
  return await apiFetch<RegistroSaved[]>("/api/registros/export/json");
}

export async function fetchRascunho(): Promise<PreparoDraft | null> {
  return await apiFetch<PreparoDraft | null>("/api/rascunho");
}

/** Grava o rascunho e devolve a versão do servidor (com versão e autoria). Lança ConflitoRascunhoError se estava desatualizado. */
export async function saveRascunho(draft: PreparoDraft): Promise<PreparoDraft> {
  try {
    localStorage.setItem(LS_KEYS.draft, JSON.stringify(draft));
  } catch {
    // ignore
  }
  return await apiFetch<PreparoDraft>("/api/rascunho", {
    method: "PUT",
    body: JSON.stringify(draft),
  });
}

export async function clearRascunho(): Promise<void> {
  try {
    localStorage.removeItem(LS_KEYS.draft);
  } catch {
    // ignore
  }
  await apiFetch("/api/rascunho", { method: "DELETE" });
}

export async function fetchLembretes(): Promise<LembreteItem[]> {
  const data = await apiFetch<LembreteItem[]>("/api/lembretes");
  try {
    localStorage.setItem(LS_KEYS.lembretes, JSON.stringify(data));
  } catch {
    // ignore
  }
  return data;
}

export async function createLembrete(texto: string, horario: string): Promise<LembreteItem> {
  return await apiFetch<LembreteItem>("/api/lembretes", {
    method: "POST",
    body: JSON.stringify({ texto, horario }),
  });
}

export async function toggleLembrete(id: string, feito: boolean): Promise<LembreteItem> {
  return await apiFetch<LembreteItem>(`/api/lembretes/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ feito }),
  });
}

export async function deleteLembrete(id: string): Promise<void> {
  await apiFetch(`/api/lembretes/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function fetchConfig(): Promise<ConfigAvisos> {
  const data = await apiFetch<ConfigAvisos>("/api/config");
  try {
    localStorage.setItem(LS_KEYS.config, JSON.stringify(data));
  } catch {
    // ignore
  }
  return data;
}

export async function updateConfig(partial: Partial<ConfigAvisos>): Promise<ConfigAvisos> {
  const data = await apiFetch<ConfigAvisos>("/api/config", {
    method: "PUT",
    body: JSON.stringify(partial),
  });
  try {
    localStorage.setItem(LS_KEYS.config, JSON.stringify(data));
  } catch {
    // ignore
  }
  return data;
}

export async function predictBlocos(
  draft: PreparoDraft,
  metaLitrosPadrao?: number
): Promise<PredictResponse> {
  const payload = buildPayloadFromDraft(draft);
  return await apiFetch<PredictResponse>("/api/stats/predict", {
    method: "POST",
    body: JSON.stringify({
      data: payload.data,
      blocos: payload.blocos,
      metaLitrosPadrao,
    }),
  });
}

export async function fetchStatsSummary(): Promise<StatsSummary> {
  return await apiFetch<StatsSummary>("/api/stats/summary");
}

export async function fetchPesosPanelas(): Promise<PesoSugestao[]> {
  return await apiFetch<PesoSugestao[]>("/api/stats/pesos-panelas");
}
