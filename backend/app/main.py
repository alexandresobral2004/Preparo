"""Aplicação principal FastAPI + inicialização do SQLite + serving do build React PWA."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth
from .config import FRONTEND_DIST_DIR
from .database import init_db
from .routers import auth as auth_router
from .routers import config_avisos, lembretes, preparos, rascunho, registros, stats, usuarios


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    auth.garantir_admin_inicial()
    yield


_ROTULOS_CAMPOS = {
    "login": "Login",
    "nome": "Nome",
    "senha": "Senha",
    "novaSenha": "Nova senha",
    "senhaAtual": "Senha atual",
    "grau": "Grau",
    "nucleo": "Núcleo",
}


def _frase_do_erro(erro: dict) -> str:
    """Traduz um erro do Pydantic em frase. Nunca usa o valor digitado nem o contexto técnico."""
    campo = next((p for p in reversed(erro["loc"]) if isinstance(p, str) and p != "body"), "campo")
    rotulo = _ROTULOS_CAMPOS.get(campo, campo)
    tipo, ctx = erro["type"], erro.get("ctx", {})
    if tipo == "missing":
        return f"Informe {rotulo}."
    if tipo == "string_too_short":
        return f"{rotulo} deve ter pelo menos {ctx['min_length']} caracteres."
    if tipo == "string_too_long":
        return f"{rotulo} deve ter no máximo {ctx['max_length']} caracteres."
    if tipo == "string_pattern_mismatch":
        return f"{rotulo} só aceita letras, números, ponto, hífen e sublinhado."
    if tipo == "literal_error":
        return f"Escolha um valor válido para {rotulo}."
    if tipo == "value_error":
        return erro["msg"].removeprefix("Value error, ")
    return f"Confira o campo {rotulo}."


async def _erro_de_validacao(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": " ".join(_frase_do_erro(e) for e in exc.errors())})


def create_app(dist_dir: Path | None = None) -> FastAPI:
    app = FastAPI(
        title="Preparo de Vegetal v2 API",
        version="2.0.0",
        lifespan=lifespan,
    )
    app.add_exception_handler(RequestValidationError, _erro_de_validacao)

    # Por padrão só a mesma origem acessa a API (o Vite usa proxy no desenvolvimento).
    origens = [o.strip() for o in os.environ.get("PREPARO_CORS_ORIGINS", "").split(",") if o.strip()]
    if origens:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origens,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def cabecalhos_de_seguranca(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if auth.cookie_seguro():
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "preparo-vegetal-v2"}

    app.include_router(auth_router.router)
    app.include_router(usuarios.router)
    app.include_router(preparos.router)
    protegidas = [Depends(auth.exigir_login)]
    for rota in (registros, rascunho, lembretes, config_avisos, stats):
        app.include_router(rota.router, dependencies=protegidas)

    static_root = dist_dir or FRONTEND_DIST_DIR
    if static_root.exists() and (static_root / "index.html").exists():
        assets_dir = static_root / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        icons_dir = static_root / "icons"
        if icons_dir.exists():
            app.mount("/icons", StaticFiles(directory=str(icons_dir)), name="icons")

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_spa(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Endpoint não encontrado.")
            candidate = (static_root / full_path).resolve()
            try:
                candidate.relative_to(static_root.resolve())
            except ValueError as exc:
                raise HTTPException(status_code=403, detail="Caminho inválido.") from exc

            if full_path and candidate.is_file():
                return FileResponse(str(candidate))
            return FileResponse(str(static_root / "index.html"))

    return app


app = create_app()
