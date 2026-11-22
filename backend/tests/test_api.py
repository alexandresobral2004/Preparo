"""Testes de integração da API FastAPI + SQLite."""

from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def _make_client(monkeypatch, tmp_path: Path) -> TestClient:
    db_file = tmp_path / "preparo_test.db"
    monkeypatch.setenv("PREPARO_DB_PATH", str(db_file))
    monkeypatch.setenv("PREPARO_ADMIN_LOGIN", "admin")
    monkeypatch.setenv("PREPARO_ADMIN_SENHA", "senha-forte-1")
    app = create_app(dist_dir=tmp_path / "no_dist")
    return TestClient(app)


@contextmanager
def _logged_client(monkeypatch, tmp_path: Path):
    """Cliente já autenticado como administrador (as rotas da API exigem login)."""
    with _make_client(monkeypatch, tmp_path) as client:
        res = client.post("/api/auth/login", json={"login": "admin", "senha": "senha-forte-1"})
        assert res.status_code == 200
        preparo = client.post("/api/preparos", json={"nome": "Preparo de teste"})
        assert preparo.status_code == 201
        client.headers["X-Preparo-Id"] = preparo.json()["id"]
        yield client


def test_crud_registros_e_rascunho_e_lembretes_e_config(monkeypatch, tmp_path: Path) -> None:
    with _logged_client(monkeypatch, tmp_path) as client:
        assert client.get("/api/health").status_code == 200

        # Config padrão
        cfg = client.get("/api/config").json()
        assert cfg["minSemFervura"] == 30
        assert cfg["horasSemColheita"] == 5
        assert cfg["metaLitrosPadrao"] == 10.15

        cfg_upd = client.put("/api/config", json={"metaLitrosPadrao": 10.5}).json()
        assert cfg_upd["metaLitrosPadrao"] == 10.5

        # Rascunho
        draft = {"nucleo": "Bendito Filho", "data": "2026-11-22", "blocos": []}
        assert client.put("/api/rascunho", json=draft).status_code == 200
        assert client.get("/api/rascunho").json()["nucleo"] == "Bendito Filho"

        # Criar registro com vírgula pt-BR e tipos variados
        payload = {
            "nucleo": "Bendito Filho",
            "data": "2026-11-22",
            "mestre": "João",
            "mariri": "Tucunacá",
            "maririKg": "120,5",
            "chacrona": [{"nucleo": "Sede", "kg": "45,5"}, {"nucleo": "Anexo", "kg": "14,5"}],
            "blocos": [
                {
                    "obs": "Bloco piloto",
                    "panelas": [
                        {
                            "numero": 1,
                            "tipo": "1ª",
                            "entrada": "08:00",
                            "fervura": "08:30",
                            "colhida": "12:00",
                            "litros": "10,15",
                            "pesoSecaKg": "12,0",
                            "pesoCheiaKg": "36,0",
                        },
                        {
                            "numero": 2,
                            "tipo": "apuro",
                            "entrada": "09:00",
                            "fervura": "09:20",
                            "colhida": "11:40",
                            "litros": "11,2",
                            "pesoSecaKg": "10,0",
                            "pesoCheiaKg": "28,0",
                        },
                    ],
                }
            ],
        }
        res_create = client.post("/api/registros", json=payload)
        assert res_create.status_code == 201
        created = res_create.json()
        reg_id = created["id"]
        assert created["chacronaTotalKg"] == 60.0
        assert created["totalLitros"] == 21.35
        assert created["totaisPorTipo"]["1ª vez"] == 10.15
        assert created["totaisPorTipo"]["APURO"] == 11.2

        # Export CSV (BOM UTF-8 e ;)
        csv_res = client.get("/api/registros/export/csv")
        assert csv_res.status_code == 200
        csv_text = csv_res.content.decode("utf-8")
        assert csv_text.startswith("\ufeffData;Núcleo;")
        assert "10,15" in csv_text
        assert "APURO" in csv_text

        # Lembretes
        lem = client.post("/api/lembretes", json={"texto": "Conferir lenha", "horario": "14:00"}).json()
        assert lem["feito"] is False
        lem_patched = client.patch(f"/api/lembretes/{lem['id']}", json={"feito": True}).json()
        assert lem_patched["feito"] is True
        assert client.delete(f"/api/lembretes/{lem['id']}").status_code == 200

        # Predict com painel ativo em memória
        pred_res = client.post(
            "/api/stats/predict",
            json={
                "data": "2026-11-22",
                "agora": "2026-11-22T10:30:00",
                "blocos": [
                    {
                        "obs": "",
                        "panelas": [
                            {
                                "numero": 1,
                                "tipo": "1ª vez",
                                "entrada": "08:30",
                                "fervura": "09:00",
                                "pesoSecaKg": 12.0,
                                "pesoCheiaKg": 36.0,
                            }
                        ],
                    }
                ],
            },
        )
        assert pred_res.status_code == 200
        pred_data = pred_res.json()
        assert pred_data["resumo"]["noFogo"] == 1
        assert pred_data["blocos"][0]["panelas"][0]["predicao"]["disponivel"] is True
        assert pred_data["blocos"][0]["panelas"][0]["predicao"]["modeloNivel"] == "aprendendo"

        # Pesos distintos sugeridos
        pesos = client.get("/api/stats/pesos-panelas").json()
        assert len(pesos) == 2

        # Excluir registro
        assert client.delete(f"/api/registros/{reg_id}").status_code == 200
        assert client.get("/api/registros").json() == []


