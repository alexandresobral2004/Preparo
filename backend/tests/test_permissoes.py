"""Permissão do membro: quem só acompanha lê, mas não escreve; quem edita escreve."""

from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.preparos import preparo_atual, preparo_editavel
from tests.test_preparos import HDR, REGISTRO, _app, _equipe, _membro, _rascunho

MSG_ACOMPANHA = "Você participa deste preparo só para acompanhar. Peça ao dono permissão para editar."


def _com_joao(monkeypatch, tmp_path: Path, permissao: str):
    """Maria (dona) tem dados; João entra com a permissão dada. Devolve (maria, joao, headers, id do lembrete)."""
    maria, joao, pid = _equipe(monkeypatch, tmp_path)
    h = {HDR: pid}
    assert maria.post("/api/registros", json={"id": "reg-1", **REGISTRO}, headers=h).status_code == 201
    lem = maria.post("/api/lembretes", json={"texto": "Lenha", "horario": ""}, headers=h).json()["id"]
    maria.put("/api/config", json={"metaLitrosPadrao": 11.5}, headers=h)
    maria.put("/api/rascunho", json=_rascunho(10), headers=h)
    joao.post(f"/api/preparos/{pid}/solicitar")
    uid = _membro(maria, pid, "João")["usuarioId"]
    body = {"situacao": "aprovado", "permissao": permissao}
    assert maria.patch(f"/api/preparos/{pid}/membros/{uid}", json=body).status_code == 200
    return maria, joao, h, lem


def _estado(maria: TestClient, h: dict) -> tuple:
    """Tudo o que o acompanhante poderia alterar, lido como a dona lê."""
    return (
        maria.get("/api/registros", headers=h).json(),
        maria.get("/api/lembretes", headers=h).json(),
        maria.get("/api/config", headers=h).json(),
        maria.get("/api/rascunho", headers=h).json(),
    )


ESCRITAS = [
    ("post", "/api/registros", {"json": {"id": "reg-2", **REGISTRO}}),
    ("put", "/api/registros/reg-1", {"json": REGISTRO}),
    ("delete", "/api/registros/reg-1", {}),
    ("post", "/api/registros/import", {"json": {"payload": [{"id": "reg-3", **REGISTRO}]}}),
    ("post", "/api/lembretes", {"json": {"texto": "Outro", "horario": ""}}),
    ("patch", "/api/lembretes/{lem}", {"json": {"feito": True}}),
    ("delete", "/api/lembretes/{lem}", {}),
    ("put", "/api/config", {"json": {"metaLitrosPadrao": 9.0}}),
    ("put", "/api/rascunho", {"json": _rascunho(20)}),
    ("delete", "/api/rascunho", {}),
]

LEITURAS = [
    ("get", "/api/registros", {}),
    ("get", "/api/registros/reg-1", {}),
    ("get", "/api/registros/export/csv", {}),
    ("get", "/api/registros/export/json", {}),
    ("get", "/api/lembretes", {}),
    ("get", "/api/config", {}),
    ("get", "/api/rascunho", {}),
    ("get", "/api/stats/summary", {}),
    ("get", "/api/stats/pesos-panelas", {}),
    ("post", "/api/stats/predict", {"json": {"data": "2026-11-22", "agora": "2026-11-22T10:30:00", "blocos": []}}),
]


@pytest.mark.parametrize("metodo,url,kwargs", ESCRITAS, ids=lambda v: v if isinstance(v, str) else None)
def test_acompanhante_recebe_403_em_cada_escrita_e_o_banco_nao_muda(monkeypatch, tmp_path: Path, metodo, url, kwargs) -> None:
    maria, joao, h, lem = _com_joao(monkeypatch, tmp_path, "acompanhar")
    antes = _estado(maria, h)
    res = getattr(joao, metodo)(url.format(lem=lem), headers=h, **kwargs)
    assert res.status_code == 403
    assert res.json()["detail"] == MSG_ACOMPANHA
    assert _estado(maria, h) == antes


@pytest.mark.parametrize("metodo,url,kwargs", LEITURAS, ids=lambda v: v if isinstance(v, str) else None)
def test_acompanhante_consegue_ler_e_simular(monkeypatch, tmp_path: Path, metodo, url, kwargs) -> None:
    _, joao, h, _ = _com_joao(monkeypatch, tmp_path, "acompanhar")
    assert getattr(joao, metodo)(url, headers=h, **kwargs).status_code == 200


