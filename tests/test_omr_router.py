from fastapi.testclient import TestClient

from app.main import app


class FakePool:
    def __init__(self):
        self.jobs = []

    async def enqueue_job(self, func, image_key):
        self.jobs.append((func, image_key))
        return object()


def test_202_enfileira():
    app.state.arq_pool = FakePool()
    with TestClient(app) as c:
        r = c.post("/omr/process", json={"imageKey": "cartoes/665/a.jpg"})
    assert r.status_code == 202
    assert r.json()["status"] == "enqueued"
    assert app.state.arq_pool.jobs == [("process_cartao", "cartoes/665/a.jpg")]


def test_400_imagekey_invalido():
    app.state.arq_pool = FakePool()
    with TestClient(app) as c:
        r = c.post("/omr/process", json={"imageKey": "invalido"})
    assert r.status_code == 400


def test_503_sem_pool():
    app.state.arq_pool = None
    with TestClient(app) as c:
        r = c.post("/omr/process", json={"imageKey": "cartoes/665/a.jpg"})
    assert r.status_code == 503
