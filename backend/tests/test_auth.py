"""Testes de login, sessões e gestão de usuários."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.database import db_session, init_db
from app.main import create_app

ADMIN = {"login": "admin", "senha": "senha-forte-1"}
GRAU_NUCLEO = {"grau": "socio", "nucleo": "Bendito Filho"}
HDR = "X-Preparo-Id"


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


def _mail(nome: str) -> str:
    """Identidade de teste: contas novas entram pelo e-mail derivado do nome."""
    return f"{nome}@x.com"


def _login(client: TestClient, login: str, senha: str):
    identificador = login if login.lower() == ADMIN["login"] else _mail(login)
    return client.post("/api/auth/login", json={"login": identificador, "senha": senha})


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
        novo = {"email": "maria@x.com", "nome": "Maria", "senha": "maria-senha-1", "papel": "usuario", **GRAU_NUCLEO}
        criado = admin_client.post("/api/usuarios", json=novo)
        assert criado.status_code == 201
        assert "senha" not in criado.json() and "senhaHash" not in criado.json()
        repetido = admin_client.post("/api/usuarios", json=novo)
        assert repetido.status_code == 409  # e-mail repetido
        assert repetido.json()["detail"] == "Este e-mail já está em uso por outra conta."

        with TestClient(admin_client.app) as comum:
            assert _login(comum, "maria", "maria-senha-1").status_code == 200
            assert comum.get("/api/preparos").status_code == 200  # dados compartilhados
            assert comum.get("/api/usuarios").status_code == 403
            assert comum.post("/api/usuarios", json=novo).status_code == 403


def test_senha_curta_e_papel_invalido_sao_rejeitados(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        _login(client, **ADMIN)
        base = {"email": "joao@x.com", "nome": "João", "senha": "joao-senha-1", "papel": "usuario", **GRAU_NUCLEO}
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


def test_admin_nao_rebaixa_nem_desativa_a_si_mesmo_mesmo_com_outro_admin(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        meu_id = _login(client, **ADMIN).json()["usuario"]["id"]
        segundo = client.post(
            "/api/usuarios",
            json={"email": "outro_admin@x.com", "nome": "Outro", "senha": "outro-senha-1", "papel": "admin", **GRAU_NUCLEO},
        )
        assert segundo.status_code == 201
        assert client.patch(f"/api/usuarios/{meu_id}", json={"papel": "usuario"}).status_code == 400
        assert client.patch(f"/api/usuarios/{meu_id}", json={"situacao": "inativo"}).status_code == 400
        eu = client.get("/api/auth/me").json()["usuario"]
        assert (eu["papel"], eu["situacao"]) == ("admin", "ativo")
        assert client.patch(f"/api/usuarios/{meu_id}", json={"nome": "Admin Novo"}).status_code == 200
        assert client.patch(f"/api/usuarios/{meu_id}", json={"papel": "admin", "situacao": "ativo"}).status_code == 200


def test_usuario_desativado_perde_a_sessao_e_nao_loga(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin_client:
        _login(admin_client, **ADMIN)
        uid = admin_client.post(
            "/api/usuarios",
            json={"email": "ana@x.com", "nome": "Ana", "senha": "ana-senha-123", "papel": "usuario", **GRAU_NUCLEO},
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
            json={"email": "leo@x.com", "nome": "Leo", "senha": "leo-senha-123", "papel": "usuario", **GRAU_NUCLEO},
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


def _cadastro(client: TestClient, nome_teste: str, senha: str = "cadastro-123", nome: str = "Pessoa"):
    return client.post("/api/auth/cadastro", json={"email": _mail(nome_teste), "nome": nome, "senha": senha})


def test_cadastro_fica_pendente_e_so_entra_depois_de_aprovado(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin, TestClient(_client(monkeypatch, tmp_path).app) as novo:
        _login(admin, **ADMIN)
        res = _cadastro(novo, "carla", nome="Carla")
        assert res.status_code == 201
        assert '"senha' not in res.text and "hash" not in res.text.lower()  # a mensagem fala em "senha", sem expor campo
        assert novo.get("/api/preparos").status_code == 401  # cadastro não abre sessão

        pendente = _login(novo, "carla", "cadastro-123")
        assert pendente.status_code == 403
        assert "aprova" in pendente.json()["detail"].lower()
        assert _login(novo, "carla", "senha-errada-1").status_code == 401  # senha errada continua genérica

        lista = admin.get("/api/usuarios").json()
        carla = next(u for u in lista if u["email"] == _mail("carla"))
        assert carla["situacao"] == "pendente"
        assert admin.patch(f"/api/usuarios/{carla['id']}", json={"situacao": "ativo"}).status_code == 200
        assert _login(novo, "carla", "cadastro-123").status_code == 200


def test_cadastro_rejeita_senha_curta_e_excesso_de_pendentes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(auth, "MAX_PENDENTES", 2)
    with _client(monkeypatch, tmp_path) as client:
        assert _cadastro(client, "dani", senha="curta").status_code == 422
        assert _cadastro(client, "pa1").status_code == 201
        assert _cadastro(client, "pa2").status_code == 201
        assert _cadastro(client, "pa3").status_code == 429  # limite de contas pendentes


def test_cadastro_nao_deixa_escolher_papel(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin, TestClient(_client(monkeypatch, tmp_path).app) as novo:
        novo.post(
            "/api/auth/cadastro",
            json={"email": "intruso@x.com", "nome": "X", "senha": "intruso-123", "papel": "admin", "situacao": "ativo"},
        )
        _login(admin, **ADMIN)
        u = next(u for u in admin.get("/api/usuarios").json() if u["email"] == "intruso@x.com")
        assert (u["papel"], u["situacao"]) == ("usuario", "pendente")


def _cadastro_completo(client: TestClient, login: str, **extra):
    corpo = {"email": _mail(login), "nome": "Pessoa", "senha": "cadastro-123", "grau": "mestre", "nucleo": "Bendito Filho"}
    return client.post("/api/auth/cadastro", json={**corpo, **extra})


def test_cadastro_grava_grau_e_nucleo_e_fica_pendente(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin, TestClient(_client(monkeypatch, tmp_path).app) as novo:
        _login(admin, **ADMIN)
        assert _cadastro_completo(novo, "rita", nome="Rita").status_code == 201
        rita = next(u for u in admin.get("/api/usuarios").json() if u["email"] == "rita@x.com")
        assert (rita["situacao"], rita["grau"], rita["nucleo"]) == ("pendente", "mestre", "Bendito Filho")
        assert "senha_hash" not in rita and "senhaHash" not in rita


def test_cadastro_sem_grau_e_nucleo_continua_aceito_para_pwa_antigo(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin, TestClient(_client(monkeypatch, tmp_path).app) as novo:
        _login(admin, **ADMIN)
        assert _cadastro(novo, "velha01").status_code == 201
        antiga = next(u for u in admin.get("/api/usuarios").json() if u["email"] == _mail("velha01"))
        assert (antiga["grau"], antiga["nucleo"]) == ("", "")


def test_cadastro_valida_grau_nucleo_e_login_reservado(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        assert _cadastro_completo(client, "tiago", grau="rei").status_code == 422
        assert _cadastro_completo(client, "tiago", grau="").status_code == 422
        assert _cadastro_completo(client, "tiago", nucleo="   ").status_code == 422
        assert _cadastro_completo(client, "tiago", nucleo="x" * 81).status_code == 422
        assert _cadastro_completo(client, "removido-7").status_code == 422


def test_erro_de_validacao_vem_em_portugues_por_campo_sem_ecoar_a_senha(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        res = client.post(
            "/api/auth/cadastro",
            json={"email": "a b", "nome": "Pessoa", "senha": "abc-9"},
        )
        assert res.status_code == 422
        detalhe = res.json()["detail"]
        assert isinstance(detalhe, str)
        assert "Senha" in detalhe and "Informe um e-mail válido." in detalhe
        assert "abc-9" not in res.text
        assert "input" not in res.text and "pydantic" not in res.text.lower()


def test_cadastro_limita_cinco_por_ip_a_cada_quinze_minutos(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        for i in range(5):
            assert _cadastro(client, f"usr{i:02d}").status_code == 201
        assert _cadastro(client, "usr09").status_code == 429
        # o último IP do X-Forwarded-For é o que o proxy acrescenta: outro cliente segue livre
        outro = client.post(
            "/api/auth/cadastro",
            json={"email": "outra01@x.com", "nome": "Outra", "senha": "cadastro-123"},
            headers={"X-Forwarded-For": "10.0.0.1, 203.0.113.9"},
        )
        assert outro.status_code == 201


def test_limite_de_cadastros_nao_se_burla_trocando_o_primeiro_ip_do_cabecalho(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        for i in range(5):
            res = client.post(
                "/api/auth/cadastro",
                json={"email": f"rot{i:02d}@x.com", "nome": "Pessoa", "senha": "cadastro-123"},
                headers={"X-Forwarded-For": f"198.51.100.{i + 1}, 203.0.113.7"},
            )
            assert res.status_code == 201
        sexto = client.post(
            "/api/auth/cadastro",
            json={"email": "rot09@x.com", "nome": "Pessoa", "senha": "cadastro-123"},
            headers={"X-Forwarded-For": "192.0.2.99, 203.0.113.7"},
        )
        assert sexto.status_code == 429


def test_me_traz_pendentes_so_para_admin(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin:
        _login(admin, **ADMIN)
        _cadastro(admin, "pend01")
        assert admin.get("/api/auth/me").json()["cadastrosPendentes"] == 1
        _novo_usuario(admin, "comum01")
        with TestClient(admin.app) as comum:
            _login(comum, "comum01", "comum01-senha-1")
            corpo = comum.get("/api/auth/me").json()
            assert "cadastrosPendentes" not in corpo
            assert (corpo["usuario"]["grau"], corpo["usuario"]["nucleo"]) == ("socio", "Bendito Filho")
            assert "senha_hash" not in corpo["usuario"]


def _novo_usuario(client: TestClient, login: str):
    return client.post(
        "/api/usuarios",
        json={"email": _mail(login), "nome": login.title(), "senha": f"{login}-senha-1", "papel": "usuario", **GRAU_NUCLEO},
    )


def test_admin_cria_usuario_com_grau_e_nucleo_obrigatorios(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        _login(client, **ADMIN)
        base = {"email": "dani@x.com", "nome": "Dani", "senha": "dani-senha-1", "papel": "usuario"}
        assert client.post("/api/usuarios", json=base).status_code == 422  # sem grau nem núcleo
        assert client.post("/api/usuarios", json={**base, **GRAU_NUCLEO, "grau": ""}).status_code == 422
        assert client.post("/api/usuarios", json={**base, **GRAU_NUCLEO, "email": "removido-3@x.com"}).status_code == 422
        criado = client.post("/api/usuarios", json={**base, **GRAU_NUCLEO})
        assert criado.status_code == 201
        assert (criado.json()["grau"], criado.json()["nucleo"]) == ("socio", "Bendito Filho")


def test_admin_edita_grau_e_nucleo(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as client:
        _login(client, **ADMIN)
        uid = _novo_usuario(client, "eva").json()["id"]
        res = client.patch(f"/api/usuarios/{uid}", json={"grau": "conselho", "nucleo": "Outro"})
        assert res.status_code == 200
        assert (res.json()["grau"], res.json()["nucleo"]) == ("conselho", "Outro")
        assert client.patch(f"/api/usuarios/{uid}", json={"grau": "rei"}).status_code == 422


def test_perfil_altera_nome_grau_e_nucleo_sem_mudar_papel_ou_situacao(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin:
        _login(admin, **ADMIN)
        _novo_usuario(admin, "lia")
        with TestClient(admin.app) as lia:
            assert lia.patch("/api/auth/perfil", json={"nome": "X"}).status_code == 401
            _login(lia, "lia", "lia-senha-1")
            res = lia.patch(
                "/api/auth/perfil",
                json={"nome": "Lia Souza", "grau": "conselho", "nucleo": "Outro", "papel": "admin", "situacao": "inativo"},
            )
            assert res.status_code == 200
            assert res.json()["nome"] == "Lia Souza" and res.json()["grau"] == "conselho"
            eu = lia.get("/api/auth/me").json()["usuario"]
            assert (eu["papel"], eu["situacao"], eu["nucleo"]) == ("usuario", "ativo", "Outro")
            assert lia.patch("/api/auth/perfil", json={"nome": "   "}).status_code == 422


def test_excluir_usuario_respeita_as_regras(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin:
        meu_id = _login(admin, **ADMIN).json()["usuario"]["id"]
        uid = _novo_usuario(admin, "caio").json()["id"]
        assert admin.delete(f"/api/usuarios/{meu_id}").status_code == 400  # a si mesmo
        assert admin.delete("/api/usuarios/9999").status_code == 404
        with TestClient(admin.app) as comum:
            _login(comum, "caio", "caio-senha-1")
            assert comum.delete(f"/api/usuarios/{meu_id}").status_code == 403


def test_excluir_sem_vinculo_apaga_a_linha_e_derruba_a_sessao(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin:
        _login(admin, **ADMIN)
        uid = _novo_usuario(admin, "bruno").json()["id"]
        with TestClient(admin.app) as bruno:
            _login(bruno, "bruno", "bruno-senha-1")
            assert admin.delete(f"/api/usuarios/{uid}").json() == {"anonimizado": False}
            assert bruno.get("/api/auth/me").status_code == 401
            assert all(u["id"] != uid for u in admin.get("/api/usuarios").json())
            assert admin.delete(f"/api/usuarios/{uid}").status_code == 404


def test_excluir_com_vinculo_anonimiza_e_mantem_o_historico(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin:
        _login(admin, **ADMIN)
        uid = _novo_usuario(admin, "bia").json()["id"]
        with TestClient(admin.app) as bia:
            _login(bia, "bia", "bia-senha-1")
            assert bia.post("/api/preparos", json={"nome": "Preparo da Bia"}).status_code == 201

            assert admin.delete(f"/api/usuarios/{uid}").json() == {"anonimizado": True}
            assert bia.get("/api/auth/me").status_code == 401
            with TestClient(admin.app) as nova_sessao:
                assert _login(nova_sessao, "bia", "bia-senha-1").status_code == 401
            lista = admin.get("/api/usuarios").json()
            assert all(u["id"] != uid for u in lista)
            assert all(u["email"] != "bia@x.com" and "bia" not in u["nome"].lower() for u in lista)

            preparos = admin.get("/api/preparos").json()
            assert preparos and preparos[0]["donoNome"] == "Usuário removido"
            assert admin.delete(f"/api/usuarios/{uid}").status_code == 404
            assert admin.patch(f"/api/usuarios/{uid}", json={"situacao": "ativo"}).status_code == 404


def _membro_aprovado(admin: TestClient, pid: str, login: str) -> int:
    """Cria a conta, pede entrada no preparo e o dono aprova. Devolve o id do usuário."""
    uid = _novo_usuario(admin, login).json()["id"]
    with TestClient(admin.app) as membro:
        _login(membro, login, f"{login}-senha-1")
        assert membro.post(f"/api/preparos/{pid}/solicitar").status_code == 200
    body = {"situacao": "aprovado", "permissao": "editar"}
    assert admin.patch(f"/api/preparos/{pid}/membros/{uid}", json=body).status_code == 200
    return uid


def _preparo_com_membro(admin: TestClient, login: str) -> tuple[str, int]:
    _login(admin, **ADMIN)
    pid = admin.post("/api/preparos", json={"nome": "Preparo da equipe"}).json()["id"]
    return pid, _membro_aprovado(admin, pid, login)


def test_anonimizar_troca_o_nome_do_autor_dentro_do_rascunho(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin:
        pid, uid = _preparo_com_membro(admin, "tais")
        with TestClient(admin.app) as tais:
            _login(tais, "tais", "tais-senha-1")
            rascunho = {"nucleo": "Bendito Filho", "data": "2026-11-22", "blocos": [{"obs": "Bloco piloto", "panelas": []}]}
            assert tais.put("/api/rascunho", json=rascunho, headers={HDR: pid}).status_code == 200
            assert tais.get("/api/rascunho", headers={HDR: pid}).json()["blocos"][0]["autoria"]["criadoPorNome"] == "Tais"

        assert admin.delete(f"/api/usuarios/{uid}").json() == {"anonimizado": True}
        atual = admin.get("/api/rascunho", headers={HDR: pid})
        assert atual.status_code == 200
        assert atual.json()["blocos"][0]["autoria"]["criadoPorNome"] == "Usuário removido"
        assert "Tais" not in atual.text


@pytest.mark.parametrize("payload_ruim", ["{quebrado", "[1, 2]", '{"blocos": "nao-e-lista"}'])
def test_rascunho_com_payload_invalido_nao_impede_a_anonimizacao(monkeypatch, tmp_path: Path, payload_ruim: str) -> None:
    with _client(monkeypatch, tmp_path) as admin:
        pid, uid = _preparo_com_membro(admin, "rui")
        with TestClient(admin.app) as rui:
            _login(rui, "rui", "rui-senha-1")
            assert rui.put("/api/rascunho", json={"nucleo": "Bendito Filho", "blocos": []}, headers={HDR: pid}).status_code == 200
        with db_session(tmp_path / "auth.db") as conn:
            conn.execute("UPDATE rascunhos SET payload_json = ? WHERE preparo_id = ?", (payload_ruim, pid))

        assert admin.delete(f"/api/usuarios/{uid}").status_code == 200
        assert admin.delete(f"/api/usuarios/{uid}").status_code == 404  # confirma que a conta foi anonimizada


def test_anonimizar_troca_a_autoria_de_registros_e_blocos(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin:
        pid, uid = _preparo_com_membro(admin, "lara")
        with TestClient(admin.app) as lara:
            _login(lara, "lara", "lara-senha-1")
            corpo = {"nucleo": "Bendito Filho", "data": "2026-11-22", "blocos": [{"obs": "Bloco piloto", "panelas": []}]}
            criado = lara.post("/api/registros", json=corpo, headers={HDR: pid})
            assert criado.status_code == 201
            reg_id = criado.json()["id"]
            editado = {**corpo, "blocos": [{"obs": "Bloco revisado", "panelas": []}]}
            assert lara.put(f"/api/registros/{reg_id}", json=editado, headers={HDR: pid}).status_code == 200

        assert admin.delete(f"/api/usuarios/{uid}").json() == {"anonimizado": True}
        reg = admin.get(f"/api/registros/{reg_id}", headers={HDR: pid}).json()
        assert reg["criadoPor"]["nome"] == "Usuário removido"
        assert reg["atualizadoPor"]["nome"] == "Usuário removido"
        bloco = reg["blocos"][0]["autoria"]
        assert (bloco["criadoPorNome"], bloco["editadoPorNome"]) == ("Usuário removido", "Usuário removido")


def test_membro_sem_ser_dono_e_anonimizado_e_nao_apagado(monkeypatch, tmp_path: Path) -> None:
    with _client(monkeypatch, tmp_path) as admin:
        pid, uid = _preparo_com_membro(admin, "moa")
        assert admin.delete(f"/api/usuarios/{uid}").json() == {"anonimizado": True}
        membros = admin.get(f"/api/preparos/{pid}/membros").json()
        assert [m["nome"] for m in membros if m["usuarioId"] == uid] == ["Usuário removido"]


def test_migracao_acrescenta_grau_e_nucleo_sem_perder_usuarios(tmp_path: Path) -> None:
    caminho = tmp_path / "antigo.db"
    antigo = sqlite3.connect(caminho)
    antigo.execute(
        "CREATE TABLE usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "login TEXT NOT NULL UNIQUE COLLATE NOCASE, nome TEXT NOT NULL, senha_hash TEXT NOT NULL, "
        "papel TEXT NOT NULL CHECK (papel IN ('admin', 'usuario')), "
        "situacao TEXT NOT NULL DEFAULT 'pendente' CHECK (situacao IN ('pendente', 'ativo', 'inativo')), "
        "created_at TEXT NOT NULL)"
    )
    antigo.execute(
        "INSERT INTO usuarios (login, nome, senha_hash, papel, situacao, created_at) "
        "VALUES ('velho', 'Velho', 'x', 'usuario', 'ativo', '2025-01-01')"
    )
    antigo.commit()
    antigo.close()

    init_db(caminho)
    init_db(caminho)  # segunda subida não quebra

    with db_session(caminho) as conn:
        row = conn.execute("SELECT login, nome, grau, nucleo FROM usuarios").fetchone()
    assert (row["login"], row["nome"], row["grau"], row["nucleo"]) == ("velho", "Velho", "", "")
