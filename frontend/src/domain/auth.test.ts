import { describe, expect, it } from "vitest";
import type { BlocoDraft, PreparoDraft } from "../types";
import { createEmptyBloco, createEmptyPreparo } from "./calc";
import type { Usuario } from "../types";
import {
  descreverAutoria,
  filtrarPorSituacao,
  mesclarRespostaDoRascunho,
  ordenarUsuarios,
  rotuloGrau,
  validarLogin,
  validarNovaSenha,
} from "./auth";

const usuario = (id: number, nome: string, situacao: Usuario["situacao"]): Usuario => ({
  id,
  login: `login${id}`,
  nome,
  papel: "usuario",
  situacao,
  grau: "",
  nucleo: "",
});

describe("rotuloGrau", () => {
  it("devolve o rótulo de cada grau da lista fixa", () => {
    expect(rotuloGrau("socio")).toBe("Quadro de Sócios");
    expect(rotuloGrau("instrutivo")).toBe("Corpo Instrutivo");
    expect(rotuloGrau("conselho")).toBe("Corpo do Conselho");
    expect(rotuloGrau("mestre")).toBe("Quadro de Mestres");
  });

  it("mostra 'Não informado' para usuário antigo (vazio) e para valor desconhecido", () => {
    expect(rotuloGrau("")).toBe("Não informado");
    expect(rotuloGrau("aprendiz")).toBe("Não informado");
  });
});

describe("ordenarUsuarios", () => {
  it("põe os pendentes primeiro e depois ordena por nome sem diferenciar acento nem caixa", () => {
    const lista = [
      usuario(1, "Zé", "ativo"),
      usuario(2, "Bruno", "pendente"),
      usuario(3, "álvaro", "ativo"),
      usuario(4, "Ana", "ativo"),
    ];
    const ordenada = ordenarUsuarios(lista).map((u) => u.nome);
    expect(ordenada).toEqual(["Bruno", "álvaro", "Ana", "Zé"]);
  });

  it("não altera a lista original", () => {
    const lista = [usuario(1, "Zé", "ativo"), usuario(2, "Ana", "pendente")];
    ordenarUsuarios(lista);
    expect(lista.map((u) => u.nome)).toEqual(["Zé", "Ana"]);
  });
});

describe("filtrarPorSituacao", () => {
  const lista = [
    usuario(1, "Ana", "pendente"),
    usuario(2, "Bia", "ativo"),
    usuario(3, "Caio", "inativo"),
    usuario(4, "Dani", "ativo"),
  ];

  it("'todos' devolve a lista inteira", () => {
    expect(filtrarPorSituacao(lista, "todos")).toHaveLength(4);
  });

  it("filtra por situação exata", () => {
    expect(filtrarPorSituacao(lista, "pendente").map((u) => u.nome)).toEqual(["Ana"]);
    expect(filtrarPorSituacao(lista, "ativo").map((u) => u.nome)).toEqual(["Bia", "Dani"]);
    expect(filtrarPorSituacao(lista, "inativo").map((u) => u.nome)).toEqual(["Caio"]);
  });
});

describe("validarNovaSenha", () => {
  it("exige 8 caracteres e confirmação igual", () => {
    expect(validarNovaSenha("curta", "curta")).toMatch(/8 caracteres/);
    expect(validarNovaSenha("senha-longa-1", "senha-longa-2")).toMatch(/não conferem/);
    expect(validarNovaSenha("senha-longa-1", "senha-longa-1")).toBeNull();
  });
});

describe("validarLogin", () => {
  it("aceita letras sem acento, números, ponto, hífen e sublinhado, de 3 a 64 caracteres", () => {
    expect(validarLogin("ana.silva_1-x")).toBeNull();
    expect(validarLogin("abc")).toBeNull();
    expect(validarLogin("a".repeat(64))).toBeNull();
  });

  it("recusa acento, espaço, caractere especial, login curto e longo demais com a mesma mensagem", () => {
    const regra = "Use só letras sem acento, números, ponto, hífen e sublinhado (3 a 64).";
    expect(validarLogin("João")).toBe(regra);
    expect(validarLogin("ana silva")).toBe(regra);
    expect(validarLogin("ana@x")).toBe(regra);
    expect(validarLogin("ab")).toBe(regra);
    expect(validarLogin("a".repeat(65))).toBe(regra);
  });

  it("recusa o prefixo reservado de contas anonimizadas, sem diferenciar caixa", () => {
    expect(validarLogin("removido-x")).toBe("Esse login é reservado.");
    expect(validarLogin("Removido-7")).toBe("Esse login é reservado.");
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