def test_editor_continua_escrevendo(monkeypatch, tmp_path: Path) -> None:
    _, joao, h, lem = _com_joao(monkeypatch, tmp_path, "editar")
    assert joao.put("/api/config", json={"metaLitrosPadrao": 9.0}, headers=h).status_code == 200
    assert joao.post("/api/lembretes", json={"texto": "Outro"}, headers=h).status_code == 201
    assert joao.delete(f"/api/lembretes/{lem}", headers=h).status_code == 200
    assert joao.delete("/api/registros/reg-1", headers=h).status_code == 200


def test_dono_continua_escrevendo_mesmo_com_o_membro_so_acompanhando(monkeypatch, tmp_path: Path) -> None:
    maria, _, h, _ = _com_joao(monkeypatch, tmp_path, "acompanhar")
    assert maria.put("/api/config", json={"metaLitrosPadrao": 9.0}, headers=h).status_code == 200


def test_rebaixar_editor_para_acompanhante_bloqueia_a_proxima_escrita_sem_novo_login(monkeypatch, tmp_path: Path) -> None:
    maria, joao, h, _ = _com_joao(monkeypatch, tmp_path, "editar")
    assert joao.put("/api/config", json={"metaLitrosPadrao": 9.0}, headers=h).status_code == 200

    uid = _membro(maria, h[HDR], "João")["usuarioId"]
    maria.patch(f"/api/preparos/{h[HDR]}/membros/{uid}", json={"situacao": "aprovado", "permissao": "acompanhar"})

    res = joao.put("/api/config", json={"metaLitrosPadrao": 8.0}, headers=h)  # mesma sessão, sem logar de novo
    assert res.status_code == 403
    assert res.json()["detail"] == MSG_ACOMPANHA


def _vinculo(maria: TestClient, pid: str) -> tuple:
    joao = _membro(maria, pid, "João")
    return (joao["situacao"], joao["permissao"])


def test_solicitar_de_acompanhante_aprovado_nao_muda_situacao_nem_permissao(monkeypatch, tmp_path: Path) -> None:
    maria, joao, h, _ = _com_joao(monkeypatch, tmp_path, "acompanhar")
    pid = h[HDR]
    antes = _vinculo(maria, pid)
    assert joao.post(f"/api/preparos/{pid}/solicitar").json() == {"situacao": "aprovado"}
    assert _vinculo(maria, pid) == antes == ("aprovado", "acompanhar")


def test_solicitar_de_membro_recusado_da_409_e_nao_muda_o_vinculo(monkeypatch, tmp_path: Path) -> None:
    maria, joao, pid = _equipe(monkeypatch, tmp_path)
    joao.post(f"/api/preparos/{pid}/solicitar")
    uid = _membro(maria, pid, "João")["usuarioId"]
    assert maria.patch(f"/api/preparos/{pid}/membros/{uid}", json={"situacao": "recusado"}).status_code == 200
    antes = _vinculo(maria, pid)
    assert joao.post(f"/api/preparos/{pid}/solicitar").status_code == 409
    assert _vinculo(maria, pid) == antes
    assert antes[0] == "recusado"


def _rotas(itens):
    """Rotas do app, descendo nos routers incluídos (o FastAPI novo os guarda em original_router)."""
    for item in itens:
        if isinstance(item, APIRoute):
            yield item
        elif hasattr(item, "original_router"):
            yield from _rotas(item.original_router.routes)


def test_toda_escrita_com_preparo_usa_preparo_editavel_exceto_predict(monkeypatch, tmp_path: Path) -> None:
    app = _app(monkeypatch, tmp_path)

    def dependencias(dependant):
        for dep in dependant.dependencies:
            yield dep.call
            yield from dependencias(dep)

    escritas = 0
    for route in _rotas(app.routes):
        chamadas = set(dependencias(route.dependant))
        if not chamadas & {preparo_atual, preparo_editavel}:
            continue  # rota sem contexto de preparo (login, preparos, usuários)
        if not route.methods & {"POST", "PUT", "PATCH", "DELETE"}:
            continue
        escritas += 1
        if route.path == "/api/stats/predict":
            continue  # só calcula, não grava
        assert preparo_editavel in chamadas, f"{sorted(route.methods)} {route.path} aceita acompanhante"
    assert escritas >= len(ESCRITAS)  # guarda contra o teste passar sem ver nenhuma rota
