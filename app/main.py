import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from arq.worker import create_worker
from fastapi import FastAPI

from app.config import get_settings
from app.queue import criar_pool
from app.routers import health, omr
from app.worker import WorkerSettings

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # pool p/ enfileirar
    if getattr(app.state, "arq_pool", None) is None and settings.redis_url:
        try:
            app.state.arq_pool = await criar_pool()
        except Exception as exc:  # Redis fora → fila off (503 no endpoint)
            logging.getLogger(__name__).warning("pool arq indisponível: %s", exc)
            app.state.arq_pool = None
    elif not hasattr(app.state, "arq_pool"):
        app.state.arq_pool = None

    # worker in-process (Opção A) — mesmo processo do uvicorn
    worker = None
    if settings.omr_inprocess_worker and app.state.arq_pool is not None:
        # handle_signals=False: o lifespan do uvicorn é quem dirige o shutdown;
        # sem isso o arq sequestra SIGINT/SIGTERM do uvicorn no loop compartilhado.
        worker = create_worker(WorkerSettings, handle_signals=False)
        app.state.arq_worker_task = asyncio.create_task(worker.async_run())
        logging.getLogger(__name__).info(
            "worker arq in-process iniciado (max_jobs=%s)", settings.omr_max_workers
        )

    yield

    if worker is not None:
        task = getattr(app.state, "arq_worker_task", None)
        if task is not None:
            task.cancel()  # para o loop de poll do async_run()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await worker.close()
    pool = getattr(app.state, "arq_pool", None)
    close = getattr(pool, "close", None)
    if close is not None:
        await close()


app = FastAPI(title="ms-omr", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(omr.router)
