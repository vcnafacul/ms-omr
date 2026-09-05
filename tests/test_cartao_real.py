"""Regressão de leitura contra uma FOTO REAL (celular) de um cartão preenchido à mão.

Fixture `cartao-real-v1`: cartão gerado pelo ms-simulado (layout com colunas distribuídas na
caixa dos markers), impresso, preenchido a caneta preta e fotografado plano. `expected.json`
guarda a leitura validada manualmente (matrícula 57262531 + 90 respostas, sem nulas/múltiplas).
Trava regressões no pipeline (wrapper + OMRChecker vendorizado).
"""

import json
from pathlib import Path

import pytest

from app.services.omr_engine import run_omr

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cartao-real-v1"


@pytest.mark.integration
def test_leitura_foto_real():
    expected = json.loads((FIXTURE / "expected.json").read_text())
    result = run_omr(FIXTURE / "foto.jpeg", FIXTURE)

    # matrícula = m1..m8 concatenados
    matricula = "".join(expected[f"m{i}"] for i in range(1, 9))
    assert matricula == "57262531"

    # leitura idêntica à esperada (todos os campos)
    assert result.fields == expected

    # sanidade: 90 respostas, nenhuma vazia, nenhuma múltipla (valor de 1 caractere A-E)
    respostas = {k: v for k, v in result.fields.items() if k.startswith("q")}
    assert len(respostas) == 90
    assert all(v in ("A", "B", "C", "D", "E") for v in respostas.values())
