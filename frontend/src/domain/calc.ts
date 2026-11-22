import {
  TIPOS_PANELA,
  type BlocoDraft,
  type BlocoMetricas,
  type PanelaAlertas,
  type PanelaDraft,
  type PanelaEstado,
  type PreparoDraft,
  type RegistroSaved,
  type TipoPanela,
} from "../types";
import {
  createEmptyPorTipo,
  formatDecimalInput,
  normalizarTipo,
  todayIsoLocal,
  tryParseDecimal,
} from "./format";

const TIME_RE = /^([01]?\d|2[0-3]):([0-5]\d)$/;

export function parseHhmm(hhmm: string | null | undefined): number | null {
  if (!hhmm) return null;
  const s = hhmm.trim();
  const m = TIME_RE.exec(s);
  if (!m) return null;
  return Number(m[1]) * 60 + Number(m[2]);
}

export function formatHhmm(minutes: number): string {
  const m = ((Math.round(minutes) % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

export function diffMinutes(startHhmm: string, endHhmm: string): number | null {
  const s = parseHhmm(startHhmm);
  const e = parseHhmm(endHhmm);
  if (s === null || e === null) return null;
  let delta = e - s;
  if (delta < 0) delta += 1440;
  return delta;
}

export function addMinutes(hhmm: string, deltaMin: number): string | null {
  const s = parseHhmm(hhmm);
  if (s === null) return null;
  return formatHhmm(s + Math.round(deltaMin));
}

export function estadoPanela(panela: PanelaDraft): PanelaEstado {
  const tipo = normalizarTipo(panela.tipo);
  const entrada = panela.entrada.trim();
  const fervura = panela.fervura.trim();
  const colhida = panela.colhida.trim();
  const litros = tryParseDecimal(panela.litros);

  const hasAny =
    Boolean(tipo) ||
    Boolean(entrada) ||
    Boolean(fervura) ||
    Boolean(colhida) ||
    litros !== null;

  if (!hasAny) return "vazia";
  if (colhida) return "colhida";
  if (entrada && fervura) return "fervendo";
  if (entrada) return "no_fogo";
  return "sem_entrada";
}

export type FiltroAndamento = "todas" | "no_fogo" | "colhida";

export function estadoPassaFiltro(estado: PanelaEstado, filtro: FiltroAndamento): boolean {
  if (filtro === "no_fogo") return estado === "no_fogo" || estado === "fervendo";
  if (filtro === "colhida") return estado === "colhida";
  return true;
}

function toIsoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
}

export function calcularNoFogoHa(
  entrada: string,
  dataPreparo: string,
  now: Date = new Date()
): number | null {
  const entMin = parseHhmm(entrada);
  if (entMin === null || !dataPreparo) return null;

  const todayStr = toIsoDate(now);
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayStr = toIsoDate(yesterday);

  const nowMin = now.getHours() * 60 + now.getMinutes();

  if (dataPreparo === todayStr) {
    const delta = nowMin - entMin;
    return delta >= 0 && delta <= 16 * 60 ? delta : null;
  }
  if (dataPreparo === yesterdayStr && nowMin < entMin) {
    const delta = nowMin + 1440 - entMin;
    return delta >= 0 && delta <= 16 * 60 ? delta : null;
  }
  return null;
}

export function validarPanelaLocal(
  panela: PanelaDraft,
  dataPreparo: string,
  minSemFervura = 30,
  horasSemColheita = 5,
  now: Date = new Date()
): PanelaAlertas {
  const estado = estadoPanela(panela);
  if (estado === "vazia") return { faltando: [], conferir: [] };

  const tipo = normalizarTipo(panela.tipo);
  const entrada = panela.entrada.trim();
  const fervura = panela.fervura.trim();
  const colhida = panela.colhida.trim();
  const litros = tryParseDecimal(panela.litros);

  const faltando: string[] = [];
  const conferir: string[] = [];

  if (!tipo) faltando.push("Panela sem tipo informado");
  if ((fervura || colhida || litros !== null) && !entrada) {
    faltando.push("Horário de entrada faltando");
  }
  if ((colhida || litros !== null) && !fervura) {
    faltando.push("Horário de fervura faltando");
  }
  if (litros !== null && !colhida) {
    faltando.push("Horário de colheita faltando");
  }
  if (colhida && litros === null) {
    faltando.push("Litros colhidos não informados");
  }
  if (entrada && !colhida) {
    const noFogoMin = calcularNoFogoHa(entrada, dataPreparo, now);
    if (noFogoMin !== null) {
      if (!fervura && noFogoMin >= minSemFervura) {
        conferir.push(`Sem fervura após ${minSemFervura} min da entrada`);
      }
      if (noFogoMin >= Math.round(horasSemColheita * 60)) {
        const horasTxt = Number.isInteger(horasSemColheita)
          ? String(horasSemColheita)
          : String(horasSemColheita).replace(".", ",");
        conferir.push(`Sem colheita após ${horasTxt} h da entrada`);
      }
    }
  }

  return { faltando, conferir };
}

export function calcularMetricasBloco(bloco: BlocoDraft): BlocoMetricas {
  let totalLitros = 0;
  const tempos: number[] = [];
  const entradas: number[] = [];

  for (const p of bloco.panelas) {
    const ent = parseHhmm(p.entrada);
    if (ent !== null) entradas.push(ent);
  }

  let anchor: number | null = null;
  let crossMidnightEntries = false;
  if (entradas.length > 0) {
    const maxEnt = Math.max(...entradas);
    const minEnt = Math.min(...entradas);
    if (maxEnt - minEnt > 720) {
      crossMidnightEntries = true;
      const evening = entradas.filter((e) => e >= 720);
      anchor = evening.length > 0 ? Math.min(...evening) : minEnt;
    } else {
      anchor = minEnt;
    }
  }

  const colhidasRel: number[] = [];

  for (const p of bloco.panelas) {
    const litros = tryParseDecimal(p.litros);
    if (litros !== null && litros > 0) {
      totalLitros += litros;
    }
    const ent = parseHhmm(p.entrada);
    const col = parseHhmm(p.colhida);
    if (ent !== null && col !== null) {
      const dur = diffMinutes(p.entrada, p.colhida);
      if (dur !== null) tempos.push(dur);
    }
    if (anchor !== null && col !== null) {
      if (ent !== null) {
        const entRel = ent >= anchor ? ent - anchor : ent - anchor + 1440;
        const panDur = diffMinutes(p.entrada, p.colhida) ?? 0;
        colhidasRel.push(entRel + panDur);
      } else {
        let colRel = col >= anchor ? col - anchor : col - anchor + 1440;
        if (crossMidnightEntries && col < 720 && anchor >= 720) {
          colRel = col - anchor + 1440;
        }
        colhidasRel.push(colRel);
      }
    }
  }

  const duracaoMin = colhidasRel.length > 0 ? Math.max(...colhidasRel) : null;
  const tempoMedioMin =
    tempos.length > 0 ? tempos.reduce((acc, v) => acc + v, 0) / tempos.length : null;

  let litrosPorHora: number | null = null;
  let minPorLitro: number | null = null;
  if (totalLitros > 0 && duracaoMin !== null && duracaoMin > 0) {
    litrosPorHora = totalLitros / (duracaoMin / 60);
    minPorLitro = duracaoMin / totalLitros;
  }

  return {
    totalLitros: Math.round(totalLitros * 100) / 100,
    tempoMedioMin: tempoMedioMin !== null ? Math.round(tempoMedioMin * 10) / 10 : null,
    duracaoMin,
    litrosPorHora: litrosPorHora !== null ? Math.round(litrosPorHora * 100) / 100 : null,
    minPorLitro: minPorLitro !== null ? Math.round(minPorLitro * 100) / 100 : null,
  };
}

export function calcularTotaisPorTipo(blocos: BlocoDraft[]): {
  totalGeral: number;
  porTipo: Record<TipoPanela, number>;
} {
  const porTipo = createEmptyPorTipo();
  let totalGeral = 0;

  for (const bloco of blocos) {
    for (const p of bloco.panelas) {
      const litros = tryParseDecimal(p.litros);
      if (litros === null || litros <= 0) continue;
      totalGeral += litros;
      const tipo = normalizarTipo(p.tipo);
      if (tipo && tipo in porTipo) {
        porTipo[tipo] += litros;
      }
    }
  }

  return {
    totalGeral: Math.round(totalGeral * 100) / 100,
    porTipo: {
      [TIPOS_PANELA[0]]: Math.round(porTipo[TIPOS_PANELA[0]] * 100) / 100,
      [TIPOS_PANELA[1]]: Math.round(porTipo[TIPOS_PANELA[1]] * 100) / 100,
      [TIPOS_PANELA[2]]: Math.round(porTipo[TIPOS_PANELA[2]] * 100) / 100,
      [TIPOS_PANELA[3]]: Math.round(porTipo[TIPOS_PANELA[3]] * 100) / 100,
    },
  };
}

// π com 25 casas decimais para cálculo exato com BigInt até 15 casas (RF-26/RF-27)
const PI_SCALE = 25;
const PI_SCALED = 31415926535897932384626433n;

export type CalcPiResult =
  | { ok: true; formatted: string }
  | { ok: false; empty?: boolean; error?: string };

export function multiplyByPiExact(rawInput: string, decimals: number): CalcPiResult {
  const trimmed = rawInput.trim();
  if (!trimmed) {
    return { ok: false, empty: true };
  }

  let normalized = trimmed;
  if (normalized.includes(",") && normalized.includes(".")) {
    if (normalized.lastIndexOf(",") > normalized.lastIndexOf(".")) {
      normalized = normalized.replace(/\./g, "").replace(",", ".");
    } else {
      normalized = normalized.replace(/,/g, "");
    }
  } else if (normalized.includes(",")) {
    normalized = normalized.replace(",", ".");
  }

  if (!/^[+-]?(\d+(\.\d+)?|\.\d+)$/.test(normalized)) {
    return {
      ok: false,
      error: "Digite apenas um número válido (use vírgula ou ponto para decimais).",
    };
  }

  const sign = normalized.startsWith("-") ? "-" : "";
  const unsigned = normalized.replace(/^[+-]/, "");
  const [intPartRaw, fracPartRaw = ""] = unsigned.split(".");
  const intPart = intPartRaw || "0";
  const fracLen = fracPartRaw.length;
  const inputBig = BigInt(intPart + fracPartRaw);

  if (inputBig === 0n) {
    return { ok: true, formatted: `0,${"0".repeat(decimals)}` };
  }

  const product = inputBig * PI_SCALED;
  const totalFracDigits = fracLen + PI_SCALE;

  let roundedScaled: bigint;
  if (totalFracDigits > decimals) {
    const drop = totalFracDigits - decimals;
    const divisor = 10n ** BigInt(drop);
    const q = product / divisor;
    const rem = product % divisor;
    roundedScaled = rem * 2n >= divisor ? q + 1n : q;
  } else {
    roundedScaled = product * 10n ** BigInt(decimals - totalFracDigits);
  }

  const scaleFactor = 10n ** BigInt(decimals);
  const resInt = roundedScaled / scaleFactor;
  const resFrac = roundedScaled % scaleFactor;

  const fracStr = resFrac.toString().padStart(decimals, "0");
  return {
    ok: true,
    formatted: `${sign}${resInt.toString()},${fracStr}`,
  };
}

export function createEmptyBloco(startNumber: number, anotador = ""): BlocoDraft {
  return {
    obs: "",
    anotador,
    data: todayIsoLocal(),
    panelas: Array.from({ length: 5 }, (_, idx) => ({
      numero: startNumber + idx,
      tipo: "",
      entrada: "",
      fervura: "",
      colhida: "",
      litros: "",
      litrosLocked: false,
    })),
  };
}

export function createEmptyPreparo(anotador = ""): PreparoDraft {
  return {
    nucleo: "Bendito Filho",
    data: todayIsoLocal(),
    mestre: "",
    auxiliar: "",
    respMariri: "",
    respChacrona: "",
    respChacrona2: "",
    mariri: "",
    maririKg: "",
    pesoSecaKg: "",
    pesoCheiaKg: "",
    pesoComAguaKg: "",
    chacrona: [
      { nucleo: "", kg: "" },
      { nucleo: "", kg: "" },
    ],
    obsGeral: "",
    blocos: [createEmptyBloco(1, anotador)],
  };
}

export function draftFromSavedRegistro(reg: RegistroSaved): PreparoDraft {
  const chacrona =
    reg.chacrona.length > 0
      ? reg.chacrona.map((c) => ({
          nucleo: c.nucleo,
          kg: formatDecimalInput(c.kg),
        }))
      : [
          { nucleo: "", kg: "" },
          { nucleo: "", kg: "" },
        ];

  const blocos: BlocoDraft[] =
    reg.blocos.length > 0
      ? reg.blocos.map((b, bIdx) => ({
          obs: b.obs,
          anotador: b.anotador || "",
          data: b.data || reg.data || "",
          panelas: b.panelas.map((p, pIdx) => {
            const litrosStr = formatDecimalInput(p.litros);
            return {
              numero: p.numero || bIdx * 5 + pIdx + 1,
              tipo: normalizarTipo(p.tipo),
              entrada: p.entrada || "",
              fervura: p.fervura || "",
              colhida: p.colhida || "",
              litros: litrosStr,
              litrosLocked: litrosStr !== "",
              metaLitros: formatDecimalInput(p.metaLitros),
            };
          }),
        }))
      : [createEmptyBloco(1)];

  return {
    id: reg.id,
    salvoEm: reg.salvoEm,
    nucleo: reg.nucleo || "Bendito Filho",
    data: reg.data || "",
    mestre: reg.mestre || "",
    auxiliar: reg.auxiliar || "",
    respMariri: reg.respMariri || "",
    respChacrona: reg.respChacrona || "",
    respChacrona2: reg.respChacrona2 || "",
    mariri: reg.mariri || "",
    maririKg: formatDecimalInput(reg.maririKg),
    // Registros antigos guardavam o peso por panela; as panelas são iguais, então usa a primeira com peso.
    pesoSecaKg: formatDecimalInput(pesoPrimeiraPanela(reg, "pesoSecaKg")),
    pesoCheiaKg: formatDecimalInput(pesoPrimeiraPanela(reg, "pesoCheiaKg")),
    pesoComAguaKg: formatDecimalInput(pesoPrimeiraPanela(reg, "pesoComAguaKg")),
    chacrona,
    obsGeral: reg.obsGeral || "",
    blocos,
  };
}

function pesoPrimeiraPanela(
  reg: RegistroSaved,
  campo: "pesoSecaKg" | "pesoCheiaKg" | "pesoComAguaKg"
): number | null {
  for (const bloco of reg.blocos) {
    for (const p of bloco.panelas) {
      if (p[campo] != null) return p[campo] ?? null;
    }
  }
  return null;
}

/**
 * Os três pesos do preparo (iguais para todas as panelas):
 * a) panela vazia, b) panela + mariri + chacrona, c) panela + mariri + chacrona + água.
 * Derivados: material = b − a; água = c − b (1 kg ≈ 1 L). Campo em branco não vira 0.
 */
export function avaliarPesos(
  draft: Pick<PreparoDraft, "pesoSecaKg" | "pesoCheiaKg" | "pesoComAguaKg">
): { material: number | null; agua: number | null; materialInvalido: boolean; aguaInvalida: boolean } {
  const a = tryParseDecimal(draft.pesoSecaKg);
  const b = tryParseDecimal(draft.pesoCheiaKg);
  const c = tryParseDecimal(draft.pesoComAguaKg);
  const material = a !== null && b !== null ? b - a : null;
  const agua = b !== null && c !== null ? c - b : null;
  return {
    material,
    agua,
    materialInvalido: material !== null && material <= 0,
    aguaInvalida: agua !== null && agua <= 0,
  };
}

// Colhe-se cerca de 10 kg de mariri para 1 kg de chacrona (aproximado, nunca exato).
const MARIRI_POR_CHACRONA = 10;
const TOLERANCIA_PROPORCAO = 0.3;

export function avaliarProporcaoChacrona(
  maririKg: string,
  totalChacronaKg: number
): { esperadoKg: number; foraDaProporcao: boolean } | null {
  const mariri = tryParseDecimal(maririKg);
  if (mariri === null || mariri <= 0) return null;
  const esperadoKg = mariri / MARIRI_POR_CHACRONA;
  const foraDaProporcao =
    totalChacronaKg > 0 &&
    Math.abs(totalChacronaKg - esperadoKg) > esperadoKg * TOLERANCIA_PROPORCAO;
  return { esperadoKg, foraDaProporcao };
}

export function buildPayloadFromDraft(draft: PreparoDraft) {
  // Os pesos são únicos do preparo (cabeçalho); o backend ainda recebe um valor por panela.
  const pesoSecaKg = tryParseDecimal(draft.pesoSecaKg);
  const pesoCheiaKg = tryParseDecimal(draft.pesoCheiaKg);
  const pesoComAguaKg = tryParseDecimal(draft.pesoComAguaKg);
  return {
    id: draft.id,
    salvoEm: draft.salvoEm,
    nucleo: draft.nucleo.trim() || "Bendito Filho",
    data: draft.data.trim(),
    mestre: draft.mestre.trim(),
    auxiliar: draft.auxiliar.trim(),
    respMariri: draft.respMariri.trim(),
    respChacrona: draft.respChacrona.trim(),
    respChacrona2: draft.respChacrona2.trim(),
    mariri: draft.mariri.trim(),
    maririKg: tryParseDecimal(draft.maririKg),
    chacrona: draft.chacrona.map((c) => ({
      nucleo: c.nucleo.trim(),
      kg: tryParseDecimal(c.kg),
    })),
    obsGeral: draft.obsGeral.trim(),
    blocos: draft.blocos.map((b, bIdx) => ({
      obs: b.obs.trim(),
      anotador: b.anotador.trim(),
      data: b.data,
      panelas: b.panelas.map((p, pIdx) => ({
        numero: p.numero || bIdx * 5 + pIdx + 1,
        tipo: normalizarTipo(p.tipo),
        entrada: p.entrada.trim(),
        fervura: p.fervura.trim(),
        colhida: p.colhida.trim(),
        litros: tryParseDecimal(p.litros),
        pesoSecaKg,
        pesoCheiaKg,
        pesoComAguaKg,
        metaLitros: tryParseDecimal(p.metaLitros),
      })),
    })),
  };
}
