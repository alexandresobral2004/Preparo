"""Schemas Pydantic da API Preparo de Vegetal v2."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .auth import SENHA_MIN
from .domain import normalizar_tipo, parse_decimal_ptbr


class ChacronaItemIn(BaseModel):
    nucleo: str = ""
    kg: float | None = None

    @field_validator("kg", mode="before")
    @classmethod
    def _parse_kg(cls, v: Any) -> float | None:
        return parse_decimal_ptbr(v)


class PanelaIn(BaseModel):
    numero: int | None = None
    tipo: str = ""
    entrada: str = ""
    fervura: str = ""
    colhida: str = ""
    litros: float | None = None
    pesoSecaKg: float | None = None
    pesoCheiaKg: float | None = None
    metaLitros: float | None = None
    pesoComAguaKg: float | None = None

    @field_validator("tipo", mode="before")
    @classmethod
    def _norm_tipo(cls, v: Any) -> str:
        return normalizar_tipo(v)

    @field_validator("litros", "pesoSecaKg", "pesoCheiaKg", "metaLitros", "pesoComAguaKg", mode="before")
    @classmethod
    def _parse_num(cls, v: Any) -> float | None:
        return parse_decimal_ptbr(v)


class BlocoIn(BaseModel):
    obs: str = ""
    anotador: str = ""
    data: str = ""
    panelas: list[PanelaIn] = Field(default_factory=list)


class RegistroPayload(BaseModel):
    id: str | None = None
    salvoEm: str | None = None
    nucleo: str = "Bendito Filho"
    data: str = ""
    mestre: str = ""
    auxiliar: str = ""
    respMariri: str = ""
    respChacrona: str = ""
    respChacrona2: str = ""
    mariri: str = ""
    maririKg: float | None = None
    chacrona: list[ChacronaItemIn] = Field(default_factory=list)
    obsGeral: str = ""
    blocos: list[BlocoIn] = Field(default_factory=list)

    @field_validator("maririKg", mode="before")
    @classmethod
    def _parse_mariri_kg(cls, v: Any) -> float | None:
        return parse_decimal_ptbr(v)


class LembreteCreate(BaseModel):
    texto: str
    horario: str = ""

    @field_validator("texto")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("Informe o texto do lembrete.")
        return text


class LembretePatch(BaseModel):
    feito: bool | None = None
    texto: str | None = None
    horario: str | None = None


class ConfigUpdate(BaseModel):
    minSemFervura: int | None = Field(default=None, ge=1, le=600)
    horasSemColheita: float | None = Field(default=None, ge=0.5, le=24.0)
    metaLitrosPadrao: float | None = Field(default=None, ge=0.5, le=500.0)


class PredictRequest(BaseModel):
    data: str = ""
    blocos: list[BlocoIn] = Field(default_factory=list)
    metaLitrosPadrao: float | None = Field(default=None, ge=0.5, le=500.0)
    agora: str | None = None


class ImportRequest(BaseModel):
    payload: Any


class ImportSummary(BaseModel):
    importados: int
    jaExistentes: int
    invalidos: int


ModeloNivel = Literal["inicial", "aprendendo", "calibrado"]


class LoginIn(BaseModel):
    """`login` recebe o e-mail (contas novas) ou o login antigo; o nome do campo não muda por compatibilidade."""

    login: str = Field(min_length=1, max_length=254)
    senha: str = Field(min_length=1, max_length=256)


class TrocaSenhaIn(BaseModel):
    senhaAtual: str = Field(min_length=1, max_length=256)
    novaSenha: str = Field(min_length=SENHA_MIN, max_length=256)


GRAUS = Literal["socio", "instrutivo", "conselho", "mestre"]
PREFIXO_USUARIO_REMOVIDO = "removido-"  # logins com esse prefixo são de contas anonimizadas


def _texto(valor: str, limite: int, campo: str) -> str:
    texto = valor.strip()
    if not 1 <= len(texto) <= limite:
        raise ValueError(f"{campo} deve ter de 1 a {limite} caracteres.")
    return texto


def _login_livre(valor: str) -> str:
    if valor.lower().startswith(PREFIXO_USUARIO_REMOVIDO):
        raise ValueError("Esse login é reservado.")
    return valor


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalizar_email(valor: str) -> str:
    email = valor.strip().lower()
    if len(email) > 254 or not _EMAIL_RE.match(email):
        raise ValueError("Informe um e-mail válido.")
    return _login_livre(email)


class UsuarioNovo(BaseModel):
    email: str
    nome: str = Field(min_length=1, max_length=120)
    grau: GRAUS
    nucleo: str
    senha: str = Field(min_length=SENHA_MIN, max_length=256)
    papel: Literal["admin", "usuario"] = "usuario"

    @field_validator("email")
    @classmethod
    def _email_valido(cls, v: str) -> str:
        return normalizar_email(v)

    @field_validator("nome")
    @classmethod
    def _nome_limpo(cls, v: str) -> str:
        return _texto(v, 120, "O nome")

    @field_validator("nucleo")
    @classmethod
    def _nucleo_limpo(cls, v: str) -> str:
        return _texto(v, 80, "O núcleo")


class CadastroIn(BaseModel):
    """Autocadastro. Grau e núcleo são obrigatórios no formulário novo; o PWA antigo ainda pode omiti-los."""

    email: str
    nome: str = Field(min_length=1, max_length=120)
    grau: GRAUS | None = None
    nucleo: str | None = None
    senha: str = Field(min_length=SENHA_MIN, max_length=256)

    @field_validator("email")
    @classmethod
    def _email_valido(cls, v: str) -> str:
        return normalizar_email(v)

    @field_validator("nome")
    @classmethod
    def _nome_limpo(cls, v: str) -> str:
        return _texto(v, 120, "O nome")

    @field_validator("nucleo")
    @classmethod
    def _nucleo_limpo(cls, v: str | None) -> str | None:
        return None if v is None else _texto(v, 80, "O núcleo")


class UsuarioEdicao(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    grau: GRAUS | None = None
    nucleo: str | None = None
    papel: Literal["admin", "usuario"] | None = None
    situacao: Literal["pendente", "ativo", "inativo"] | None = None
    senha: str | None = Field(default=None, min_length=SENHA_MIN, max_length=256)
    email: str | None = None

    @field_validator("nome")
    @classmethod
    def _nome_limpo(cls, v: str | None) -> str | None:
        return None if v is None else _texto(v, 120, "O nome")

    @field_validator("nucleo")
    @classmethod
    def _nucleo_limpo(cls, v: str | None) -> str | None:
        return None if v is None else _texto(v, 80, "O núcleo")

    @field_validator("email")
    @classmethod
    def _email_valido(cls, v: str | None) -> str | None:
        return None if v is None else normalizar_email(v)


class PerfilEdicao(BaseModel):
    """Edição do próprio perfil. Papel e situação não aparecem aqui, então são ignorados."""

    nome: str | None = Field(default=None, min_length=1, max_length=120)
    grau: GRAUS | None = None
    nucleo: str | None = None
    email: str | None = None
    senhaAtual: str | None = Field(default=None, max_length=256)

    @field_validator("nome")
    @classmethod
    def _nome_limpo(cls, v: str | None) -> str | None:
        return None if v is None else _texto(v, 120, "O nome")

    @field_validator("nucleo")
    @classmethod
    def _nucleo_limpo(cls, v: str | None) -> str | None:
        return None if v is None else _texto(v, 80, "O núcleo")

    @field_validator("email")
    @classmethod
    def _email_valido(cls, v: str | None) -> str | None:
        return None if v is None else normalizar_email(v)


class PreparoNovo(BaseModel):
    nome: str = Field(min_length=1, max_length=80)


class MembroSituacaoIn(BaseModel):
    situacao: Literal["aprovado", "recusado"]


class MembroNovoIn(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _email_valido(cls, v: str) -> str:
        return normalizar_email(v)
