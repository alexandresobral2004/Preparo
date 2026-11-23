"""Persistência SQLite com WAL mode, chaves estrangeiras e seed idempotente."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .autoria import aplicar_autoria
from .config import DADOS_INICIAIS, DEFAULT_CONFIG, get_db_path
from .domain import normalizar_tipo, try_parse_decimal_ptbr

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS registros (
    id TEXT PRIMARY KEY,
    salvo_em TEXT NOT NULL,
    nucleo TEXT NOT NULL DEFAULT 'Bendito Filho',
    data TEXT NOT NULL DEFAULT '',
    mestre TEXT NOT NULL DEFAULT '',
    auxiliar TEXT NOT NULL DEFAULT '',
    resp_mariri TEXT NOT NULL DEFAULT '',
    resp_chacrona TEXT NOT NULL DEFAULT '',
    resp_chacrona2 TEXT NOT NULL DEFAULT '',
    mariri TEXT NOT NULL DEFAULT '',
    mariri_kg REAL,
    obs_geral TEXT NOT NULL DEFAULT '',
    origem TEXT NOT NULL DEFAULT 'usuario',
    excluido INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chacrona_itens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    registro_id TEXT NOT NULL REFERENCES registros(id) ON DELETE CASCADE,
    ordem INTEGER NOT NULL,
    nucleo TEXT NOT NULL DEFAULT '',
    kg REAL
);

CREATE TABLE IF NOT EXISTS blocos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    registro_id TEXT NOT NULL REFERENCES registros(id) ON DELETE CASCADE,
    ordem INTEGER NOT NULL,
    obs TEXT NOT NULL DEFAULT '',
    anotador TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS panelas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bloco_id INTEGER NOT NULL REFERENCES blocos(id) ON DELETE CASCADE,
    numero INTEGER NOT NULL,
    tipo TEXT NOT NULL DEFAULT '',
    entrada TEXT NOT NULL DEFAULT '',
    fervura TEXT NOT NULL DEFAULT '',
    colhida TEXT NOT NULL DEFAULT '',
    litros REAL,
    peso_seca_kg REAL,
    peso_cheia_kg REAL,
    meta_litros REAL
);

CREATE INDEX IF NOT EXISTS idx_panelas_stats
    ON panelas(tipo, fervura, colhida, litros);

CREATE INDEX IF NOT EXISTS idx_registros_data
    ON registros(excluido, data DESC, salvo_em DESC);

CREATE TABLE IF NOT EXISTS rascunho (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lembretes (
    id TEXT PRIMARY KEY,
    texto TEXT NOT NULL,
    horario TEXT NOT NULL DEFAULT '',
    feito INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS configuracoes (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nome TEXT NOT NULL,
    senha_hash TEXT NOT NULL,
    papel TEXT NOT NULL CHECK (papel IN ('admin', 'usuario')),
    situacao TEXT NOT NULL DEFAULT 'pendente' CHECK (situacao IN ('pendente', 'ativo', 'inativo')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preparos (
    id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    criado_por INTEGER NOT NULL REFERENCES usuarios(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preparo_membros (
    preparo_id TEXT NOT NULL REFERENCES preparos(id) ON DELETE CASCADE,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    papel TEXT NOT NULL CHECK (papel IN ('dono', 'membro')),
    situacao TEXT NOT NULL CHECK (situacao IN ('pendente', 'aprovado', 'recusado')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (preparo_id, usuario_id)
);

CREATE TABLE IF NOT EXISTS rascunhos (
    preparo_id TEXT PRIMARY KEY REFERENCES preparos(id) ON DELETE CASCADE,
    payload_json TEXT NOT NULL,
    versao INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS configuracoes_preparo (
    preparo_id TEXT NOT NULL REFERENCES preparos(id) ON DELETE CASCADE,
    chave TEXT NOT NULL,
    valor TEXT NOT NULL,
    PRIMARY KEY (preparo_id, chave)
);

CREATE TABLE IF NOT EXISTS sessoes (
    token_hash TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""


class RegistroDeOutroPreparo(Exception):
    """O id informado já pertence a um registro de outro preparo."""


class ConflitoRascunho(Exception):
    """O rascunho foi alterado por outra pessoa depois da última leitura de quem está salvando."""

    def __init__(self, atual: dict[str, Any]):
        super().__init__("Rascunho desatualizado.")
        self.atual = atual


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


@contextmanager
def db_session(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_AUTORIA_BLOCO = ("criado_por_id", "criado_por_nome", "criado_em", "editado_por_id", "editado_por_nome", "editado_em")

# Colunas acrescentadas depois da primeira versão do esquema (bancos antigos não as têm).
_COLUNAS_NOVAS: dict[str, list[tuple[str, str]]] = {
    "blocos": [("anotador", "TEXT NOT NULL DEFAULT ''"), ("data", "TEXT NOT NULL DEFAULT ''")]
    + [(c, "INTEGER" if c.endswith("_id") else "TEXT NOT NULL DEFAULT ''") for c in _AUTORIA_BLOCO],
    "registros": [
        ("preparo_id", "TEXT"),
        ("criado_por_id", "INTEGER"),
        ("criado_por_nome", "TEXT NOT NULL DEFAULT ''"),
        ("atualizado_por_id", "INTEGER"),
        ("atualizado_por_nome", "TEXT NOT NULL DEFAULT ''"),
    ],
    "lembretes": [("preparo_id", "TEXT")],
    "panelas": [("peso_com_agua_kg", "REAL")],
    "usuarios": [("grau", "TEXT NOT NULL DEFAULT ''"), ("nucleo", "TEXT NOT NULL DEFAULT ''"), ("email", "TEXT")],
}


def _garantir_colunas(conn: sqlite3.Connection) -> None:
    """Adiciona, uma única vez, as colunas que bancos criados antes dos campos não têm."""
    for tabela, colunas in _COLUNAS_NOVAS.items():
        existentes = {row["name"] for row in conn.execute(f"PRAGMA table_info({tabela})")}
        for nome, ddl in colunas:
            if nome not in existentes:
                conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {ddl}")
    # E-mail como identificador: contas antigas cujo login já é um e-mail ganham o mesmo valor.
    conn.execute(
        "UPDATE usuarios SET email = lower(trim(login)) "
        "WHERE email IS NULL AND login LIKE '%@%' AND login NOT LIKE 'removido-%'"
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios(email COLLATE NOCASE)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_registros_preparo ON registros(preparo_id, excluido, data DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lembretes_preparo ON lembretes(preparo_id)")


def init_db(db_path: Path | None = None) -> None:
    """Cria as tabelas, índices, configurações padrão e registros iniciais."""
    with db_session(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        _garantir_colunas(conn)
        for chave, valor in DEFAULT_CONFIG.items():
            conn.execute(
                "INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)",
                (chave, valor),
            )
        for item in DADOS_INICIAIS:
            _upsert_registro_conn(conn, item, origem="inicial", ignore_if_exists=True)


def _upsert_registro_conn(
    conn: sqlite3.Connection,
    payload: dict[str, Any],
    *,
    origem: str = "usuario",
    ignore_if_exists: bool = False,
    preparo_id: str | None = None,
    usuario: dict[str, Any] | None = None,
) -> str:
    reg_id = str(payload.get("id") or "").strip()
    if not reg_id:
        raise ValueError("Registro sem id válido.")

    existing = conn.execute(
        "SELECT id, origem, created_at, preparo_id, criado_por_id, criado_por_nome, "
        "atualizado_por_id, atualizado_por_nome FROM registros WHERE id = ?",
        (reg_id,),
    ).fetchone()

    if existing and ignore_if_exists:
        return reg_id
    if existing and existing["preparo_id"] != preparo_id:
        raise RegistroDeOutroPreparo(reg_id)

    ts = now_iso()
    salvo_em = str(payload.get("salvoEm") or payload.get("salvo_em") or ts)
    created_at = existing["created_at"] if existing else ts
    final_origem = existing["origem"] if existing else origem
    criado_id = existing["criado_por_id"] if existing else (usuario["id"] if usuario else None)
    criado_nome = existing["criado_por_nome"] if existing else (usuario["nome"] if usuario else "")
    atual_id = usuario["id"] if usuario else (existing["atualizado_por_id"] if existing else None)
    atual_nome = usuario["nome"] if usuario else (existing["atualizado_por_nome"] if existing else "")

    # Autoria dos blocos: compara com a versão salva; registro novo parte do rascunho do preparo.
    if existing:
        anteriores = hydrate_registro(
            conn, conn.execute("SELECT * FROM registros WHERE id = ?", (reg_id,)).fetchone()
        )["blocos"]
    else:
        anteriores = (get_rascunho(conn, preparo_id) or {}).get("blocos") or [] if preparo_id else []
    blocos_com_autoria = aplicar_autoria(anteriores, payload.get("blocos") or [], usuario, ts)

    mariri_kg = try_parse_decimal_ptbr(payload.get("maririKg"))

    conn.execute(
        """
        INSERT INTO registros (
            id, salvo_em, nucleo, data, mestre, auxiliar,
            resp_mariri, resp_chacrona, resp_chacrona2,
            mariri, mariri_kg, obs_geral, origem, excluido,
            created_at, updated_at, preparo_id,
            criado_por_id, criado_por_nome, atualizado_por_id, atualizado_por_nome
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            salvo_em = excluded.salvo_em,
            nucleo = excluded.nucleo,
            data = excluded.data,
            mestre = excluded.mestre,
            auxiliar = excluded.auxiliar,
            resp_mariri = excluded.resp_mariri,
            resp_chacrona = excluded.resp_chacrona,
            resp_chacrona2 = excluded.resp_chacrona2,
            mariri = excluded.mariri,
            mariri_kg = excluded.mariri_kg,
            obs_geral = excluded.obs_geral,
            excluido = 0,
            updated_at = excluded.updated_at,
            atualizado_por_id = excluded.atualizado_por_id,
            atualizado_por_nome = excluded.atualizado_por_nome
        """,
        (
            reg_id,
            salvo_em,
            str(payload.get("nucleo") or "Bendito Filho"),
            str(payload.get("data") or ""),
            str(payload.get("mestre") or ""),
            str(payload.get("auxiliar") or ""),
            str(payload.get("respMariri") or ""),
            str(payload.get("respChacrona") or ""),
            str(payload.get("respChacrona2") or ""),
            str(payload.get("mariri") or ""),
            mariri_kg,
            str(payload.get("obsGeral") or ""),
            final_origem,
            created_at,
            ts,
            preparo_id,
            criado_id,
            criado_nome,
            atual_id,
            atual_nome,
        ),
    )

    conn.execute("DELETE FROM chacrona_itens WHERE registro_id = ?", (reg_id,))
    chacrona_list = payload.get("chacrona") or []
    for idx, ch in enumerate(chacrona_list):
        conn.execute(
            "INSERT INTO chacrona_itens (registro_id, ordem, nucleo, kg) VALUES (?, ?, ?, ?)",
            (
                reg_id,
                idx,
                str(ch.get("nucleo") or ""),
                try_parse_decimal_ptbr(ch.get("kg")),
            ),
        )

    conn.execute("DELETE FROM blocos WHERE registro_id = ?", (reg_id,))
    blocos_list = blocos_com_autoria
    panela_global_counter = 0
    for b_idx, bloco in enumerate(blocos_list):
        cur = conn.execute(
            "INSERT INTO blocos (registro_id, ordem, obs, anotador, data, criado_por_id, "
            "criado_por_nome, criado_em, editado_por_id, editado_por_nome, editado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                reg_id,
                b_idx,
                str(bloco.get("obs") or ""),
                str(bloco.get("anotador") or "").strip(),
                str(bloco.get("data") or "").strip(),
                *_autoria_para_colunas(bloco.get("autoria")),
            ),
        )
        bloco_id = cur.lastrowid
        panelas_list = bloco.get("panelas") or []
        for p_idx, pan in enumerate(panelas_list):
            panela_global_counter += 1
            numero = pan.get("numero")
            numero_int = int(numero) if numero is not None else (b_idx * 5 + p_idx + 1)
            conn.execute(
                """
                INSERT INTO panelas (
                    bloco_id, numero, tipo, entrada, fervura, colhida,
                    litros, peso_seca_kg, peso_cheia_kg, meta_litros, peso_com_agua_kg
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bloco_id,
                    numero_int,
                    normalizar_tipo(pan.get("tipo")),
                    str(pan.get("entrada") or "").strip(),
                    str(pan.get("fervura") or "").strip(),
                    str(pan.get("colhida") or "").strip(),
                    try_parse_decimal_ptbr(pan.get("litros")),
                    try_parse_decimal_ptbr(pan.get("pesoSecaKg")),
                    try_parse_decimal_ptbr(pan.get("pesoCheiaKg")),
                    try_parse_decimal_ptbr(pan.get("metaLitros")),
                    try_parse_decimal_ptbr(pan.get("pesoComAguaKg")),
                ),
            )

    return reg_id