def test_import_tres_formatos_sem_duplicar(monkeypatch, tmp_path: Path) -> None:
    with _logged_client(monkeypatch, tmp_path) as client:
        # Formato 1: registro único com tipo legado "2"
        single = {
            "id": "v1-reg-1",
            "data": "2026-03-20",
            "nucleo": "Bendito Filho",
            "blocos": [
                {
                    "obs": "",
                    "panelas": [
                        {"tipo": "2", "entrada": "07:00", "fervura": "07:30", "colhida": "11:30", "litros": "12,5"}
                    ],
                }
            ],
        }
        r1 = client.post("/api/registros/import", json={"payload": single}).json()
        assert r1 == {"importados": 1, "jaExistentes": 0, "invalidos": 0}

        # Formato 2: wrapper { registros: [...] } com 1 duplicado + 1 novo
        wrapped = {
            "registros": [
                single,
                {
                    "id": "v1-reg-2",
                    "data": "2026-03-21",
                    "blocos": [{"obs": "", "panelas": [{"tipo": "3a", "litros": 9}]}],
                },
            ]
        }
        r2 = client.post("/api/registros/import", json={"payload": wrapped}).json()
        assert r2 == {"importados": 1, "jaExistentes": 1, "invalidos": 0}

        # Formato 3: lista direta com 1 inválido (sem blocos) + 1 duplicado
        r3 = client.post(
            "/api/registros/import",
            json={"payload": [single, {"id": "sem-blocos"}]},
        ).json()
        assert r3 == {"importados": 0, "jaExistentes": 1, "invalidos": 1}

        regs = client.get("/api/registros").json()
        assert len(regs) == 2
        assert regs[1]["blocos"][0]["panelas"][0]["tipo"] == "2ª vez"
        assert regs[0]["blocos"][0]["panelas"][0]["tipo"] == "3ª vez"


def test_single_port_spa_and_pwa_assets(monkeypatch, tmp_path: Path) -> None:
    from app.config import FRONTEND_DIST_DIR

    assert (FRONTEND_DIST_DIR / "index.html").is_file()
    monkeypatch.setenv("PREPARO_DB_PATH", str(tmp_path / "spa_test.db"))
    app = create_app(dist_dir=FRONTEND_DIST_DIR)
    with TestClient(app) as client:
        r_html = client.get("/")
        assert r_html.status_code == 200
        assert "Preparo de Vegetal" in r_html.text

        r_manifest = client.get("/manifest.webmanifest")
        assert r_manifest.status_code == 200
        assert r_manifest.json()["short_name"] == "Preparo"

        r_sw = client.get("/sw.js")
        assert r_sw.status_code == 200
        assert "preparo-v2" in r_sw.text

        for icon_name in ("icon-192.png", "icon-512.png", "icon-maskable-512.png"):
            r_icon = client.get(f"/icons/{icon_name}")
            assert r_icon.status_code == 200
            assert r_icon.content[:8] == b"\x89PNG\r\n\x1a\n"

        assert client.get("/api/health").status_code == 200
        # a tela e os arquivos do PWA são públicos; os dados da API exigem login
        assert client.get("/api/stats/summary").status_code == 401
        assert client.get("/api/registros").status_code == 401



def test_anotador_do_bloco_e_salvo_e_devolvido(monkeypatch, tmp_path: Path) -> None:
    with _logged_client(monkeypatch, tmp_path) as client:
        payload = {
            "data": "2026-11-22",
            "blocos": [
                {"anotador": "Maria", "data": "2026-11-21", "panelas": [{"numero": 1, "tipo": "1ª", "litros": 10}]},
                {"panelas": [{"numero": 6, "tipo": "2ª", "litros": 9}]},
            ],
        }
        res = client.post("/api/registros", json=payload)
        assert res.status_code == 201
        reg = client.get(f"/api/registros/{res.json()['id']}").json()
        assert [b["anotador"] for b in reg["blocos"]] == ["Maria", ""]
        assert [b["data"] for b in reg["blocos"]] == ["2026-11-21", ""]


def test_init_db_adiciona_anotador_em_banco_antigo(tmp_path: Path) -> None:
    import sqlite3

    from app.database import init_db

    db_file = tmp_path / "antigo.db"
    init_db(db_file)
    con = sqlite3.connect(db_file)
    for coluna in ("anotador", "data"):  # simula banco criado antes dos campos
        con.execute(f"ALTER TABLE blocos DROP COLUMN {coluna}")
    con.commit()
    con.close()

    init_db(db_file)
    init_db(db_file)  # idempotente: rodar de novo não pode falhar

    colunas = [r[1] for r in sqlite3.connect(db_file).execute("PRAGMA table_info(blocos)")]
    assert {"anotador", "data"} <= set(colunas)


def test_peso_com_agua_da_panela_e_salvo_e_devolvido(monkeypatch, tmp_path: Path) -> None:
    with _logged_client(monkeypatch, tmp_path) as client:
        payload = {
            "data": "2026-11-22",
            "blocos": [{"panelas": [{"numero": 1, "tipo": "1ª", "pesoSecaKg": "12", "pesoCheiaKg": "36", "pesoComAguaKg": "56,5"}]}],
        }
        reg_id = client.post("/api/registros", json=payload).json()["id"]
        pan = client.get(f"/api/registros/{reg_id}").json()["blocos"][0]["panelas"][0]
        assert pan["pesoComAguaKg"] == 56.5
        sem = {"data": "2026-11-23", "blocos": [{"panelas": [{"numero": 1, "tipo": "1ª"}]}]}
        outro = client.post("/api/registros", json=sem).json()["id"]
        assert client.get(f"/api/registros/{outro}").json()["blocos"][0]["panelas"][0]["pesoComAguaKg"] is None
