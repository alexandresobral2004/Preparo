"""Configurações centrais do backend Preparo de Vegetal v2."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DEFAULT_DB_PATH = BACKEND_DIR / "data" / "preparo.db"
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"


def get_db_path() -> Path:
    """Retorna o caminho configurado para o banco SQLite."""
    env_path = os.environ.get("PREPARO_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


# Registros iniciais embutidos no código (RD-02).
# Novos preparos reais (ex.: 20/03/2026) podem ser adicionados aqui mantendo o formato padrão.
DADOS_INICIAIS: list[dict[str, Any]] = []

DEFAULT_CONFIG: dict[str, str] = {
    "min_sem_fervura": "30",
    "horas_sem_colheita": "5",
    "meta_litros_padrao": "10.15",
}
