import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.queue import criar_pool
from app.routers import health, omr

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if getattr(app.state, "arq_pool", None) is None and settings.redis_url:
        try:
            app.state.arq_pool = await criar_pool()
        except Exception as exc:  # Redis indisponível → fila off (503 no endpoint)
            logging.getLogger(__name__).warning("pool arq indisponível: %s", exc)
            app.state.arq_pool = None
    elif not hasattr(app.state, "arq_pool"):
        app.state.arq_pool = None
    yield
    pool = getattr(app.state, "arq_pool", None)
    close = getattr(pool, "close", None)
    if close is not None:
        await close()


app = FastAPI(title="ms-omr", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(omr.router)
