"""Rotas de login, logout, sessão atual e troca da própria senha."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .. import auth
from ..database import db_session, now_iso
from ..schemas import CadastroIn, LoginIn, PerfilEdicao, TrocaSenhaIn

router = APIRouter(prefix="/api/auth", tags=["auth"])

_MSG_LOGIN_INVALIDO = "Login ou senha inválidos."


def _ip_do_cliente(request: Request) -> str:
    """IP que o proxy da Railway acrescentou ao X-Forwarded-For; senão o IP direto.

    O primeiro elemento vem do cliente e pode ser forjado a cada requisição, então não serve de chave.
    """
    # getlist junta cabeçalhos repetidos: se o proxy acrescentar o IP numa linha nova, o último é o dele.
    encaminhado = ",".join(request.headers.getlist("x-forwarded-for")).split(",")[-1].strip()
    if encaminhado:
        return encaminhado
    return request.client.host if request.client else "desconhecido"


def _contar_pendentes(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM usuarios WHERE situacao = 'pendente'").fetchone()[0]


@router.post("/login")
def login(body: LoginIn, response: Response) -> dict[str, Any]:
    if auth.bloqueado(body.login):
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde 15 minutos e tente de novo.")
    with db_session() as conn:
        usuario = auth.autenticar(conn, body.login, body.senha)
        if usuario is None:
            auth.registrar_falha(body.login)
            raise HTTPException(status_code=401, detail=_MSG_LOGIN_INVALIDO)
        if usuario["situacao"] == "pendente":
            raise HTTPException(status_code=403, detail="Seu cadastro aguarda a aprovação do administrador.")
        if usuario["situacao"] != "ativo":
            auth.registrar_falha(body.login)
            raise HTTPException(status_code=401, detail=_MSG_LOGIN_INVALIDO)
        token = auth.criar_sessao(conn, usuario["id"])
        publico = auth.usuario_publico(usuario)
    auth.limpar_falhas(body.login)
    response.set_cookie(
        auth.COOKIE_SESSAO,
        token,
        max_age=auth.SESSAO_DIAS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=auth.cookie_seguro(),
        path="/",
    )
    return {"usuario": publico}


@router.post("/cadastro", status_code=201)
def cadastro(body: CadastroIn, request: Request) -> dict[str, str]:
    """Autocadastro: a conta nasce pendente e só entra depois que o administrador aprovar."""
    chave_ip = "cadastro:" + _ip_do_cliente(request)
    if auth.bloqueado(chave_ip):
        raise HTTPException(status_code=429, detail="Muitos cadastros deste endereço. Aguarde 15 minutos e tente de novo.")
    auth.registrar_falha(chave_ip)  # conta cada tentativa, não só as recusadas
    with db_session() as conn:
        if conn.execute("SELECT 1 FROM usuarios WHERE login = ?", (body.login,)).fetchone():
            raise HTTPException(status_code=409, detail="Esse login já está em uso.")
        if _contar_pendentes(conn) >= auth.MAX_PENDENTES:
            raise HTTPException(status_code=429, detail="Há cadastros demais aguardando aprovação. Tente mais tarde.")
        conn.execute(
            "INSERT INTO usuarios (login, nome, senha_hash, papel, situacao, created_at, grau, nucleo) "
            "VALUES (?, ?, ?, 'usuario', 'pendente', ?, ?, ?)",
            (body.login, body.nome, auth.hash_senha(body.senha), now_iso(), body.grau or "", body.nucleo or ""),
        )
    return {"mensagem": "Cadastro enviado. Você poderá entrar quando o administrador aprovar."}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    token = request.cookies.get(auth.COOKIE_SESSAO)
    if token:
        with db_session() as conn:
            auth.encerrar_sessao(conn, token)
    response.delete_cookie(auth.COOKIE_SESSAO, path="/")
    return {"ok": True}


@router.get("/me")
def me(usuario: dict[str, Any] = Depends(auth.exigir_login)) -> dict[str, Any]:
    if usuario["papel"] != "admin":
        return {"usuario": usuario}
    with db_session() as conn:
        return {"usuario": usuario, "cadastrosPendentes": _contar_pendentes(conn)}


@router.patch("/perfil")
def editar_perfil(body: PerfilEdicao, usuario: dict[str, Any] = Depends(auth.exigir_login)) -> dict[str, Any]:
    """Nome, grau e núcleo de quem está logado. Papel e situação não são alterados aqui."""
    with db_session() as conn:
        conn.execute(
            "UPDATE usuarios SET nome = COALESCE(?, nome), grau = COALESCE(?, grau), nucleo = COALESCE(?, nucleo) "
            "WHERE id = ?",
            (body.nome, body.grau, body.nucleo, usuario["id"]),
        )
        atualizado = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario["id"],)).fetchone()
        return auth.usuario_publico(atualizado)


@router.post("/senha")
def trocar_senha(
    body: TrocaSenhaIn,
    request: Request,
    usuario: dict[str, Any] = Depends(auth.exigir_login),
) -> dict[str, bool]:
    with db_session() as conn:
        row = conn.execute("SELECT senha_hash FROM usuarios WHERE id = ?", (usuario["id"],)).fetchone()
        if row is None or not auth.verificar_senha(body.senhaAtual, row["senha_hash"]):
            raise HTTPException(status_code=400, detail="A senha atual está incorreta.")
        conn.execute(
            "UPDATE usuarios SET senha_hash = ? WHERE id = ?",
            (auth.hash_senha(body.novaSenha), usuario["id"]),
        )
        auth.encerrar_sessoes_do_usuario(
            conn, usuario["id"], manter_token=request.cookies.get(auth.COOKIE_SESSAO)
        )
    return {"ok": True}
