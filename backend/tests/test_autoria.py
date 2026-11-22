"""Autoria por bloco: quem criou e quem editou, calculado pelo servidor."""

from app.autoria import aplicar_autoria

MARIA = {"id": 1, "nome": "Maria"}
JOAO = {"id": 2, "nome": "João"}


def _bloco(litros=10, tipo="1ª vez", anotador="", obs=""):
    return {
        "obs": obs,
        "anotador": anotador,
        "data": "2026-11-22",
        "panelas": [{"numero": 1, "tipo": tipo, "entrada": "06:00", "fervura": "", "colhida": "", "litros": litros}],
    }


def test_bloco_novo_registra_quem_criou() -> None:
    out = aplicar_autoria([], [_bloco()], MARIA, "t1")
    assert out[0]["autoria"] == {"criadoPorId": 1, "criadoPorNome": "Maria", "criadoEm": "t1"}


def test_bloco_igual_mantem_a_autoria_mesmo_com_outro_usuario_salvando() -> None:
    antes = aplicar_autoria([], [_bloco()], MARIA, "t1")
    depois = aplicar_autoria(antes, [_bloco()], JOAO, "t2")
    assert depois[0]["autoria"] == antes[0]["autoria"]
    assert "editadoPorId" not in depois[0]["autoria"]


def test_alterar_o_bloco_registra_quem_editou_e_preserva_quem_criou() -> None:
    antes = aplicar_autoria([], [_bloco(litros=10)], MARIA, "t1")
    depois = aplicar_autoria(antes, [_bloco(litros=11)], JOAO, "t2")
    assert depois[0]["autoria"] == {
        "criadoPorId": 1, "criadoPorNome": "Maria", "criadoEm": "t1",
        "editadoPorId": 2, "editadoPorNome": "João", "editadoEm": "t2",
    }


def test_formato_diferente_do_mesmo_valor_nao_conta_como_edicao() -> None:
    antes = aplicar_autoria([], [_bloco(litros=10, tipo="1ª vez")], MARIA, "t1")
    mesmo = _bloco(litros="10,0", tipo="1ª")  # vírgula pt-BR e tipo abreviado
    depois = aplicar_autoria(antes, [mesmo], JOAO, "t2")
    assert "editadoPorId" not in depois[0]["autoria"]


def test_autoria_enviada_pelo_cliente_e_ignorada() -> None:
    forjado = {**_bloco(), "autoria": {"criadoPorId": 99, "criadoPorNome": "Forjado", "criadoEm": "x"}}
    out = aplicar_autoria([], [forjado], MARIA, "t1")
    assert out[0]["autoria"]["criadoPorNome"] == "Maria"


def test_blocos_novos_no_fim_e_blocos_removidos() -> None:
    antes = aplicar_autoria([], [_bloco(), _bloco(litros=9)], MARIA, "t1")
    depois = aplicar_autoria(antes, [_bloco(), _bloco(litros=9), _bloco(litros=8)], JOAO, "t2")
    assert depois[0]["autoria"] == antes[0]["autoria"]
    assert depois[2]["autoria"]["criadoPorNome"] == "João"
    assert len(aplicar_autoria(depois, [_bloco()], MARIA, "t3")) == 1


def test_sem_usuario_nao_inventa_autoria() -> None:  # importação e seeds
    out = aplicar_autoria([], [_bloco()], None, "t1")
    assert out[0].get("autoria") is None
