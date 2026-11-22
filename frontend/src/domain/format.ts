import { TIPOS_PANELA, type TipoPanela } from "../types";

export function todayIsoLocal(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function nowHhmmLocal(): string {
  const d = new Date();
  const h = String(d.getHours()).padStart(2, "0");
  const m = String(d.getMinutes()).padStart(2, "0");
  return `${h}:${m}`;
}

export function formatDateBr(isoDate: string): string {
  if (!isoDate) return "sem data";
  const parts = isoDate.split("-");
  if (parts.length !== 3) return isoDate;
  return `${parts[2]}/${parts[1]}/${parts[0]}`;
}

export function normalizarTipo(raw: unknown): TipoPanela | "" {
  if (raw == null) return "";
  const text = String(raw).trim();
  if (!text) return "";

  const norm = text
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[ºª°]/g, "a")
    .replace(/\s+/g, " ")
    .trim();

  if (["1", "1a", "1a vez", "1 vez", "1vez", "primeira", "primeira vez"].includes(norm)) {
    return "1ª vez";
  }
  if (["2", "2a", "2a vez", "2 vez", "2vez", "segunda", "segunda vez"].includes(norm)) {
    return "2ª vez";
  }
  if (["3", "3a", "3a vez", "3 vez", "3vez", "terceira", "terceira vez"].includes(norm)) {
    return "3ª vez";
  }
  if (norm.includes("apuro") || norm.includes("apurac")) {
    return "APURO";
  }
  if (norm.startsWith("1")) return "1ª vez";
  if (norm.startsWith("2")) return "2ª vez";
  if (norm.startsWith("3")) return "3ª vez";

  return "";
}

export interface DecimalParseResult {
  valid: boolean;
  value: number | null;
}

export function parseDecimalPtBr(raw: string | number | null | undefined): DecimalParseResult {
  if (raw === null || raw === undefined) {
    return { valid: true, value: null };
  }
  if (typeof raw === "number") {
    if (!Number.isFinite(raw)) return { valid: false, value: null };
    return { valid: true, value: raw };
  }
  let s = raw.trim();
  if (!s) return { valid: true, value: null };

  if (s.includes(",") && s.includes(".")) {
    if (s.lastIndexOf(",") > s.lastIndexOf(".")) {
      s = s.replace(/\./g, "").replace(",", ".");
    } else {
      s = s.replace(/,/g, "");
    }
  } else if (s.includes(",")) {
    s = s.replace(",", ".");
  }

  if (!/^[+-]?(\d+(\.\d+)?|\.\d+)$/.test(s)) {
    return { valid: false, value: null };
  }
  const num = Number(s);
  if (!Number.isFinite(num)) {
    return { valid: false, value: null };
  }
  return { valid: true, value: num };
}

export function tryParseDecimal(raw: string | number | null | undefined): number | null {
  const res = parseDecimalPtBr(raw);
  return res.valid ? res.value : null;
}

export function formatPtBr(num: number | null | undefined, maxDecimals = 2): string {
  if (num === null || num === undefined || !Number.isFinite(num)) return "—";
  return num.toLocaleString("pt-BR", {
    minimumFractionDigits: 0,
    maximumFractionDigits: maxDecimals,
  });
}

export function formatDecimalInput(num: number | null | undefined): string {
  if (num === null || num === undefined || !Number.isFinite(num)) return "";
  return String(num).replace(".", ",");
}

export function formatDurationMin(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || !Number.isFinite(minutes)) return "—";
  const rounded = Math.max(0, Math.round(minutes));
  const h = Math.floor(rounded / 60);
  const m = rounded % 60;
  if (h === 0) return `${m}min`;
  return `${h}h ${String(m).padStart(2, "0")}min`;
}

export function createEmptyPorTipo(): Record<TipoPanela, number> {
  return {
    [TIPOS_PANELA[0]]: 0,
    [TIPOS_PANELA[1]]: 0,
    [TIPOS_PANELA[2]]: 0,
    [TIPOS_PANELA[3]]: 0,
  };
}
