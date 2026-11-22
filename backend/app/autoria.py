"""Autoria por bloco: quem criou e quem editou, sempre calculada no servidor."""

from __future__ import annotations

from typing import Any

from .domain import normalizar_tipo, try_parse_decimal_ptbr

_CAMPOS_PANELA = ("entrada", "fervura", "colhida")
_CAMPOS_NUM = ("litros", "pesoSecaKg", "pesoCheiaKg", "metaLitros", "pesoComAguaKg")


def assinatura_bloco(bloco: dict[str, Any]) -> tuple:
    """Conteúdo normalizado do bloco; formatos diferentes do mesmo valor dão a mesma assinatura."""
    panelas = []
    for p in bloco.get("panelas") or []:
        panelas.append(
            (
                p.get("numero"),
                normalizar_tipo(p.get("tipo")),
                *(str(p.get(c) or "").strip() for c in _CAMPOS_PANELA),
                *(try_parse_decimal_ptbr(p.get(c)) for c in _CAMPOS_NUM),
            )
        )
    return (
        str(bloco.get("obs") or "").strip(),
        str(bloco.get("anotador") or "").strip(),
        str(bloco.get("data") or "").strip(),
        tuple(panelas),
    )


def aplicar_autoria(
    anteriores: list[dict[str, Any]],
    novos: list[dict[str, Any]],
    usuario: dict[str, Any] | None,
    agora: str,
) -> list[dict[str, Any]]:
    """Devolve os blocos novos com 'autoria' recalculada a partir dos anteriores.

    Bloco sem equivalente anterior: criado por `usuario`. Bloco com conteúdo diferente do
    anterior: mantém quem criou e registra quem editou. Igual: mantém a autoria. A autoria que
    vier do cliente é sempre descartada.
    """
    resultado: list[dict[str, Any]] = []
    for i, novo in enumerate(novos):
        base = {k: v for k, v in novo.items() if k != "autoria"}
        if usuario is None:
            resultado.append(base)
            continue
        anterior = anteriores[i] if i < len(anteriores) else None
        autoria_ant = (anterior or {}).get("autoria")
        if not autoria_ant:
            autoria = {"criadoPorId": usuario["id"], "criadoPorNome": usuario["nome"], "criadoEm": agora}
        elif assinatura_bloco(anterior) != assinatura_bloco(base):
            autoria = {
                **autoria_ant,
                "editadoPorId": usuario["id"],
                "editadoPorNome": usuario["nome"],
                "editadoEm": agora,
            }
        else:
            autoria = autoria_ant
        resultado.append({**base, "autoria": autoria})
    return resultado
