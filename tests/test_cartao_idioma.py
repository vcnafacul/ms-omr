"""tickets/038 (R13) — o cartão DA PROVA do ENEM Dia 1 do cursinho tem, além das 90 questões, a
marcação de idioma (bloco `idioma`, bubbleValues ING/ESP). O leitor devolve o valor cru em
`campos`; quem escolhe o simulado é o ms-simulado.

Fixture `cartao-prova-idioma-v1`: template e PDF gerados pelo ms-simulado (card 08), folha
rasterizada a 300 dpi e preenchida DIGITALMENTE (q1=A, q2=B, q3=C, q40=D, q90=E + o idioma),
reduzida para caber no repo. Não é foto de celular — essa fica para o QA da série.
"""

from pathlib import Path

import pytest

from app.services.cartao_reader import ler_cartao

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cartao-prova-idioma-v1"
RESPOSTAS = [("1", "A"), ("2", "B"), ("3", "C"), ("40", "D"), ("90", "E")]


@pytest.mark.integration
@pytest.mark.parametrize(
    ("folha", "idioma"),
    [("esp", "ESP"), ("nenhum", ""), ("duas", "INGESP")],
)
def test_le_o_idioma_cru_e_as_respostas(folha, idioma):
    leitura = ler_cartao("x", FIXTURE / f"folha-{folha}.jpg", FIXTURE)

    assert leitura.campos == {"idioma": idioma}
    assert [(r.questao, r.alternativaEstudante) for r in leitura.respostas] == RESPOSTAS


@pytest.mark.integration
def test_cartao_de_hoje_tem_campos_vazio():
    real = FIXTURE.parent / "cartao-real-v1"
    leitura = ler_cartao("x", real / "foto.jpeg", real)
    assert leitura.campos == {}
