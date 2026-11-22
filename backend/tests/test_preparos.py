"""Testes de preparos, membros, aprovação do dono e acesso aos dados."""

from pathlib import Path

from fastapi.testclient import TestClient

from app import auth
from app.main import create_app

ADMIN = {"login": "admin", "senha": "senha-forte-1"}
HDR = "X-Preparo-Id"


def _app(monkeypatch, tmp_path: Path):
    auth.limpar_falhas()
    monkeypatch.setenv("PREPARO_DB_PATH", str(tmp_path / "preparos.db"))
    monkeypatch.setenv("PREPARO_ADMIN_LOGIN", ADMIN["login"])
    monkeypatch.setenv("PREPARO_ADMIN_SENHA", ADMIN["senha"])
    return create_app(dist_dir=tmp_path / "sem_dist")


def _entrar(app, login: str, senha: str) -> TestClient:
    c = TestClient(app)
    c.__enter__()
    assert c.post("/api/auth/login", json={"login": login, "senha": senha}).status_code == 200
    return c


def _equipe(monkeypatch, tmp_path: Path):
    """Admin + Maria (dona de um preparo) + João (sem vínculo), todos ativos e logados."""
    app = _app(monkeypatch, tmp_path)
    with TestClient(app) as boot:  # sobe o app e cria o admin
        boot.post("/api/auth/login", json=ADMIN)
        for login, nome in (("maria", "Maria"), ("joao", "João")):
            r = boot.post("/api/usuarios", json={"login": login, "nome": nome, "senha": f"{login}-senha-1", "papel": "usuario"})
            assert r.status_code == 201
    maria = _entrar(app, "maria", "maria-senha-1")
    joao = _entrar(app, "joao", "joao-senha-1")
    prep = maria.post("/api/preparos", json={"nome": "Bendito Filho"})
    assert prep.status_code == 201
    return maria, joao, prep.json()["id"]


def test_quem_cria_o_preparo_vira_dono_e_acessa_os_dados(monkeypatch, tmp_path: Path) -> None:
    maria, _, pid = _equipe(monkeypatch, tmp_path)
    meus = [p for p in maria.get("/api/preparos").json() if p["minhaSituacao"] == "aprovado"]
    assert [(p["id"], p["meuPapel"]) for p in meus] == [(pid, "dono")]
    assert maria.get("/api/registros", headers={HDR: pid}).status_code == 200


def test_acesso_aos_dados_exige_preparo_escolhido_e_vinculo_aprovado(monkeypatch, tmp_path: Path) -> None:
    maria, joao, pid = _equipe(monkeypatch, tmp_path)
    assert maria.get("/api/registros").status_code == 400  # sem escolher preparo
    assert joao.get("/api/registros", headers={HDR: pid}).status_code == 403  # sem vínculo
    assert maria.get("/api/registros", headers={HDR: "inexistente"}).status_code == 403  # mesmo erro: não revela se existe


def test_pedido_de_entrada_so_vale_depois_que_o_dono_aprova(monkeypatch, tmp_path: Path) -> None:
    maria, joao, pid = _equipe(monkeypatch, tmp_path)
    vista = next(p for p in joao.get("/api/preparos").json() if p["id"] == pid)
    assert vista["minhaSituacao"] is None and vista["donoNome"] == "Maria"

    assert joao.post(f"/api/preparos/{pid}/solicitar").status_code == 200
    assert joao.post(f"/api/preparos/{pid}/solicitar").status_code == 200  # repetir não duplica
    assert joao.get("/api/registros", headers={HDR: pid}).status_code == 403  # pendente ainda não entra

    membros = maria.get(f"/api/preparos/{pid}/membros").json()
    pendente = next(m for m in membros if m["nome"] == "João")
    assert pendente["situacao"] == "pendente"
    assert next(p for p in maria.get("/api/preparos").json() if p["id"] == pid)["pendentes"] == 1

    res = maria.patch(f"/api/preparos/{pid}/membros/{pendente['usuarioId']}", json={"situacao": "aprovado"})
    assert res.status_code == 200
    assert joao.get("/api/registros", headers={HDR: pid}).status_code == 200


