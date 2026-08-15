from types import SimpleNamespace

import pytest

from tests.helpers.patologico import assert_patologico


def _r(q, alt):
    return SimpleNamespace(questao=q, alternativaEstudante=alt)


def test_ok_dupla_e_branco_omitidas():
    # n=5, questões 1,3,5 lidas (2 e 4 omitidas = dupla+branco)
    respostas = [_r("1", "A"), _r("3", "C"), _r("5", "E")]
    assert_patologico(respostas, n=5, dupla="2", branco="4")  # não levanta


def test_falha_se_dupla_presente():
    respostas = [_r("1", "A"), _r("2", "B"), _r("3", "C"), _r("5", "E")]
    with pytest.raises(AssertionError):
        assert_patologico(respostas, n=5, dupla="2", branco="4")


def test_falha_se_contagem_errada():
    respostas = [_r("1", "A"), _r("3", "C")]  # falta a 5 → só 2, esperado n-2=3
    with pytest.raises(AssertionError):
        assert_patologico(respostas, n=5, dupla="2", branco="4")


def test_falha_se_alternativa_invalida():
    respostas = [_r("1", "A"), _r("3", "C"), _r("5", "Z")]
    with pytest.raises(AssertionError):
        assert_patologico(respostas, n=5, dupla="2", branco="4")
