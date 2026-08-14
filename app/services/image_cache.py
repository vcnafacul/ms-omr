import logging
from functools import lru_cache

import redis

from app.config import get_settings

logger = logging.getLogger(__name__)
_PREFIX = "omr:img:"


@lru_cache
def _redis() -> "redis.Redis | None":
    s = get_settings()
    if not s.redis_url:
        return None
    try:
        return redis.Redis.from_url(s.redis_url, socket_timeout=2)
    except (ValueError, redis.RedisError):
        logger.warning("REDIS_URL inválida; cache desligado")
        return None


def cache_get(key: str) -> bytes | None:
    """Bytes do cache ou None (Redis off/erro → None, gracioso)."""
    client = _redis()
    if client is None:
        return None
    try:
        return client.get(_PREFIX + key)
    except redis.RedisError as exc:
        logger.warning("cache indisponível (get): %s — usando bucket", exc)
        return None


def cache_set(key: str, data: bytes) -> None:
    """Grava no cache com TTL. No-op se Redis off; erro é engolido (loga)."""
    client = _redis()
    if client is None:
        return
    try:
        client.set(_PREFIX + key, data, ex=get_settings().omr_cache_ttl_seconds)
    except redis.RedisError as exc:
        logger.warning("cache indisponível (set): %s — ignorando", exc)