def test_pedido_recusado_nao_entra_nem_pode_insistir(monkeypatch, tmp_path: Path) -> None:
    maria, joao, pid = _equipe(monkeypatch, tmp_path)
    joao.post(f"/api/preparos/{pid}/solicitar")
    uid = maria.get(f"/api/preparos/{pid}/membros").json()[-1]["usuarioId"]
    maria.patch(f"/api/preparos/{pid}/membros/{uid}", json={"situacao": "recusado"})
    assert joao.get("/api/registros", headers={HDR: pid}).status_code == 403
    assert joao.post(f"/api/preparos/{pid}/solicitar").status_code == 409


def test_so_o_dono_gerencia_membros_e_o_dono_nao_pode_ser_alterado(monkeypatch, tmp_path: Path) -> None:
    maria, joao, pid = _equipe(monkeypatch, tmp_path)
    joao.post(f"/api/preparos/{pid}/solicitar")
    uid_joao = next(m for m in maria.get(f"/api/preparos/{pid}/membros").json() if m["nome"] == "João")["usuarioId"]

    assert joao.get(f"/api/preparos/{pid}/membros").status_code == 403
    auto = joao.patch(f"/api/preparos/{pid}/membros/{uid_joao}", json={"situacao": "aprovado"})
    assert auto.status_code == 403  # não aprova a si mesmo

    uid_maria = next(m for m in maria.get(f"/api/preparos/{pid}/membros").json() if m["papel"] == "dono")["usuarioId"]
    assert maria.patch(f"/api/preparos/{pid}/membros/{uid_maria}", json={"situacao": "recusado"}).status_code == 400


REGISTRO = {
    "data": "2026-11-22",
    "blocos": [
        {
            "panelas": [
                {
                    "numero": 1, "tipo": "1ª", "entrada": "06:00", "fervura": "06:30",
                    "colhida": "10:00", "litros": 10, "pesoSecaKg": 12, "pesoCheiaKg": 36,
                }
            ]
        }
    ],
}


def _dois_preparos(monkeypatch, tmp_path: Path):
    """Maria é dona do preparo A e João é dono do preparo B; um não participa do outro."""
    maria, joao, pid_a = _equipe(monkeypatch, tmp_path)
    pid_b = joao.post("/api/preparos", json={"nome": "Outro Núcleo"}).json()["id"]
    return maria, {HDR: pid_a}, joao, {HDR: pid_b}


def test_dados_ficam_isolados_por_preparo(monkeypatch, tmp_path: Path) -> None:
    maria, ha, joao, hb = _dois_preparos(monkeypatch, tmp_path)

    assert maria.post("/api/registros", json=REGISTRO, headers=ha).status_code == 201
    maria.post("/api/lembretes", json={"texto": "Lenha", "horario": "14:00"}, headers=ha)
    maria.put("/api/config", json={"metaLitrosPadrao": 11.5}, headers=ha)
    maria.put("/api/rascunho", json={"data": "2026-11-22", "blocos": []}, headers=ha)

    assert len(maria.get("/api/registros", headers=ha).json()) == 1
    assert maria.get("/api/stats/pesos-panelas", headers=ha).json() != []

    assert joao.get("/api/registros", headers=hb).json() == []
    assert joao.get("/api/lembretes", headers=hb).json() == []
    assert joao.get("/api/config", headers=hb).json()["metaLitrosPadrao"] == 10.15
    assert joao.get("/api/rascunho", headers=hb).json() is None
    assert joao.get("/api/stats/pesos-panelas", headers=hb).json() == []
    assert joao.get("/api/stats/summary", headers=hb).json()["totalPanelasColhidas"] == 0
    assert maria.get("/api/stats/summary", headers=ha).json()["totalPanelasColhidas"] == 1
    assert joao.get("/api/registros/export/json", headers=hb).json() == []


def test_nao_acessa_por_id_o_que_e_de_outro_preparo(monkeypatch, tmp_path: Path) -> None:
    maria, ha, joao, hb = _dois_preparos(monkeypatch, tmp_path)
    reg_id = maria.post("/api/registros", json=REGISTRO, headers=ha).json()["id"]
    lem_id = maria.post("/api/lembretes", json={"texto": "Lenha", "horario": ""}, headers=ha).json()["id"]

    assert joao.get(f"/api/registros/{reg_id}", headers=hb).status_code == 404
    assert joao.delete(f"/api/registros/{reg_id}", headers=hb).status_code == 404
    assert joao.put(f"/api/registros/{reg_id}", json={**REGISTRO, "mestre": "Invasor"}, headers=hb).status_code == 404
    assert joao.patch(f"/api/lembretes/{lem_id}", json={"feito": True}, headers=hb).status_code == 404
    assert joao.delete(f"/api/lembretes/{lem_id}", headers=hb).status_code == 404

    original = maria.get(f"/api/registros/{reg_id}", headers=ha).json()
    assert original["mestre"] == ""  # nada foi sobrescrito


