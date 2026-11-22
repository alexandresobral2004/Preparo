"""Rotas de login, logout, sessão atual e troca da própria senha."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .. import auth
from ..database import db_session, now_iso
from ..schemas import CadastroIn, LoginIn, TrocaSenhaIn

router = APIRouter(prefix="/api/auth", tags=["auth"])

_MSG_LOGIN_INVALIDO = "Login ou senha inválidos."


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
def cadastro(body: CadastroIn) -> dict[str, str]:
    """Autocadastro: a conta nasce pendente e só entra depois que o administrador aprovar."""
    with db_session() as conn:
        if conn.execute("SELECT 1 FROM usuarios WHERE login = ?", (body.login,)).fetchone():
            raise HTTPException(status_code=409, detail="Esse login já está em uso.")
        pendentes = conn.execute("SELECT COUNT(*) FROM usuarios WHERE situacao = 'pendente'").fetchone()[0]
        if pendentes >= auth.MAX_PENDENTES:
            raise HTTPException(status_code=429, detail="Há cadastros demais aguardando aprovação. Tente mais tarde.")
        conn.execute(
            "INSERT INTO usuarios (login, nome, senha_hash, papel, situacao, created_at) "
            "VALUES (?, ?, ?, 'usuario', 'pendente', ?)",
            (body.login, body.nome.strip(), auth.hash_senha(body.senha), now_iso()),
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
    return {"usuario": usuario}


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
