from arq import create_pool
from arq.connections import RedisSettings

from app.config import get_settings

_QUEUE_FUNC = "process_cartao"


def _redis_settings() -> RedisSettings:
    dsn = get_settings().redis_url or "redis://localhost:6379"
    return RedisSettings.from_dsn(dsn)


async def criar_pool():
    return await create_pool(_redis_settings())


async def enfileirar(pool, image_key: str):
    return await pool.enqueue_job(_QUEUE_FUNC, image_key)
