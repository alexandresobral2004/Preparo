import { describe, expect, it } from "vitest";
import type { BlocoDraft, PreparoDraft } from "../types";
import { createEmptyBloco, createEmptyPreparo } from "./calc";
import { descreverAutoria, mesclarRespostaDoRascunho, validarNovaSenha } from "./auth";

describe("validarNovaSenha", () => {
  it("exige 8 caracteres e confirmação igual", () => {
    expect(validarNovaSenha("curta", "curta")).toMatch(/8 caracteres/);
    expect(validarNovaSenha("senha-longa-1", "senha-longa-2")).toMatch(/não conferem/);
    expect(validarNovaSenha("senha-longa-1", "senha-longa-1")).toBeNull();
  });
});

describe("descreverAutoria", () => {
  const hora = (h: number, m: number) => new Date(2026, 10, 22, h, m).toISOString();

  it("mostra só quem criou quando ninguém editou", () => {
    expect(
      descreverAutoria({ criadoPorId: 1, criadoPorNome: "Maria", criadoEm: hora(18, 5) })
    ).toBe("Criado por Maria às 18:05");
  });

  it("mostra criação e última edição", () => {
    expect(
      descreverAutoria({
        criadoPorId: 1,
        criadoPorNome: "Maria",
        criadoEm: hora(18, 5),
        editadoPorId: 2,
        editadoPorNome: "João",
        editadoEm: hora(19, 40),
      })
    ).toBe("Criado por Maria às 18:05 · editado por João às 19:40");
  });

  it("não mostra nada sem autoria (registros antigos e importados)", () => {
    expect(descreverAutoria(null)).toBe("");
    expect(descreverAutoria(undefined)).toBe("");
  });
});

describe("mesclarRespostaDoRascunho", () => {
  const autoria = { criadoPorId: 1, criadoPorNome: "Maria", criadoEm: "t1" };

  it("copia só autoria e versão do servidor e preserva o que a pessoa digitou depois", () => {
    const local: PreparoDraft = {
      ...createEmptyPreparo(),
      mestre: "digitado depois do envio",
      blocos: [{ ...createEmptyBloco(1), obs: "texto novo" }, createEmptyBloco(6)],
    };
    const doServidor: PreparoDraft = {
      ...createEmptyPreparo(),
      _versao: 4,
      mestre: "valor antigo do servidor",
      blocos: [{ ...createEmptyBloco(1), obs: "texto velho", autoria }] as BlocoDraft[],
    };
    const mesclado = mesclarRespostaDoRascunho(local, doServidor);
    expect(mesclado._versao).toBe(4);
    expect(mesclado.mestre).toBe("digitado depois do envio");
    expect(mesclado.blocos[0].obs).toBe("texto novo");
    expect(mesclado.blocos[0].autoria).toEqual(autoria);
    expect(mesclado.blocos[1].autoria).toBeUndefined(); // bloco que o servidor ainda não conhece
  });

  it("devolve o mesmo objeto quando nada mudou (evita novo envio à toa)", () => {
    const local: PreparoDraft = { ...createEmptyPreparo(), _versao: 2, blocos: [{ ...createEmptyBloco(1), autoria }] };
    expect(mesclarRespostaDoRascunho(local, { ...local })).toBe(local);
  });
});
