import type { BlocoAutoria, PreparoDraft } from "../types";

export const SENHA_MIN = 8;

export function validarNovaSenha(nova: string, confirmacao: string): string | null {
  if (nova.length < SENHA_MIN) return `A senha precisa ter pelo menos ${SENHA_MIN} caracteres.`;
  if (nova !== confirmacao) return "As senhas não conferem.";
  return null;
}

function hhmm(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** Texto exibido acima do bloco: quem criou e quem editou por último. */
export function descreverAutoria(autoria: BlocoAutoria | null | undefined): string {
  if (!autoria) return "";
  const criado = `Criado por ${autoria.criadoPorNome} às ${hhmm(autoria.criadoEm)}`;
  if (!autoria.editadoPorNome || !autoria.editadoEm) return criado;
  return `${criado} · editado por ${autoria.editadoPorNome} às ${hhmm(autoria.editadoEm)}`;
}

/**
 * Depois de gravar o rascunho, incorpora do servidor só a versão e a autoria dos blocos.
 * O resto do que a pessoa digitou enquanto a gravação ia e voltava não pode ser sobrescrito.
 */
export function mesclarRespostaDoRascunho(local: PreparoDraft, doServidor: PreparoDraft): PreparoDraft {
  const mudouVersao = local._versao !== doServidor._versao;
  let mudouAutoria = false;
  const blocos = local.blocos.map((bloco, i) => {
    const autoria = doServidor.blocos[i]?.autoria;
    if (autoria === undefined || JSON.stringify(autoria) === JSON.stringify(bloco.autoria)) return bloco;
    mudouAutoria = true;
    return { ...bloco, autoria };
  });
  if (!mudouVersao && !mudouAutoria) return local;
  return { ...local, _versao: doServidor._versao, blocos };
}
