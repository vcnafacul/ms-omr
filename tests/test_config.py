from app.config import Settings


def test_worker_defaults():
    s = Settings()
    assert s.omr_max_workers >= 1
    assert s.omr_inprocess_worker is True
