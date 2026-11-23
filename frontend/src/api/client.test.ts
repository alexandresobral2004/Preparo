import { describe, expect, it } from "vitest";
import { mensagemDoDetail } from "./client";

describe("mensagemDoDetail", () => {
  it("usa o texto quando o servidor manda uma mensagem simples", () => {
    expect(mensagemDoDetail("Login ou senha inválidos.")).toBe("Login ou senha inválidos.");
  });

  it("troca a lista de erros de validação (422) por uma frase em português, sem objeto cru", () => {
    const detail = [{ type: "string_pattern_mismatch", loc: ["body", "login"], msg: "String should match pattern" }];
    expect(mensagemDoDetail(detail)).toBe("Confira os dados informados.");
  });

  it("devolve null quando não há mensagem utilizável, para o chamador usar o padrão", () => {
    expect(mensagemDoDetail(undefined)).toBeNull();
    expect(mensagemDoDetail(null)).toBeNull();
    expect(mensagemDoDetail({ outro: 1 })).toBeNull();
    expect(mensagemDoDetail(42)).toBeNull();
  });
});
