from app.config import get_settings
from app.services.omr_pipeline import process_cartao
from app.worker import WorkerSettings


def test_worker_settings():
    assert process_cartao in WorkerSettings.functions
    assert WorkerSettings.max_jobs == get_settings().omr_max_workers