def _autoria_para_colunas(autoria: dict[str, Any] | None) -> tuple:
    a = autoria or {}
    return (
        a.get("criadoPorId"), a.get("criadoPorNome") or "", a.get("criadoEm") or "",
        a.get("editadoPorId"), a.get("editadoPorNome") or "", a.get("editadoEm") or "",
    )


def _autoria_de_linha(b: sqlite3.Row) -> dict[str, Any] | None:
    if not b["criado_em"]:
        return None
    autoria: dict[str, Any] = {
        "criadoPorId": b["criado_por_id"], "criadoPorNome": b["criado_por_nome"], "criadoEm": b["criado_em"],
    }
    if b["editado_em"]:
        autoria.update(
            editadoPorId=b["editado_por_id"], editadoPorNome=b["editado_por_nome"], editadoEm=b["editado_em"]
        )
    return autoria


def hydrate_registro(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    reg_id = row["id"]
    chacrona_rows = conn.execute(
        "SELECT nucleo, kg FROM chacrona_itens WHERE registro_id = ? ORDER BY ordem ASC, id ASC",
        (reg_id,),
    ).fetchall()
    bloco_rows = conn.execute(
        "SELECT id, ordem, obs, anotador, data, criado_por_id, criado_por_nome, criado_em, "
        "editado_por_id, editado_por_nome, editado_em FROM blocos WHERE registro_id = ? ORDER BY ordem ASC, id ASC",
        (reg_id,),
    ).fetchall()

    blocos: list[dict[str, Any]] = []
    for b in bloco_rows:
        pan_rows = conn.execute(
            """
            SELECT numero, tipo, entrada, fervura, colhida, litros,
                   peso_seca_kg, peso_cheia_kg, meta_litros, peso_com_agua_kg
            FROM panelas
            WHERE bloco_id = ?
            ORDER BY numero ASC, id ASC
            """,
            (b["id"],),
        ).fetchall()
        blocos.append(
            {
                "obs": b["obs"],
                "anotador": b["anotador"],
                "data": b["data"],
                "autoria": _autoria_de_linha(b),
                "panelas": [
                    {
                        "numero": p["numero"],
                        "tipo": p["tipo"],
                        "entrada": p["entrada"],
                        "fervura": p["fervura"],
                        "colhida": p["colhida"],
                        "litros": p["litros"],
                        "pesoSecaKg": p["peso_seca_kg"],
                        "pesoCheiaKg": p["peso_cheia_kg"],
                        "metaLitros": p["meta_litros"],
                        "pesoComAguaKg": p["peso_com_agua_kg"],
                    }
                    for p in pan_rows
                ],
            }
        )

    return {
        "id": reg_id,
        "salvoEm": row["salvo_em"],
        "nucleo": row["nucleo"],
        "data": row["data"],
        "mestre": row["mestre"],
        "auxiliar": row["auxiliar"],
        "respMariri": row["resp_mariri"],
        "respChacrona": row["resp_chacrona"],
        "respChacrona2": row["resp_chacrona2"],
        "mariri": row["mariri"],
        "maririKg": row["mariri_kg"],
        "chacrona": [{"nucleo": c["nucleo"], "kg": c["kg"]} for c in chacrona_rows],
        "obsGeral": row["obs_geral"],
        "origem": row["origem"],
        "criadoPor": {"id": row["criado_por_id"], "nome": row["criado_por_nome"]} if row["criado_por_nome"] else None,
        "atualizadoPor": (
            {"id": row["atualizado_por_id"], "nome": row["atualizado_por_nome"]}
            if row["atualizado_por_nome"]
            else None
        ),
        "blocos": blocos,
    }


def list_registros(conn: sqlite3.Connection, preparo_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM registros
        WHERE excluido = 0 AND preparo_id = ?
        ORDER BY data DESC, salvo_em DESC
        """,
        (preparo_id,),
    ).fetchall()
    return [hydrate_registro(conn, row) for row in rows]


def get_registro(conn: sqlite3.Connection, reg_id: str, preparo_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM registros WHERE id = ? AND excluido = 0 AND preparo_id = ?",
        (reg_id, preparo_id),
    ).fetchone()
    return hydrate_registro(conn, row) if row else None


def save_registro(
    conn: sqlite3.Connection,
    payload: dict[str, Any],
    preparo_id: str,
    usuario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reg_id = _upsert_registro_conn(conn, payload, origem="usuario", preparo_id=preparo_id, usuario=usuario)
    result = get_registro(conn, reg_id, preparo_id)
    assert result is not None
    return result


def delete_registro(conn: sqlite3.Connection, reg_id: str, preparo_id: str) -> bool:
    row = conn.execute(
        "SELECT id, origem FROM registros WHERE id = ? AND excluido = 0 AND preparo_id = ?",
        (reg_id, preparo_id),
    ).fetchone()
    if not row:
        return False
    if row["origem"] == "inicial":
        conn.execute(
            "UPDATE registros SET excluido = 1, updated_at = ? WHERE id = ?",
            (now_iso(), reg_id),
        )
    else:
        conn.execute("DELETE FROM registros WHERE id = ?", (reg_id,))
    return True


def registro_exists(conn: sqlite3.Connection, reg_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM registros WHERE id = ?",
        (reg_id,),
    ).fetchone()
    return row is not None


_CAMPOS_META_RASCUNHO = {"_updatedAt", "_versao"}


def get_rascunho(conn: sqlite3.Connection, preparo_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT payload_json, versao, updated_at FROM rascunhos WHERE preparo_id = ?", (preparo_id,)
    ).fetchone()
    if not row:
        return None
    data = json.loads(row["payload_json"])
    data["_updatedAt"] = row["updated_at"]
    data["_versao"] = row["versao"]
    return data


def save_rascunho(
    conn: sqlite3.Connection,
    preparo_id: str,
    payload: dict[str, Any],
    usuario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Grava o rascunho do preparo. Recusa (ConflitoRascunho) se foi alterado desde a leitura de quem salva."""
    base = payload.get("_versao")
    atual = get_rascunho(conn, preparo_id)
    if atual is not None and base != atual["_versao"]:
        raise ConflitoRascunho(atual)
    if atual is None and base not in (None, 0):
        raise ConflitoRascunho({})  # o rascunho foi apagado/finalizado por outra pessoa

    ts = now_iso()
    clean = {k: v for k, v in payload.items() if k not in _CAMPOS_META_RASCUNHO}
    clean["blocos"] = aplicar_autoria(
        (atual or {}).get("blocos") or [], clean.get("blocos") or [], usuario, ts
    )
    if atual is not None and {k: v for k, v in atual.items() if k not in _CAMPOS_META_RASCUNHO} == clean:
        return atual  # nada mudou: mantém a versão (o app regrava depois de cada resposta)
    versao = (atual["_versao"] if atual else 0) + 1
    conn.execute(
        """
        INSERT INTO rascunhos (preparo_id, payload_json, versao, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(preparo_id) DO UPDATE SET
            payload_json = excluded.payload_json,
            versao = excluded.versao,
            updated_at = excluded.updated_at
        """,
        (preparo_id, json.dumps(clean, ensure_ascii=False), versao, ts),
    )
    return {**clean, "_updatedAt": ts, "_versao": versao}


def clear_rascunho(conn: sqlite3.Connection, preparo_id: str) -> None:
    conn.execute("DELETE FROM rascunhos WHERE preparo_id = ?", (preparo_id,))


def adotar_dados_legados(conn: sqlite3.Connection, usuario_id: int) -> str | None:
    """Dá um dono aos dados criados antes do login (sem preparo) criando o preparo "Bendito Filho".

    Só age se existir algum dado sem preparo; devolve o id do preparo criado (ou None).
    """
    orfaos = conn.execute("SELECT 1 FROM registros WHERE preparo_id IS NULL LIMIT 1").fetchone()
    lembretes = conn.execute("SELECT 1 FROM lembretes WHERE preparo_id IS NULL LIMIT 1").fetchone()
    rascunho = conn.execute("SELECT 1 FROM rascunho WHERE id = 1").fetchone()
    if not (orfaos or lembretes or rascunho):
        return None

    ts = now_iso()
    preparo_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO preparos (id, nome, criado_por, created_at) VALUES (?, 'Bendito Filho', ?, ?)",
        (preparo_id, usuario_id, ts),
    )
    conn.execute(
        "INSERT INTO preparo_membros (preparo_id, usuario_id, papel, situacao, created_at) "
        "VALUES (?, ?, 'dono', 'aprovado', ?)",
        (preparo_id, usuario_id, ts),
    )
    conn.execute("UPDATE registros SET preparo_id = ? WHERE preparo_id IS NULL", (preparo_id,))
    conn.execute("UPDATE lembretes SET preparo_id = ? WHERE preparo_id IS NULL", (preparo_id,))
    conn.execute(
        "INSERT INTO configuracoes_preparo (preparo_id, chave, valor) "
        "SELECT ?, chave, valor FROM configuracoes",
        (preparo_id,),
    )
    conn.execute(
        "INSERT INTO rascunhos (preparo_id, payload_json, versao, updated_at) "
        "SELECT ?, payload_json, 1, updated_at FROM rascunho WHERE id = 1",
        (preparo_id,),
    )
    return preparo_id


def get_config_map(conn: sqlite3.Connection, preparo_id: str) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT chave, valor FROM configuracoes_preparo WHERE preparo_id = ?", (preparo_id,)
    ).fetchall()
    raw = {**DEFAULT_CONFIG, **{r["chave"]: r["valor"] for r in rows}}
    return {
        "minSemFervura": int(float(raw["min_sem_fervura"])),
        "horasSemColheita": float(raw["horas_sem_colheita"]),
        "metaLitrosPadrao": float(raw["meta_litros_padrao"]),
    }


def update_config_map(conn: sqlite3.Connection, preparo_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        "minSemFervura": "min_sem_fervura",
        "horasSemColheita": "horas_sem_colheita",
        "metaLitrosPadrao": "meta_litros_padrao",
    }
    for api_key, db_key in mapping.items():
        if api_key in updates and updates[api_key] is not None:
            conn.execute(
                """
                INSERT INTO configuracoes_preparo (preparo_id, chave, valor) VALUES (?, ?, ?)
                ON CONFLICT(preparo_id, chave) DO UPDATE SET valor = excluded.valor
                """,
                (preparo_id, db_key, str(updates[api_key])),
            )
    return get_config_map(conn, preparo_id)