def test_importar_vai_para_o_preparo_escolhido(monkeypatch, tmp_path: Path) -> None:
    maria, ha, joao, hb = _dois_preparos(monkeypatch, tmp_path)
    item = {"id": "reg-importado", **REGISTRO}
    res = maria.post("/api/registros/import", json={"payload": [item]}, headers=ha)
    assert res.status_code == 200
    assert [r["id"] for r in maria.get("/api/registros", headers=ha).json()] == ["reg-importado"]
    assert joao.get("/api/registros", headers=hb).json() == []
    # importar o mesmo id em outro preparo não pode sobrescrever o original
    joao.post("/api/registros/import", json={"payload": [{**item, "mestre": "Invasor"}]}, headers=hb)
    assert maria.get("/api/registros/reg-importado", headers=ha).json()["mestre"] == ""


def _com_joao_aprovado(monkeypatch, tmp_path: Path):
    maria, joao, pid = _equipe(monkeypatch, tmp_path)
    joao.post(f"/api/preparos/{pid}/solicitar")
    uid = next(m for m in maria.get(f"/api/preparos/{pid}/membros").json() if m["nome"] == "João")["usuarioId"]
    maria.patch(f"/api/preparos/{pid}/membros/{uid}", json={"situacao": "aprovado"})
    return maria, joao, {HDR: pid}


def _rascunho(litros: float, versao=None) -> dict:
    corpo = {
        "data": "2026-11-22",
        "blocos": [{"obs": "", "anotador": "", "data": "2026-11-22",
                    "panelas": [{"numero": 1, "tipo": "1ª vez", "entrada": "06:00", "litros": litros}]}],
    }
    if versao is not None:
        corpo["_versao"] = versao
    return corpo


def test_rascunho_recusa_gravacao_sobre_versao_desatualizada(monkeypatch, tmp_path: Path) -> None:
    maria, joao, h = _com_joao_aprovado(monkeypatch, tmp_path)
    v1 = maria.put("/api/rascunho", json=_rascunho(10), headers=h).json()
    assert v1["_versao"] == 1

    lido = joao.get("/api/rascunho", headers=h).json()
    v2 = joao.put("/api/rascunho", json=_rascunho(11, lido["_versao"]), headers=h).json()
    assert v2["_versao"] == 2

    atrasada = maria.put("/api/rascunho", json=_rascunho(99, 1), headers=h)  # Maria ainda tem a v1
    assert atrasada.status_code == 409
    assert atrasada.json()["atual"]["_versao"] == 2
    assert atrasada.json()["atual"]["blocos"][0]["panelas"][0]["litros"] == 11  # o do João não se perdeu

    ok = maria.put("/api/rascunho", json=_rascunho(12, 2), headers=h)
    assert ok.status_code == 200 and ok.json()["_versao"] == 3


def test_rascunho_exige_versao_para_sobrescrever_um_existente(monkeypatch, tmp_path: Path) -> None:
    maria, _, h = _com_joao_aprovado(monkeypatch, tmp_path)
    maria.put("/api/rascunho", json=_rascunho(10), headers=h)
    assert maria.put("/api/rascunho", json=_rascunho(11), headers=h).status_code == 409  # sem _versao
    maria.delete("/api/rascunho", headers=h)
    assert maria.put("/api/rascunho", json=_rascunho(11, 7), headers=h).status_code == 409  # versão de um rascunho que já não existe
    assert maria.put("/api/rascunho", json=_rascunho(11), headers=h).status_code == 200


def test_autoria_do_bloco_e_calculada_pelo_servidor(monkeypatch, tmp_path: Path) -> None:
    maria, joao, h = _com_joao_aprovado(monkeypatch, tmp_path)
    forjado = _rascunho(10)
    forjado["blocos"][0]["autoria"] = {"criadoPorId": 99, "criadoPorNome": "Forjado", "criadoEm": "x"}
    v1 = maria.put("/api/rascunho", json=forjado, headers=h).json()
    assert v1["blocos"][0]["autoria"]["criadoPorNome"] == "Maria"

    v2 = joao.put("/api/rascunho", json=_rascunho(11, v1["_versao"]), headers=h).json()
    autoria = v2["blocos"][0]["autoria"]
    assert (autoria["criadoPorNome"], autoria["editadoPorNome"]) == ("Maria", "João")


