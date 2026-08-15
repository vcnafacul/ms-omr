import pytest

from app.services.imagekey import is_valid, parse_simulado_id


def test_parse_ok():
    assert parse_simulado_id("cartoes/665abc/img1.jpg") == "665abc"


@pytest.mark.parametrize("k", ["", "cartoes/só-um-nível", "outro/665/img", "cartoes/665/a/b"])
def test_invalidos(k):
    assert is_valid(k) is False
    with pytest.raises(ValueError):
        parse_simulado_id(k)


def test_valido_true():
    assert is_valid("cartoes/665abc/img1.jpg") is True
