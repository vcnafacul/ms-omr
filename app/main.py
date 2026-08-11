import logging

from fastapi import FastAPI

from app.config import get_settings
from app.routers import health

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="ms-omr", version="0.1.0")
app.include_router(health.router)
