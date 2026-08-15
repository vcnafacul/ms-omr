from app.queue import _redis_settings
from app.services.omr_pipeline import process_cartao


class WorkerSettings:
    functions = [process_cartao]
    redis_settings = _redis_settings()
    job_timeout = 180
    max_tries = 3
