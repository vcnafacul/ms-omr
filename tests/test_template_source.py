from pathlib import Path

import pytest

from app.codigos import CodigoFalha
from app.errors import FalhaNegocio
from app.services import template_source as ts
from app.services.bucket_storage import StorageNotFound


def test_miss_baixa_grava_cache_e_monta_dir(monkeypatch):
    baixados, gravados = [], []

    def fake_baixar(key):
        baixados.append(key)
        return b'{"x":1}' if key.endswith("template.json") else b'{"y":2}'

    monkeypatch.setattr(ts, "baixar_imagem", fake_baixar)
    monkeypatch.setattr(ts, "cache_get", lambda k, p: None)
    monkeypatch.setattr(ts, "cache_set", lambda k, d, p: gravados.append(k))
    d = ts.obter_template("665abc")
    assert (Path(d) / "template.json").read_bytes() == b'{"x":1}'
    assert (Path(d) / "config.json").read_bytes() == b'{"y":2}'
    assert (Path(d) / "omr_marker.png").exists()
    assert baixados == ["templates/665abc/template.json", "templates/665abc/config.json"]
    assert len(gravados) == 2


def test_hit_nao_toca_no_r2(monkeypatch):
    def fail(_):
        raise AssertionError("não deveria baixar")

    monkeypatch.setattr(ts, "baixar_imagem", fail)
    monkeypatch.setattr(ts, "cache_get", lambda k, p: b"{}")
    monkeypatch.setattr(ts, "cache_set", lambda k, d, p: None)
    d = ts.obter_template("665abc")
    assert (Path(d) / "template.json").read_bytes() == b"{}"


def test_template_ausente_vira_falha_negocio(monkeypatch):
    def missing(key):
        raise StorageNotFound(f"objeto não encontrado: {key}")

    monkeypatch.setattr(ts, "baixar_imagem", missing)
    monkeypatch.setattr(ts, "cache_get", lambda k, p: None)
    monkeypatch.setattr(ts, "cache_set", lambda k, d, p: None)
    with pytest.raises(FalhaNegocio) as ei:
        ts.obter_template("665abc")
    assert ei.value.motivo == CodigoFalha.TEMPLATE_AUSENTE
