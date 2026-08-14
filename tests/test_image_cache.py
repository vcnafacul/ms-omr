import redis

from app.services import image_cache
from app.services.image_cache import cache_get, cache_set


def test_cache_get_sem_redis_devolve_none(monkeypatch):
    monkeypatch.setattr(image_cache, "_redis", lambda: None)
    assert cache_get("k") is None


def test_cache_set_sem_redis_e_noop(monkeypatch):
    monkeypatch.setattr(image_cache, "_redis", lambda: None)
    cache_set("k", b"data")  # não deve levantar


def test_cache_get_hit(monkeypatch):
    class _R:
        def get(self, key):
            assert key == "omr:img:k"
            return b"CACHED"

    monkeypatch.setattr(image_cache, "_redis", lambda: _R())
    assert cache_get("k") == b"CACHED"


def test_cache_get_erro_e_gracioso(monkeypatch):
    class _R:
        def get(self, key):
            raise redis.RedisError("caiu")

    monkeypatch.setattr(image_cache, "_redis", lambda: _R())
    assert cache_get("k") is None  # não levanta, cai pro None


def test_cache_set_grava_com_ttl(monkeypatch):
    chamado = {}

    class _R:
        def set(self, key, data, ex=None):
            chamado.update(key=key, data=data, ex=ex)

    monkeypatch.setattr(image_cache, "_redis", lambda: _R())
    cache_set("k", b"data")
    assert chamado == {"key": "omr:img:k", "data": b"data", "ex": 3600}


def test_cache_set_erro_e_gracioso(monkeypatch):
    class _R:
        def set(self, key, data, ex=None):
            raise redis.RedisError("caiu")

    monkeypatch.setattr(image_cache, "_redis", lambda: _R())
    cache_set("k", b"data")  # não deve levantar
