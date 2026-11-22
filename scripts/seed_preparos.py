"""Insere os registros de exemplo (backend/seeds/preparos_semana.json) em um preparo existente.

Uso: python scripts/seed_preparos.py "Nome do preparo"
Idempotente: registros com o mesmo id já existentes são ignorados.
Usa PREPARO_DB_PATH se definido; senão, o banco local padrão.
Para remover depois: DELETE FROM registros WHERE origem = 'seed';
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from app.database import _upsert_registro_conn, db_session, init_db  # noqa: E402

SEED_FILE = RAIZ / "backend" / "seeds" / "preparos_semana.json"


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit('Uso: python scripts/seed_preparos.py "Nome do preparo"')
    nome = sys.argv[1]
    registros = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    init_db()
    with db_session() as conn:
        row = conn.execute("SELECT id FROM preparos WHERE nome = ?", (nome,)).fetchone()
        if row is None:
            sys.exit(f'Preparo "{nome}" não existe. Crie-o no app e rode de novo.')
        for item in registros:
            _upsert_registro_conn(conn, item, origem="seed", ignore_if_exists=True, preparo_id=row["id"])
    print(f"{len(registros)} preparos de seed processados (existentes foram mantidos).")


if __name__ == "__main__":
    main()
