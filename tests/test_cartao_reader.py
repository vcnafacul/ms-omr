from pathlib import Path

import pytest

from app.services.cartao_reader import (
    LeituraCartao,
    RespostaCartao,
    _estruturar_respostas,
    ler_cartao,
)

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cartao-real-v1"


def test_estruturar_filtra_single_omite_branco_dupla_e_matricula():
    fields = {
        "m1": "2",  # matrícula — ignorada
        "m8": "1",  # matrícula — ignorada
        "q1": "A",  # ok
        "q2": "",  # branco — omitido
        "q3": "AE",  # dupla — omitido
        "q10": "C",  # ok
        "input_path": "x.jpg",  # metadado — ignorado
    }
    respostas = _estruturar_respostas(fields)
    assert respostas == [
        RespostaCartao(questao="1", alternativaEstudante="A"),
        RespostaCartao(questao="10", alternativaEstudante="C"),
    ]


def test_estruturar_ordena_por_numero():
    fields = {"q9": "B", "q10": "C", "q1": "A"}
    numeros = [r.questao for r in _estruturar_respostas(fields)]
    assert numeros == ["1", "9", "10"]  # ordem numérica, não lexicográfica


def test_leitura_cartao_shape():
    # ler_cartao é coberto pelo teste de integração (roda o OMR de verdade); aqui só o shape.
    m = LeituraCartao(
        idImage="x", respostas=[RespostaCartao(questao="1", alternativaEstudante="A")]
    )
    assert m.idImage == "x"
    assert m.respostas[0].alternativaEstudante == "A"


@pytest.mark.integration
def test_ler_cartao_foto_real_ecoa_id_e_estrutura_respostas():
    leitura = ler_cartao("img-abc", _FIXTURE / "foto.jpeg", _FIXTURE)

    assert leitura.idImage == "img-abc"
    # a foto do card 03 leu 90/90 single (sem branco/dupla)
    assert len(leitura.respostas) == 90
    por_numero = {r.questao: r.alternativaEstudante for r in leitura.respostas}
    assert por_numero["1"] == "A"
    assert por_numero["73"] == "D"
    # matrícula e metadados não entram
    assert all(r.questao.isdigit() for r in leitura.respostas)
