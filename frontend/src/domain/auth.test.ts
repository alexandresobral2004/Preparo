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
  normalizarEmail,
  podeEditar,
  validarEmail,
  validarEntrar,
  validarNovaSenha,
} from "./auth";

const usuario = (id: number, nome: string, situacao: Usuario["situacao"]): Usuario => ({
  id,
  login: `login${id}`,
  email: null,
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

describe("normalizarEmail", () => {
  it("tira espaços das pontas e põe em minúsculas", () => {
    expect(normalizarEmail(" Ana@X.com ")).toBe("ana@x.com");
  });
});

describe("validarEntrar", () => {
  it("exige e-mail ou login e senha antes de enviar, com a mensagem de cada campo", () => {
    expect(validarEntrar("", "segredo-1")).toBe("Informe seu e-mail ou login.");
    expect(validarEntrar("   ", "segredo-1")).toBe("Informe seu e-mail ou login.");
    expect(validarEntrar("ana", "")).toBe("Informe sua senha.");
  });

  it("aceita login ou e-mail preenchido com senha, sem exigir formato de e-mail", () => {
    expect(validarEntrar("ana", "segredo-1")).toBeNull();
    expect(validarEntrar("ana@x.com", "x")).toBeNull();
  });
});

describe("validarEmail", () => {
  it("aceita e-mail válido, mesmo com espaços e caixa mista", () => {
    expect(validarEmail("ana@x.com")).toBeNull();
    expect(validarEmail(" Ana@X.com ")).toBeNull();
  });

  it("recusa formato incompleto ou com espaço no meio, com a mensagem em português", () => {
    const mensagem = "Informe um e-mail válido.";
    expect(validarEmail("ana")).toBe(mensagem);
    expect(validarEmail("ana@")).toBe(mensagem);
    expect(validarEmail("ana@x")).toBe(mensagem);
    expect(validarEmail("a b@x.com")).toBe(mensagem);
    expect(validarEmail("")).toBe(mensagem);
    expect(validarEmail("   ")).toBe(mensagem);
  });

  it("recusa o prefixo reservado 'removido-' de contas anonimizadas, sem diferenciar caixa", () => {
    expect(validarEmail("removido-1@x.com")).toBe("Esse e-mail é reservado.");
    expect(validarEmail(" REMOVIDO-1@x.com ")).toBe("Esse e-mail é reservado.");
    expect(validarEmail("ana@x.com")).toBeNull();
  });

  it("aceita até 254 caracteres e recusa 255", () => {
    expect(validarEmail("a".repeat(248) + "@x.com")).toBeNull(); // 254
    expect(validarEmail("a".repeat(249) + "@x.com")).toBe("Informe um e-mail válido.");
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

describe("podeEditar", () => {
  const preparo = (minhaPermissao: "editar" | "acompanhar" | null) => ({ minhaPermissao });

  it("libera quem edita e o dono (que recebe 'editar' do servidor)", () => {
    expect(podeEditar(preparo("editar"))).toBe(true);
  });

  it("bloqueia quem só acompanha", () => {
    expect(podeEditar(preparo("acompanhar"))).toBe(false);
  });

  it("bloqueia quem não tem vínculo aprovado", () => {
    expect(podeEditar(preparo(null))).toBe(false);
  });
});
