from app.services.cartao_reader import (
    LeituraCartao,
    RespostaCartao,
    _estruturar_respostas,
)


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
