import json
from pathlib import Path

import pytest

from app.services.cartao_reader import ler_cartao
from tests.helpers.patologico import assert_patologico

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cartao-patologico-v1"
FOTO = FIXTURE / "foto.jpeg"


@pytest.mark.integration
@pytest.mark.skipif(
    not FOTO.exists(),
    reason="foto.jpeg da fixture patológica ainda não fornecida (passo manual)",
)
def test_cartao_patologico_omite_dupla_e_branco():
    exp = json.loads((FIXTURE / "expected.json").read_text())
    leitura = ler_cartao("cartoes/teste/patologico", FOTO, FIXTURE)
    assert_patologico(
        leitura.respostas,
        n=exp["n"],
        dupla=exp["questaoDupla"],
        branco=exp["questaoBranco"],
    )
