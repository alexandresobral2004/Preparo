import { afterEach, describe, expect, it, vi } from "vitest";
import {
  addMinutes,
  avaliarProporcaoChacrona,
  buildPayloadFromDraft,
  calcularMetricasBloco,
  calcularTotaisPorTipo,
  createEmptyBloco,
  createEmptyPreparo,
  diffMinutes,
  draftFromSavedRegistro,
  estadoPanela,
  estadoPassaFiltro,
  multiplyByPiExact,
  avaliarPesos,
} from "./calc";
import { normalizarTipo, parseDecimalPtBr } from "./format";

describe("Domínio e Calculadora π do frontend", () => {
  it("normaliza variações da v1 para exatamente 4 categorias", () => {
    expect(normalizarTipo("1")).toBe("1ª vez");
    expect(normalizarTipo("2ª")).toBe("2ª vez");
    expect(normalizarTipo("3a vez")).toBe("3ª vez");
    expect(normalizarTipo("apuro")).toBe("APURO");
    expect(normalizarTipo("Água")).toBe("");
  });

  it("calcula virada de meia-noite e métricas do bloco", () => {
    expect(diffMinutes("22:30", "01:45")).toBe(195);
    expect(addMinutes("23:10", 110)).toBe("01:00");

    const bloco = createEmptyBloco(1);
    bloco.panelas[0] = {
      ...bloco.panelas[0],
      tipo: "1ª vez",
      entrada: "21:00",
      fervura: "21:30",
      colhida: "01:00",
      litros: "12,5",
    };
    bloco.panelas[1] = {
      ...bloco.panelas[1],
      tipo: "APURO",
      entrada: "22:00",
      fervura: "22:30",
      colhida: "02:30",
      litros: "10,0",
    };

    const met = calcularMetricasBloco(bloco);
    expect(met.totalLitros).toBeCloseTo(22.5, 2);
    expect(met.duracaoMin).toBe(330);
    expect(met.tempoMedioMin).toBeCloseTo(255, 1);
    expect(met.litrosPorHora).toBeCloseTo(4.09, 1);

    const totais = calcularTotaisPorTipo([bloco]);
    expect(totais.totalGeral).toBeCloseTo(22.5, 2);
    expect(totais.porTipo["1ª vez"]).toBeCloseTo(12.5, 2);
    expect(totais.porTipo.APURO).toBeCloseTo(10.0, 2);
  });

  it("abre registros salvos com litros já travados", () => {
    const draft = draftFromSavedRegistro({
      id: "r1",
      salvoEm: "2026-11-22T10:00:00Z",
      nucleo: "Bendito Filho",
      data: "2026-11-22",
      mestre: "João",
      auxiliar: "",
      respMariri: "",
      respChacrona: "",
      respChacrona2: "",
      mariri: "",
      maririKg: null,
      chacrona: [],
      obsGeral: "",
      chacronaTotalKg: 0,
      totalLitros: 10.15,
      totaisPorTipo: { "1ª vez": 10.15, "2ª vez": 0, "3ª vez": 0, APURO: 0 },
      blocos: [
        {
          obs: "",
          anotador: "",
          data: "",
          panelas: [
            {
              numero: 1,
              tipo: "1ª vez",
              entrada: "08:00",
              fervura: "08:30",
              colhida: "12:00",
              litros: 10.15,
              pesoSecaKg: 12,
              pesoCheiaKg: 35,
              metaLitros: null,
            },
          ],
        },
      ],
    });
    expect(draft.blocos[0].panelas[0].litros).toBe("10,15");
    expect(draft.blocos[0].panelas[0].litrosLocked).toBe(true);
    expect(estadoPanela(draft.blocos[0].panelas[0])).toBe("colhida");
  });

  it("calcula multiplicação por π com precisão de até 15 casas decimais usando BigInt", () => {
    const r4 = multiplyByPiExact("10", 4);
    expect(r4).toEqual({ ok: true, formatted: "31,4159" });

    const r15 = multiplyByPiExact("1", 15);
    expect(r15).toEqual({ ok: true, formatted: "3,141592653589793" });

    const rComma = multiplyByPiExact("2,5", 6);
    expect(rComma).toEqual({ ok: true, formatted: "7,853982" });

    const rBad = multiplyByPiExact("12abc", 4);
    expect(rBad.ok).toBe(false);
    expect(parseDecimalPtBr("10,15")).toEqual({ valid: true, value: 10.15 });
  });

  it("usa o peso seca/cheia do cabeçalho em todas as panelas do payload", () => {
    const draft = {
      ...createEmptyPreparo(),
      pesoSecaKg: "12,5",
      pesoCheiaKg: "38",
      blocos: [createEmptyBloco(1), createEmptyBloco(6)],
    };
    const payload = buildPayloadFromDraft(draft);
    const panelas = payload.blocos.flatMap((b) => b.panelas);
    expect(panelas).toHaveLength(10);
    for (const p of panelas) {
      expect(p.pesoSecaKg).toBe(12.5);
      expect(p.pesoCheiaKg).toBe(38);
    }
  });

  it("sugere chacrona na proporção ~10:1 e só alerta quando o total foge dela", () => {
    expect(avaliarProporcaoChacrona("300", 0)).toEqual({ esperadoKg: 30, foraDaProporcao: false });
    expect(avaliarProporcaoChacrona("300", 28)).toEqual({ esperadoKg: 30, foraDaProporcao: false });
    expect(avaliarProporcaoChacrona("300", 36)).toEqual({ esperadoKg: 30, foraDaProporcao: false });
    expect(avaliarProporcaoChacrona("300", 60)).toEqual({ esperadoKg: 30, foraDaProporcao: true });
    expect(avaliarProporcaoChacrona("300", 10)).toEqual({ esperadoKg: 30, foraDaProporcao: true });
    expect(avaliarProporcaoChacrona("120,5", 12)).toEqual({ esperadoKg: 12.05, foraDaProporcao: false });
    expect(avaliarProporcaoChacrona("", 30)).toBeNull();
    expect(avaliarProporcaoChacrona("0", 30)).toBeNull();
    expect(avaliarProporcaoChacrona("abc", 30)).toBeNull();
  });

  it("leva o anotador de cada bloco ao payload e de volta ao reabrir o registro", () => {
    const b1 = { ...createEmptyBloco(1), anotador: "  Maria " };
    const b2 = createEmptyBloco(6);
    const payload = buildPayloadFromDraft({ ...createEmptyPreparo(), blocos: [b1, b2] });
    expect(payload.blocos.map((b) => b.anotador)).toEqual(["Maria", ""]);

    const reaberto = draftFromSavedRegistro({
      ...createEmptyPreparo(),
      id: "r1",
      salvoEm: "2026-11-22T10:00:00Z",
      maririKg: null,
      chacrona: [],
      blocos: payload.blocos.map((b) => ({ ...b, panelas: [] })),
      chacronaTotalKg: 0,
      totalLitros: 0,
      totaisPorTipo: { "1ª vez": 0, "2ª vez": 0, "3ª vez": 0, APURO: 0 },
    } as never);
    expect(reaberto.blocos.map((b) => b.anotador)).toEqual(["Maria", ""]);
  });

  it("filtro do andamento: Todas, No fogo (inclui fervendo) e Colhidas", () => {
    expect(estadoPassaFiltro("colhida", "todas")).toBe(true);
    expect(estadoPassaFiltro("no_fogo", "no_fogo")).toBe(true);
    expect(estadoPassaFiltro("fervendo", "no_fogo")).toBe(true);
    expect(estadoPassaFiltro("colhida", "no_fogo")).toBe(false);
    expect(estadoPassaFiltro("colhida", "colhida")).toBe(true);
    expect(estadoPassaFiltro("fervendo", "colhida")).toBe(false);
    expect(estadoPassaFiltro("sem_entrada", "colhida")).toBe(false);
  });

  describe("data do bloco", () => {
    afterEach(() => vi.useRealTimers());

    it("novo bloco já nasce com a data de hoje e ela segue no payload", () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date(2026, 10, 22, 23, 50)); // 22/11/2026 23:50 local
      const bloco = createEmptyBloco(1);
      expect(bloco.data).toBe("2026-11-22");

      vi.setSystemTime(new Date(2026, 10, 23, 0, 10)); // virou o dia: bloco novo = novo dia
      const proximo = createEmptyBloco(6);
      expect(proximo.data).toBe("2026-11-23");

      const payload = buildPayloadFromDraft({
        ...createEmptyPreparo(),
        blocos: [bloco, proximo],
      });
      expect(payload.blocos.map((b) => b.data)).toEqual(["2026-11-22", "2026-11-23"]);
    });

    it("registro antigo sem data no bloco usa a data do preparo", () => {
      const reaberto = draftFromSavedRegistro({
        ...createEmptyPreparo(),
        id: "r1",
        salvoEm: "2026-11-20T10:00:00Z",
        data: "2026-11-20",
        maririKg: null,
        chacrona: [],
        blocos: [{ obs: "", anotador: "", panelas: [] }],
        chacronaTotalKg: 0,
        totalLitros: 0,
        totaisPorTipo: { "1ª vez": 0, "2ª vez": 0, "3ª vez": 0, APURO: 0 },
      } as never);
      expect(reaberto.blocos[0].data).toBe("2026-11-20");
    });
  });

  it("o peso com água do cabeçalho vai para todas as panelas do payload e volta ao reabrir o registro", () => {
    const draft = {
      ...createEmptyPreparo(),
      pesoSecaKg: "12,5",
      pesoCheiaKg: "38",
      pesoComAguaKg: "58,5",
      blocos: [createEmptyBloco(1), createEmptyBloco(6)],
    };
    const payload = buildPayloadFromDraft(draft);
    const panelas = payload.blocos.flatMap((b) => b.panelas);
    expect(panelas).toHaveLength(10);
    for (const p of panelas) expect(p.pesoComAguaKg).toBe(58.5);

    const semAgua = buildPayloadFromDraft({ ...draft, pesoComAguaKg: "" });
    expect(semAgua.blocos[0].panelas[0].pesoComAguaKg).toBeNull(); // vazio não vira 0

    const reaberto = draftFromSavedRegistro({
      ...createEmptyPreparo(),
      id: "r1",
      salvoEm: "2026-11-22T10:00:00Z",
      maririKg: null,
      chacrona: [],
      blocos: payload.blocos.map((b) => ({ ...b, anotador: "", data: "", panelas: b.panelas })),
      chacronaTotalKg: 0,
      totalLitros: 0,
      totaisPorTipo: { "1ª vez": 0, "2ª vez": 0, "3ª vez": 0, APURO: 0 },
    } as never);
    expect(reaberto.pesoComAguaKg).toBe("58,5");
  });
});

describe("avaliarPesos", () => {
  const base = { pesoSecaKg: "12,5", pesoCheiaKg: "38", pesoComAguaKg: "58,5" };

  it("deriva o peso do mariri + chacrona (b − a) e a água (c − b)", () => {
    expect(avaliarPesos(base)).toEqual({ material: 25.5, agua: 20.5, materialInvalido: false, aguaInvalida: false });
  });

  it("sem o peso com água informado não há água, e isso não é erro", () => {
    const r = avaliarPesos({ ...base, pesoComAguaKg: "" });
    expect(r.agua).toBeNull();
    expect(r.aguaInvalida).toBe(false);
  });

  it("c menor ou igual a b é inválido; b menor ou igual a a também", () => {
    expect(avaliarPesos({ ...base, pesoComAguaKg: "38" }).aguaInvalida).toBe(true);
    expect(avaliarPesos({ ...base, pesoCheiaKg: "12" }).materialInvalido).toBe(true);
  });
});
