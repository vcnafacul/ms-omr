from app.services import image_source
from app.services.image_source import obter_imagem


def test_obter_imagem_cache_hit_nao_toca_no_bucket(monkeypatch):
    chamadas = {"bucket": 0, "set": 0}

    monkeypatch.setattr(image_source, "cache_get", lambda key: b"CACHED")

    def _nao_deveria(*a, **k):
        chamadas["bucket"] += 1
        raise AssertionError("bucket não deveria ser chamado no hit")

    monkeypatch.setattr(image_source, "baixar_imagem", _nao_deveria)
    monkeypatch.setattr(image_source, "cache_set", lambda *a, **k: chamadas.__setitem__("set", 1))

    assert obter_imagem("k") == b"CACHED"
    assert chamadas == {"bucket": 0, "set": 0}


def test_obter_imagem_miss_baixa_e_grava(monkeypatch):
    gravado = {}

    monkeypatch.setattr(image_source, "cache_get", lambda key: None)
    monkeypatch.setattr(image_source, "baixar_imagem", lambda key: b"FROM-BUCKET")
    monkeypatch.setattr(
        image_source,
        "cache_set",
        lambda key, data: gravado.update(key=key, data=data),
    )

    assert obter_imagem("k") == b"FROM-BUCKET"
    assert gravado == {"key": "k", "data": b"FROM-BUCKET"}
