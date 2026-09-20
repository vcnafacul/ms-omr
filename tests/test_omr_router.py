import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.main import app


@pytest.fixture(autouse=True)
def _isolar_worker_e_pool(monkeypatch):
    # Desabilita o worker in-process para não subir um worker real (Redis) nos
    # testes de enqueue. Zera redis_url para que o lifespan não crie um pool real
    # (o .env local pode ter REDIS_URL apontando p/ um Redis no ar) — assim o pool
    # setado por cada teste é preservado.
    monkeypatch.setattr(main.settings, "omr_inprocess_worker", False)
    monkeypatch.setattr(main.settings, "redis_url", None)


class FakePool:
    def __init__(self):
        self.jobs = []

    # ⚠️ `tentativa_id=None` com default: o enfileirar passa 3 argumentos agora,
    # e o default mantem legivel qualquer chamada antiga que sobre no arquivo.
    async def enqueue_job(self, func, image_key, tentativa_id=None):
        self.jobs.append((func, image_key, tentativa_id))
        return object()


def test_202_enfileira():
    app.state.arq_pool = FakePool()
    with TestClient(app) as c:
        r = c.post("/omr/process", json={"imageKey": "cartoes/665/a.jpg"})
    assert r.status_code == 202
    assert r.json()["status"] == "enqueued"
    assert app.state.arq_pool.jobs == [("process_cartao", "cartoes/665/a.jpg", None)]


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


def test_process_aceita_tentativa_id():
    app.state.arq_pool = FakePool()
    with TestClient(app) as c:
        r = c.post(
            "/omr/process",
            json={"imageKey": "cartoes/665/a.jpg", "tentativaId": "T1"},
        )
    assert r.status_code == 202
    assert app.state.arq_pool.jobs[-1] == ("process_cartao", "cartoes/665/a.jpg", "T1")


def test_process_sem_tentativa_id_continua_aceito():
    # ⚠️ Compatibilidade: o ms-simulado velho nao manda o campo, e recusar aqui
    # prenderia todo cartao do periodo em `awaiting_omr`.
    app.state.arq_pool = FakePool()
    with TestClient(app) as c:
        r = c.post("/omr/process", json={"imageKey": "cartoes/665/a.jpg"})
    assert r.status_code == 202
    assert app.state.arq_pool.jobs[-1][2] is None