def test_registro_salvo_herda_a_autoria_do_rascunho_e_registra_quem_editou(monkeypatch, tmp_path: Path) -> None:
    maria, joao, h = _com_joao_aprovado(monkeypatch, tmp_path)
    maria.put("/api/rascunho", json=_rascunho(10), headers=h)

    novo = {"data": "2026-11-22", "blocos": _rascunho(10)["blocos"]}
    reg = joao.post("/api/registros", json=novo, headers=h).json()
    assert reg["criadoPor"]["nome"] == "João"  # quem salvou o registro
    assert reg["blocos"][0]["autoria"]["criadoPorNome"] == "Maria"  # quem anotou o bloco

    editado = {"data": "2026-11-22", "blocos": _rascunho(15)["blocos"]}
    depois = maria.put(f"/api/registros/{reg['id']}", json=editado, headers=h).json()
    assert depois["blocos"][0]["autoria"]["editadoPorNome"] == "Maria"
    assert depois["atualizadoPor"]["nome"] == "Maria"
    assert depois["criadoPor"]["nome"] == "João"


def test_dados_antigos_sem_preparo_sao_adotados_pelo_primeiro_administrador(monkeypatch, tmp_path: Path) -> None:
    import json
    import sqlite3

    from app.database import _upsert_registro_conn, db_session, init_db

    db = tmp_path / "preparos.db"
    monkeypatch.setenv("PREPARO_DB_PATH", str(db))
    init_db()
    with db_session() as conn:  # dados de antes do login: sem preparo, rascunho global e config global
        _upsert_registro_conn(conn, {"id": "reg-antigo", **REGISTRO}, origem="seed")
        conn.execute(
            "INSERT INTO lembretes (id, texto, horario, feito, created_at) VALUES ('lem-antigo', 'Lenha', '', 0, 't')"
        )
        conn.execute("INSERT INTO rascunho (id, payload_json, updated_at) VALUES (1, ?, 't')", (json.dumps(_rascunho(10)),))
        conn.execute("UPDATE configuracoes SET valor = '11.5' WHERE chave = 'meta_litros_padrao'")

    app = _app(monkeypatch, tmp_path)
    with TestClient(app) as c:
        c.post("/api/auth/login", json=ADMIN)
        preparo = next(p for p in c.get("/api/preparos").json() if p["meuPapel"] == "dono")
        h = {HDR: preparo["id"]}
        assert [r["id"] for r in c.get("/api/registros", headers=h).json()] == ["reg-antigo"]
        assert [x["id"] for x in c.get("/api/lembretes", headers=h).json()] == ["lem-antigo"]
        assert c.get("/api/config", headers=h).json()["metaLitrosPadrao"] == 11.5
        assert c.get("/api/rascunho", headers=h).json()["blocos"][0]["panelas"][0]["litros"] == 10

    # reiniciar não duplica nem cria outro preparo
    with TestClient(_app(monkeypatch, tmp_path)) as c:
        c.post("/api/auth/login", json=ADMIN)
        assert len(c.get("/api/preparos").json()) == 1
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM registros WHERE preparo_id IS NULL").fetchone()[0] == 0


def test_sem_dados_antigos_nenhum_preparo_e_criado_sozinho(monkeypatch, tmp_path: Path) -> None:
    with TestClient(_app(monkeypatch, tmp_path)) as c:
        c.post("/api/auth/login", json=ADMIN)
        assert c.get("/api/preparos").json() == []


def test_gravar_o_mesmo_conteudo_nao_muda_a_versao(monkeypatch, tmp_path: Path) -> None:
    maria, _, h = _com_joao_aprovado(monkeypatch, tmp_path)
    v1 = maria.put("/api/rascunho", json=_rascunho(10), headers=h).json()
    repetido = maria.put("/api/rascunho", json={**_rascunho(10), "_versao": v1["_versao"]}, headers=h).json()
    assert repetido["_versao"] == v1["_versao"]  # senão o autosave do app entraria em loop
    assert repetido["_updatedAt"] == v1["_updatedAt"]
    mudou = maria.put("/api/rascunho", json={**_rascunho(11), "_versao": v1["_versao"]}, headers=h).json()
    assert mudou["_versao"] == v1["_versao"] + 1
