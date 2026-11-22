"""Testes de login, sessões e gestão de usuários."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import create_app

ADMIN = {"login": "admin", "senha": "senha-forte-1"}


@pytest.fixture(autouse=True)
def _zera_bloqueios():
    auth.limpar_falhas()
    yield
    auth.limpar_falhas()


def _client(monkeypatch, tmp_path: Path, **env: str) -> TestClient:
    monkeypatch.setenv("PREPARO_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("PREPARO_ADMIN_LOGIN", ADMIN["login"])
    monkeypatch.setenv("PREPARO_ADMIN_SENHA", ADMIN["senha"])
    for chave, valor in env.items():
        monkeypatch.setenv(chave, valor)
    # cookie Secure só é reenviado por HTTPS, como nos navegadores
    base = "https://testserver" if env.get("PREPARO_COOKIE_SECURE") else "http://testserver"
    return TestClient(create_app(dist_dir=tmp_path / "sem_dist"), base_url=base)


def _login(client: TestClient, login: str, senha: str):
    return client.post("/api/auth/login", json={"login": login, "senha": senha})


def test_hash_nao_guarda_senha_em_texto_puro_e_verifica() -> None:
    h1, h2 = auth.hash_senha("minha-senha-1"), auth.hash_senha("minha-senha-1")
    assert "minha-senha-1" not in h1
    assert h1 != h2  # sal diferente a cada hash
    assert auth.verificar_senha("minha-senha-1", h1)
    assert not auth.verificar_senha("outra-senha-1", h1)
    assert not auth.verificar_senha("x", "lixo-que-nao-e-hash")


def test_rotas_exigem_login_mas_health_fica_publico(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        assert client.get("/api/health").status_code == 200
        for rota in ("/api/preparos", "/api/registros", "/api/rascunho", "/api/lembretes", "/api/config", "/api/stats/summary"):
            assert client.get(rota).status_code == 401, rota
        assert client.get("/api/auth/me").status_code == 401


def test_login_errado_nao_revela_se_o_usuario_existe(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        senha_errada = _login(client, "admin", "senha-errada-1")
        inexistente = _login(client, "fulano", "senha-errada-1")
        assert senha_errada.status_code == inexistente.status_code == 401
        assert senha_errada.json() == inexistente.json()


def test_login_ok_define_cookie_seguro_e_libera_a_api(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path, PREPARO_COOKIE_SECURE="1") as client:
        res = _login(client, "ADMIN", ADMIN["senha"])  # login não diferencia maiúsculas
        assert res.status_code == 200
        assert res.json()["usuario"]["papel"] == "admin"
        assert "senha" not in res.text and "hash" not in res.text.lower()
        cookie = res.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie and "secure" in cookie
        assert client.get("/api/preparos").status_code == 200
        assert client.get("/api/auth/me").json()["usuario"]["login"] == "admin"


def test_logout_revoga_a_sessao_no_servidor(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        _login(client, **ADMIN)
        token = client.cookies.get(auth.COOKIE_SESSAO)
        assert token
        assert client.post("/api/auth/logout").status_code == 200
        client.cookies.set(auth.COOKIE_SESSAO, token)  # reapresenta o cookie antigo
        assert client.get("/api/preparos").status_code == 401


def test_bloqueia_apos_cinco_senhas_erradas(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        for _ in range(5):
            assert _login(client, "admin", "errada-123").status_code == 401
        assert _login(client, **ADMIN).status_code == 429  # nem a senha certa passa


def test_admin_cria_usuario_e_usuario_comum_nao_gerencia(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin_client:
        _login(admin_client, **ADMIN)
        novo = {"login": "maria", "nome": "Maria", "senha": "maria-senha-1", "papel": "usuario"}
        criado = admin_client.post("/api/usuarios", json=novo)
        assert criado.status_code == 201
        assert "senha" not in criado.json() and "senhaHash" not in criado.json()
        assert admin_client.post("/api/usuarios", json=novo).status_code == 409  # login repetido

        with TestClient(admin_client.app) as comum:
            assert _login(comum, "maria", "maria-senha-1").status_code == 200
            assert comum.get("/api/preparos").status_code == 200  # dados compartilhados
            assert comum.get("/api/usuarios").status_code == 403
            assert comum.post("/api/usuarios", json=novo).status_code == 403


def test_senha_curta_e_papel_invalido_sao_rejeitados(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        _login(client, **ADMIN)
        base = {"login": "joao", "nome": "João", "senha": "joao-senha-1", "papel": "usuario"}
        assert client.post("/api/usuarios", json={**base, "senha": "curta"}).status_code == 422
        assert client.post("/api/usuarios", json={**base, "papel": "root"}).status_code == 422


def test_trocar_senha_exige_a_atual_e_derruba_as_outras_sessoes(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as a, TestClient(_client(monkeypatch, tmp_path).app) as b:
        _login(a, **ADMIN)
        _login(b, **ADMIN)
        erro = a.post("/api/auth/senha", json={"senhaAtual": "errada-123", "novaSenha": "nova-senha-123"})
        assert erro.status_code == 400
        ok = a.post("/api/auth/senha", json={"senhaAtual": ADMIN["senha"], "novaSenha": "nova-senha-123"})
        assert ok.status_code == 200
        assert a.get("/api/preparos").status_code == 200  # a sessão atual continua
        assert b.get("/api/preparos").status_code == 401  # a do outro aparelho caiu
        assert _login(a, "admin", ADMIN["senha"]).status_code == 401
        assert _login(a, "admin", "nova-senha-123").status_code == 200


def test_nao_deixa_o_sistema_sem_administrador(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        meu_id = _login(client, **ADMIN).json()["usuario"]["id"]
        assert client.patch(f"/api/usuarios/{meu_id}", json={"situacao": "inativo"}).status_code == 400
        assert client.patch(f"/api/usuarios/{meu_id}", json={"papel": "usuario"}).status_code == 400


def test_usuario_desativado_perde_a_sessao_e_nao_loga(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin_client:
        _login(admin_client, **ADMIN)
        uid = admin_client.post(
            "/api/usuarios",
            json={"login": "ana", "nome": "Ana", "senha": "ana-senha-123", "papel": "usuario"},
        ).json()["id"]
        with TestClient(admin_client.app) as ana:
            _login(ana, "ana", "ana-senha-123")
            assert ana.get("/api/preparos").status_code == 200
            assert admin_client.patch(f"/api/usuarios/{uid}", json={"situacao": "inativo"}).status_code == 200
            assert ana.get("/api/preparos").status_code == 401
            assert _login(ana, "ana", "ana-senha-123").status_code == 401


def test_admin_redefine_senha_de_outro_usuario(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        _login(client, **ADMIN)
        uid = client.post(
            "/api/usuarios",
            json={"login": "leo", "nome": "Leo", "senha": "leo-senha-123", "papel": "usuario"},
        ).json()["id"]
        assert client.patch(f"/api/usuarios/{uid}", json={"senha": "leo-nova-123"}).status_code == 200
        with TestClient(client.app) as leo:
            assert _login(leo, "leo", "leo-senha-123").status_code == 401
            assert _login(leo, "leo", "leo-nova-123").status_code == 200


def test_admin_inicial_so_e_criado_com_o_banco_sem_usuarios(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        assert _login(client, **ADMIN).status_code == 200
    # reinicia com outra senha no ambiente: não pode sobrescrever nem criar outro admin
    with _client(monkeypatch, tmp_path, PREPARO_ADMIN_SENHA="outra-senha-999") as client:
        assert _login(client, "admin", "outra-senha-999").status_code == 401
        assert _login(client, **ADMIN).status_code == 200


def test_cabecalhos_de_seguranca_e_cors_fechado_por_padrao(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        res = client.get("/api/health", headers={"Origin": "https://site-malicioso.example"})
        assert res.headers["x-content-type-options"] == "nosniff"
        assert res.headers["x-frame-options"] == "DENY"
        assert res.headers["referrer-policy"] == "same-origin"
        assert "access-control-allow-origin" not in res.headers


def test_cors_so_libera_origens_configuradas(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path, PREPARO_CORS_ORIGINS="https://app.exemplo.com") as client:
        ok = client.get("/api/health", headers={"Origin": "https://app.exemplo.com"})
        assert ok.headers["access-control-allow-origin"] == "https://app.exemplo.com"
        outra = client.get("/api/health", headers={"Origin": "https://site-malicioso.example"})
        assert "access-control-allow-origin" not in outra.headers


def _cadastro(client: TestClient, login: str, senha: str = "cadastro-123", nome: str = "Pessoa"):
    return client.post("/api/auth/cadastro", json={"login": login, "nome": nome, "senha": senha})


def test_cadastro_fica_pendente_e_so_entra_depois_de_aprovado(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin, TestClient(_client(monkeypatch, tmp_path).app) as novo:
        _login(admin, **ADMIN)
        res = _cadastro(novo, "carla", nome="Carla")
        assert res.status_code == 201
        assert "senha" not in res.text and "hash" not in res.text.lower()
        assert novo.get("/api/preparos").status_code == 401  # cadastro não abre sessão

        pendente = _login(novo, "carla", "cadastro-123")
        assert pendente.status_code == 403
        assert "aprova" in pendente.json()["detail"].lower()
        assert _login(novo, "carla", "senha-errada-1").status_code == 401  # senha errada continua genérica

        lista = admin.get("/api/usuarios").json()
        carla = next(u for u in lista if u["login"] == "carla")
        assert carla["situacao"] == "pendente"
        assert admin.patch(f"/api/usuarios/{carla['id']}", json={"situacao": "ativo"}).status_code == 200
        assert _login(novo, "carla", "cadastro-123").status_code == 200


def test_cadastro_rejeita_login_repetido_senha_curta_e_excesso_de_pendentes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(auth, "MAX_PENDENTES", 2)
    with _client(monkeypatch, tmp_path) as client:
        assert _cadastro(client, "admin").status_code == 409  # login já existe
        assert _cadastro(client, "dani", senha="curta").status_code == 422
        assert _cadastro(client, "pa1").status_code == 201
        assert _cadastro(client, "pa2").status_code == 201
        assert _cadastro(client, "pa3").status_code == 429  # limite de contas pendentes
        assert _cadastro(client, "PA1").status_code == 409  # login não diferencia maiúsculas


def test_cadastro_nao_deixa_escolher_papel(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin, TestClient(_client(monkeypatch, tmp_path).app) as novo:
        novo.post(
            "/api/auth/cadastro",
            json={"login": "intruso", "nome": "X", "senha": "intruso-123", "papel": "admin", "situacao": "ativo"},
        )
        _login(admin, **ADMIN)
        u = next(u for u in admin.get("/api/usuarios").json() if u["login"] == "intruso")
        assert (u["papel"], u["situacao"]) == ("usuario", "pendente")
