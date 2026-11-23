"""Testes da coluna de e-mail: migração de banco antigo e unicidade."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.database import db_session, init_db, now_iso
from app.main import create_app
from app.routers import auth as rota_auth
from app.routers import preparos as rota_preparos

# DDL de `usuarios` como existia antes da coluna `email`.
DDL_USUARIOS_ANTIGO = """
CREATE TABLE usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nome TEXT NOT NULL,
    senha_hash TEXT NOT NULL,
    papel TEXT NOT NULL CHECK (papel IN ('admin', 'usuario')),
    situacao TEXT NOT NULL DEFAULT 'pendente' CHECK (situacao IN ('pendente', 'ativo', 'inativo')),
    created_at TEXT NOT NULL
);
"""


def test_migracao_em_banco_antigo_preserva_usuarios_e_login(tmp_path: Path) -> None:
    db = tmp_path / "antigo.db"
    with sqlite3.connect(db) as raw:
        raw.executescript(DDL_USUARIOS_ANTIGO)
        for login in ("admin", "ana@x.com"):
            raw.execute(
                "INSERT INTO usuarios (login, nome, senha_hash, papel, situacao, created_at) "
                "VALUES (?, ?, 'hash', 'usuario', 'ativo', '2026-01-01T00:00:00+00:00')",
                (login, login),
            )

    init_db(db)
    init_db(db)  # segunda execução não pode falhar nem mudar nada

    with db_session(db) as conn:
        linhas = conn.execute("SELECT login, email FROM usuarios ORDER BY id").fetchall()
    assert [tuple(r) for r in linhas] == [("admin", None), ("ana@x.com", "ana@x.com")]


def _insere_com_email(conn: sqlite3.Connection, login: str, email: str) -> None:
    conn.execute(
        "INSERT INTO usuarios (login, nome, senha_hash, papel, situacao, created_at, email) "
        "VALUES (?, ?, 'hash', 'usuario', 'ativo', '2026-01-01T00:00:00+00:00', ?)",
        (login, login, email),
    )


def test_indice_impede_email_duplicado_sem_diferenciar_caixa(tmp_path: Path) -> None:
    db = tmp_path / "novo.db"
    init_db(db)
    with db_session(db) as conn:
        _insere_com_email(conn, "ana-login", "ana@x.com")
    with pytest.raises(sqlite3.IntegrityError):
        with db_session(db) as conn:
            _insere_com_email(conn, "outra-login", "ANA@x.com")


# ---------------------------------------------------------------- Fase 2: cadastro, login, perfil, admin

ADMIN = {"login": "admin", "senha": "senha-forte-1"}
SENHA = "cadastro-123"
MSG_CADASTRO = (
    "Cadastro enviado. Se este e-mail ainda não tinha conta, você poderá entrar quando o administrador aprovar. "
    "Se já tinha, entre com sua senha ou fale com o administrador."
)


@pytest.fixture(autouse=True)
def _zera_bloqueios():
    auth.limpar_falhas()
    yield
    auth.limpar_falhas()


def _app(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("PREPARO_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("PREPARO_ADMIN_LOGIN", ADMIN["login"])
    monkeypatch.setenv("PREPARO_ADMIN_SENHA", ADMIN["senha"])
    return create_app(dist_dir=tmp_path / "sem_dist")


def _entrar(app, login: str, senha: str) -> TestClient:
    c = TestClient(app)
    c.__enter__()
    assert c.post("/api/auth/login", json={"login": login, "senha": senha}).status_code == 200
    return c


def _cadastro(client: TestClient, email: str, senha: str = SENHA):
    return client.post(
        "/api/auth/cadastro",
        json={"email": email, "nome": "Pessoa", "senha": senha, "grau": "socio", "nucleo": "Bendito Filho"},
    )


def _novo(email: str, senha: str = SENHA) -> dict:
    return {"email": email, "nome": "Pessoa", "senha": senha, "papel": "usuario", "grau": "socio", "nucleo": "Bendito Filho"}


def _insere_conta_antiga(tmp_path: Path, login: str, senha: str) -> None:
    """Conta criada pelo esquema antigo: login livre, sem e-mail."""
    with db_session(tmp_path / "auth.db") as conn:
        conn.execute(
            "INSERT INTO usuarios (login, nome, senha_hash, papel, situacao, created_at, grau, nucleo) "
            "VALUES (?, ?, ?, 'usuario', 'ativo', ?, 'socio', 'Bendito Filho')",
            (login, login.title(), auth.hash_senha(senha), now_iso()),
        )


def _total_usuarios(tmp_path: Path) -> int:
    with db_session(tmp_path / "auth.db") as conn:
        return conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]


def _id_por_email(admin: TestClient, email: str) -> int:
    return next(u["id"] for u in admin.get("/api/usuarios").json() if u.get("email") == email)


def test_cadastro_com_email_entra_pelo_email_depois_de_aprovado(monkeypatch, tmp_path: Path) -> None:
    app = _app(monkeypatch, tmp_path)
    with TestClient(app) as publico:
        assert _cadastro(publico, "  Ana.Silva@X.com ").status_code == 201
        assert publico.post("/api/auth/login", json={"login": "ana.silva@x.com", "senha": SENHA}).status_code == 403
    admin = _entrar(app, ADMIN["login"], ADMIN["senha"])
    uid = _id_por_email(admin, "ana.silva@x.com")
    assert admin.patch(f"/api/usuarios/{uid}", json={"situacao": "ativo"}).status_code == 200
    with TestClient(app) as ana:
        entrou = ana.post("/api/auth/login", json={"login": "  ANA.silva@x.com ", "senha": SENHA})
        assert entrou.status_code == 200
        assert ana.get("/api/auth/me").json()["usuario"]["email"] == "ana.silva@x.com"


def test_conta_antiga_continua_entrando_pelo_login(monkeypatch, tmp_path: Path) -> None:
    app = _app(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _insere_conta_antiga(tmp_path, "joao", "antiga-senha-1")
        assert client.post("/api/auth/login", json={"login": "joao", "senha": "antiga-senha-1"}).status_code == 200


def test_cadastro_com_email_ja_usado_responde_igual_e_nao_cria_conta(monkeypatch, tmp_path: Path) -> None:
    app = _app(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert _cadastro(client, "carla@x.com").status_code == 201
        antes = _total_usuarios(tmp_path)
        repetido = _cadastro(client, "CARLA@x.com ")
        assert _total_usuarios(tmp_path) == antes
        novo = _cadastro(client, "nova@x.com")
        assert novo.status_code == 201
        assert (repetido.status_code, repetido.json()) == (novo.status_code, novo.json())
        assert repetido.json() == {"mensagem": MSG_CADASTRO}


def test_cadastro_recusa_email_invalido(monkeypatch, tmp_path: Path) -> None:
    with TestClient(_app(monkeypatch, tmp_path)) as client:
        for ruim in ("ana", "ana@", "ana@x", "ana b@x.com", "a" * 250 + "@x.com"):
            assert _cadastro(client, ruim).status_code == 422, ruim


def test_login_antigo_nao_colide_com_email_de_outra_pessoa(monkeypatch, tmp_path: Path) -> None:
    app = _app(monkeypatch, tmp_path)
    with TestClient(app) as client:
        _insere_conta_antiga(tmp_path, "maria", "antiga-senha-1")
        assert _cadastro(client, "maria@x.com", senha="nova-senha-1").status_code == 201
    admin = _entrar(app, ADMIN["login"], ADMIN["senha"])
    assert admin.patch(f"/api/usuarios/{_id_por_email(admin, 'maria@x.com')}", json={"situacao": "ativo"}).status_code == 200
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"login": "maria", "senha": "antiga-senha-1"}).status_code == 200
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"login": "maria@x.com", "senha": "nova-senha-1"}).status_code == 200
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"login": "maria", "senha": "nova-senha-1"}).status_code == 401


def test_trocar_proprio_email_exige_senha_e_recusa_email_de_outro(monkeypatch, tmp_path: Path) -> None:
    app = _app(monkeypatch, tmp_path)
    admin = _entrar(app, ADMIN["login"], ADMIN["senha"])
    assert admin.post("/api/usuarios", json=_novo("dora@x.com")).status_code == 201
    assert admin.post("/api/usuarios", json=_novo("ema@x.com")).status_code == 201
    dora = _entrar(app, "dora@x.com", SENHA)
    troca = {"email": "dora.nova@x.com"}
    assert dora.patch("/api/auth/perfil", json=troca).status_code == 400  # sem senha atual
    assert dora.patch("/api/auth/perfil", json={**troca, "senhaAtual": "errada-123"}).status_code == 400
    assert dora.patch("/api/auth/perfil", json={"email": "ema@x.com", "senhaAtual": SENHA}).status_code == 409
    ok = dora.patch("/api/auth/perfil", json={**troca, "senhaAtual": SENHA})
    assert ok.status_code == 200 and ok.json()["email"] == "dora.nova@x.com"
    _entrar(app, "dora.nova@x.com", SENHA)
    # a troca certa zerou o contador; 409 conta no limite de 5 por 15 min; a 6ª tentativa para de comparar
    for _ in range(5):
        assert dora.patch("/api/auth/perfil", json={"email": "ema@x.com", "senhaAtual": SENHA}).status_code == 409
    assert dora.patch("/api/auth/perfil", json={"email": "ema@x.com", "senhaAtual": SENHA}).status_code == 429


def test_senha_atual_errada_na_troca_de_email_conta_no_limite(monkeypatch, tmp_path: Path) -> None:
    app = _app(monkeypatch, tmp_path)
    admin = _entrar(app, ADMIN["login"], ADMIN["senha"])
    assert admin.post("/api/usuarios", json=_novo("fabio@x.com")).status_code == 201
    fabio = _entrar(app, "fabio@x.com", SENHA)
    for _ in range(5):
        assert fabio.patch("/api/auth/perfil", json={"email": "fabio.nova@x.com", "senhaAtual": "errada-123"}).status_code == 400
    # bloqueado: nem a senha certa é comparada na 6ª tentativa
    assert fabio.patch("/api/auth/perfil", json={"email": "fabio.nova@x.com", "senhaAtual": SENHA}).status_code == 429


def test_troca_bem_sucedida_zera_as_falhas_de_senha(monkeypatch, tmp_path: Path) -> None:
    app = _app(monkeypatch, tmp_path)
    admin = _entrar(app, ADMIN["login"], ADMIN["senha"])
    assert admin.post("/api/usuarios", json=_novo("gil@x.com")).status_code == 201
    gil = _entrar(app, "gil@x.com", SENHA)
    for _ in range(4):
        assert gil.patch("/api/auth/perfil", json={"email": "gil.nova@x.com", "senhaAtual": "errada-123"}).status_code == 400
    assert gil.patch("/api/auth/perfil", json={"email": "gil.nova@x.com", "senhaAtual": SENHA}).status_code == 200
    # a troca certa zerou o contador: 4 erros novos não chegam ao limite de 5
    for _ in range(4):
        assert gil.patch("/api/auth/perfil", json={"email": "gil.outra@x.com", "senhaAtual": "errada-123"}).status_code == 400
    assert gil.patch("/api/auth/perfil", json={"email": "gil.outra@x.com", "senhaAtual": SENHA}).status_code == 200


def test_admin_edita_email_e_login_de_conta_nova_acompanha(monkeypatch, tmp_path: Path) -> None:
    app = _app(monkeypatch, tmp_path)
    admin = _entrar(app, ADMIN["login"], ADMIN["senha"])
    uid = admin.post("/api/usuarios", json=_novo("lia@x.com")).json()["id"]
    res = admin.patch(f"/api/usuarios/{uid}", json={"email": "lia.nova@x.com"})
    assert res.status_code == 200
    assert res.json()["login"] == "lia.nova@x.com" and res.json()["email"] == "lia.nova@x.com"
    _entrar(app, "lia.nova@x.com", SENHA)
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"login": "lia@x.com", "senha": SENHA}).status_code == 401


def test_conta_antiga_ganha_email_e_entra_pelos_dois(monkeypatch, tmp_path: Path) -> None:
    app = _app(monkeypatch, tmp_path)
    admin = _entrar(app, ADMIN["login"], ADMIN["senha"])
    _insere_conta_antiga(tmp_path, "joao", "antiga-senha-1")
    uid = next(u["id"] for u in admin.get("/api/usuarios").json() if u["login"] == "joao")
    res = admin.patch(f"/api/usuarios/{uid}", json={"email": "joao@x.com"})
    assert res.status_code == 200 and res.json()["login"] == "joao"
    _entrar(app, "joao", "antiga-senha-1")
    _entrar(app, "joao@x.com", "antiga-senha-1")


def test_conta_anonimizada_libera_o_email_para_novo_cadastro(monkeypatch, tmp_path: Path) -> None:
    app = _app(monkeypatch, tmp_path)
    admin = _entrar(app, ADMIN["login"], ADMIN["senha"])
    uid = admin.post("/api/usuarios", json=_novo("rui@x.com")).json()["id"]
    rui = _entrar(app, "rui@x.com", SENHA)
    assert rui.post("/api/preparos", json={"nome": "Preparo do Rui"}).status_code == 201  # vínculo: vai anonimizar
    assert admin.delete(f"/api/usuarios/{uid}").json() == {"anonimizado": True}
    with TestClient(app) as publico:
        assert _cadastro(publico, "rui@x.com", senha="nova-senha-1").status_code == 201
    admin.patch(f"/api/usuarios/{_id_por_email(admin, 'rui@x.com')}", json={"situacao": "ativo"})
    _entrar(app, "rui@x.com", "nova-senha-1")


# ---------------------------------------------------------------- Fase 3: adicionar participante por e-mail

HDR = "X-Preparo-Id"
MSG_NAO_ENCONTRADO = (
    "Não encontramos uma pessoa cadastrada e ativa com esse e-mail. Confira o e-mail ou peça que ela se cadastre."
)


def _rascunho(litros: float) -> dict:
    return {
        "data": "2026-11-22",
        "blocos": [{"obs": "", "anotador": "", "data": "2026-11-22",
                    "panelas": [{"numero": 1, "tipo": "1ª vez", "entrada": "06:00", "litros": litros}]}],
    }


def _equipe_por_email(monkeypatch, tmp_path: Path):
    """Admin cria Maria (dona de um preparo) e João (ativo, sem vínculo)."""
    app = _app(monkeypatch, tmp_path)
    admin = _entrar(app, ADMIN["login"], ADMIN["senha"])
    for nome in ("maria", "joao"):
        assert admin.post("/api/usuarios", json=_novo(f"{nome}@x.com")).status_code == 201
    maria = _entrar(app, "maria@x.com", SENHA)
    joao = _entrar(app, "joao@x.com", SENHA)
    pid = maria.post("/api/preparos", json={"nome": "Bendito Filho"}).json()["id"]
    return app, admin, maria, joao, pid


def _adicionar(cliente: TestClient, pid: str, email: str):
    return cliente.post(f"/api/preparos/{pid}/membros", json={"email": email})


def test_dono_adiciona_pessoa_ativa_e_ela_atualiza_rascunho_e_registros(monkeypatch, tmp_path: Path) -> None:
    _, _, maria, joao, pid = _equipe_por_email(monkeypatch, tmp_path)
    h = {HDR: pid}
    assert joao.get("/api/registros", headers=h).status_code == 403
    assert _adicionar(maria, pid, "joao@x.com").status_code == 200
    assert joao.put("/api/rascunho", json=_rascunho(10), headers=h).status_code == 200
    novo = {"data": "2026-11-22", "blocos": _rascunho(10)["blocos"]}
    assert joao.post("/api/registros", json=novo, headers=h).status_code == 201
    assert joao.put("/api/config", json={"minSemFervura": 10}, headers=h).status_code == 200


def test_adicionar_email_inexistente_pendente_ou_inativo_da_a_mesma_resposta(monkeypatch, tmp_path: Path) -> None:
    app, admin, maria, _, pid = _equipe_por_email(monkeypatch, tmp_path)
    with TestClient(app) as publico:
        assert _cadastro(publico, "pendente@x.com").status_code == 201
    assert admin.post("/api/usuarios", json=_novo("inativo@x.com")).status_code == 201
    uid = _id_por_email(admin, "inativo@x.com")
    assert admin.patch(f"/api/usuarios/{uid}", json={"situacao": "inativo"}).status_code == 200
    respostas = [_adicionar(maria, pid, e) for e in ("ninguem@x.com", "pendente@x.com", "inativo@x.com")]
    assert all(r.status_code == 404 for r in respostas)
    assert len({r.text for r in respostas}) == 1
    assert respostas[0].json()["detail"] == MSG_NAO_ENCONTRADO


def test_so_o_dono_adiciona_participante(monkeypatch, tmp_path: Path) -> None:
    _, admin, maria, joao, pid = _equipe_por_email(monkeypatch, tmp_path)
    assert _adicionar(maria, pid, "joao@x.com").status_code == 200
    assert _adicionar(joao, pid, "maria@x.com").status_code == 403  # membro comum
    assert _adicionar(admin, pid, "joao@x.com").status_code == 403  # admin que não é dono


def test_adicionar_duas_vezes_e_idempotente(monkeypatch, tmp_path: Path) -> None:
    _, _, maria, _, pid = _equipe_por_email(monkeypatch, tmp_path)
    primeiro = _adicionar(maria, pid, "joao@x.com")
    segundo = _adicionar(maria, pid, "joao@x.com")
    assert primeiro.status_code == segundo.status_code == 200
    assert primeiro.json() == segundo.json()
    membros = maria.get(f"/api/preparos/{pid}/membros").json()
    assert sum(m["usuarioId"] == primeiro.json()["usuarioId"] for m in membros) == 1
    dono = _adicionar(maria, pid, "maria@x.com")  # o próprio dono: estado atual, sem mudança
    assert dono.status_code == 200
    assert (dono.json()["papel"], dono.json()["situacao"]) == ("dono", "aprovado")


def test_adicionar_quem_tinha_pedido_pendente_ou_recusado_aprova(monkeypatch, tmp_path: Path) -> None:
    app, admin, maria, joao, pid = _equipe_por_email(monkeypatch, tmp_path)
    assert admin.post("/api/usuarios", json=_novo("ana@x.com")).status_code == 201
    ana = _entrar(app, "ana@x.com", SENHA)
    h = {HDR: pid}

    joao.post(f"/api/preparos/{pid}/solicitar")  # pendente
    assert _adicionar(maria, pid, "joao@x.com").json()["situacao"] == "aprovado"
    assert joao.get("/api/registros", headers=h).status_code == 200

    ana.post(f"/api/preparos/{pid}/solicitar")
    ana_uid = next(m["usuarioId"] for m in maria.get(f"/api/preparos/{pid}/membros").json() if m["email"] == "ana@x.com")
    assert maria.patch(f"/api/preparos/{pid}/membros/{ana_uid}", json={"situacao": "recusado"}).status_code == 200
    assert ana.get("/api/registros", headers=h).status_code == 403
    assert _adicionar(maria, pid, "ana@x.com").json()["situacao"] == "aprovado"  # convite explícito do dono
    assert ana.get("/api/registros", headers=h).status_code == 200


def test_muitas_tentativas_falhas_de_adicionar_bloqueiam(monkeypatch, tmp_path: Path) -> None:
    _, _, maria, _, pid = _equipe_por_email(monkeypatch, tmp_path)
    for i in range(5):
        assert _adicionar(maria, pid, f"nao{i}@x.com").status_code == 404
    assert _adicionar(maria, pid, "joao@x.com").status_code == 429  # 6ª tentativa, mesmo com e-mail válido


def test_participante_removido_perde_acesso_na_hora(monkeypatch, tmp_path: Path) -> None:
    _, _, maria, joao, pid = _equipe_por_email(monkeypatch, tmp_path)
    h = {HDR: pid}
    uid = _adicionar(maria, pid, "joao@x.com").json()["usuarioId"]
    assert joao.get("/api/registros", headers=h).status_code == 200
    assert maria.patch(f"/api/preparos/{pid}/membros/{uid}", json={"situacao": "recusado"}).status_code == 200
    assert joao.get("/api/registros", headers=h).status_code == 403
    assert joao.put("/api/rascunho", json=_rascunho(10), headers=h).status_code == 403


def test_participante_nao_gerencia_membros(monkeypatch, tmp_path: Path) -> None:
    _, admin, maria, joao, pid = _equipe_por_email(monkeypatch, tmp_path)
    assert _adicionar(maria, pid, "joao@x.com").status_code == 200
    assert _adicionar(joao, pid, "ninguem@x.com").status_code == 403
    assert joao.get(f"/api/preparos/{pid}/membros").status_code == 403


# ---------------------------------------------------------------- corrida: checagem vê "vazio", o INSERT bate na restrição


class _Vazio:
    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _ConexaoComCorrida:
    """Imita outra requisição que gravou a linha entre a checagem e o INSERT: só a 1ª consulta que bate na marca
    responde 'vazio'. O INSERT seguinte cai na restrição real do banco."""

    def __init__(self, conn, marca: str) -> None:
        self._conn, self._marca, self._pendente = conn, marca, True

    def execute(self, sql, params=()):
        if self._pendente and self._marca in sql:
            self._pendente = False
            return _Vazio()
        return self._conn.execute(sql, params)

    def __getattr__(self, nome):
        return getattr(self._conn, nome)


def _com_corrida(db_session_original, marca: str):
    @contextmanager
    def _cega():
        with db_session_original() as conn:
            yield _ConexaoComCorrida(conn, marca)

    return _cega


def test_cadastro_em_corrida_responde_como_novo_cadastro_sem_500(monkeypatch, tmp_path: Path) -> None:
    app = _app(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert _cadastro(client, "carla@x.com").status_code == 201
        antes = _total_usuarios(tmp_path)
        original = rota_auth.db_session
        monkeypatch.setattr(rota_auth, "db_session", _com_corrida(original, "SELECT 1 FROM usuarios WHERE email = ? OR login = ?"))
        corrida = _cadastro(client, "carla@x.com")
    assert corrida.status_code == 201
    assert corrida.json() == {"mensagem": MSG_CADASTRO}
    assert _total_usuarios(tmp_path) == antes


def test_adicionar_membro_em_corrida_responde_como_ja_membro(monkeypatch, tmp_path: Path) -> None:
    _, admin, maria, joao, pid = _equipe_por_email(monkeypatch, tmp_path)
    assert _adicionar(maria, pid, "joao@x.com").status_code == 200
    original = rota_preparos.db_session
    monkeypatch.setattr(
        rota_preparos, "db_session", _com_corrida(original, "SELECT papel, situacao FROM preparo_membros")
    )
    corrida = _adicionar(maria, pid, "joao@x.com")
    assert corrida.status_code == 200
    assert (corrida.json()["papel"], corrida.json()["situacao"]) == ("membro", "aprovado")


# ---------------------------------------------------------------- lacunas: anonimizada, legado com "@", admin por e-mail, limite de senha


def test_adicionar_email_de_conta_anonimizada_da_o_mesmo_404_generico(monkeypatch, tmp_path: Path) -> None:
    app, admin, maria, _, pid = _equipe_por_email(monkeypatch, tmp_path)
    uid = admin.post("/api/usuarios", json=_novo("rita@x.com")).json()["id"]
    rita = _entrar(app, "rita@x.com", SENHA)
    assert rita.post("/api/preparos", json={"nome": "Preparo da Rita"}).status_code == 201  # vínculo: vai anonimizar
    assert admin.delete(f"/api/usuarios/{uid}").json() == {"anonimizado": True}
    anonimizada = _adicionar(maria, pid, "rita@x.com")
    inexistente = _adicionar(maria, pid, "ninguem@x.com")
    assert anonimizada.status_code == 404
    assert (anonimizada.status_code, anonimizada.json()) == (inexistente.status_code, inexistente.json())
    assert anonimizada.json()["detail"] == MSG_NAO_ENCONTRADO


def test_conta_antiga_com_arroba_no_login_ganha_email_e_entra_pelos_dois(monkeypatch, tmp_path: Path) -> None:
    db = tmp_path / "auth.db"
    with sqlite3.connect(db) as raw:  # banco de antes da coluna email, com o admin inicial cujo login é um e-mail
        raw.executescript(DDL_USUARIOS_ANTIGO)
        raw.execute(
            "INSERT INTO usuarios (login, nome, senha_hash, papel, situacao, created_at) "
            "VALUES ('dono@x.com', 'Dono', ?, 'admin', 'ativo', '2026-01-01T00:00:00+00:00')",
            (auth.hash_senha(ADMIN["senha"]),),
        )
    app = _app(monkeypatch, tmp_path)  # o startup roda a migração do backfill
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"login": "dono@x.com", "senha": ADMIN["senha"]}).status_code == 200
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"login": "  DONO@x.com ", "senha": ADMIN["senha"]}).status_code == 200
    with db_session(db) as conn:
        assert conn.execute("SELECT email FROM usuarios WHERE login = 'dono@x.com'").fetchone()[0] == "dono@x.com"


def test_admin_inicial_com_email_como_login_grava_a_coluna_email(monkeypatch, tmp_path: Path) -> None:
    db = tmp_path / "auth.db"
    monkeypatch.setenv("PREPARO_DB_PATH", str(db))
    monkeypatch.setenv("PREPARO_ADMIN_LOGIN", "Dono@X.com")
    monkeypatch.setenv("PREPARO_ADMIN_SENHA", ADMIN["senha"])
    init_db(db)
    auth.garantir_admin_inicial()
    with db_session(db) as conn:
        assert tuple(conn.execute("SELECT login, email FROM usuarios").fetchone()) == ("Dono@X.com", "dono@x.com")


def test_senha_atual_longa_demais_da_422_com_o_rotulo_do_campo(monkeypatch, tmp_path: Path) -> None:
    app = _app(monkeypatch, tmp_path)
    admin = _entrar(app, ADMIN["login"], ADMIN["senha"])
    assert admin.post("/api/usuarios", json=_novo("hana@x.com")).status_code == 201
    hana = _entrar(app, "hana@x.com", SENHA)
    res = hana.patch("/api/auth/perfil", json={"email": "hana.nova@x.com", "senhaAtual": "x" * 257})
    assert res.status_code == 422
    assert "Senha atual" in res.json()["detail"]
