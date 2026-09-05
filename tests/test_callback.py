import httpx

from app.services import callback


class FakeResp:
    def raise_for_status(self):
        pass


class FakeClient:
    posted = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json):
        FakeClient.posted.append((url, json))
        return FakeResp()


async def test_ok_monta_payload(monkeypatch):
    FakeClient.posted = []
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    await callback.enviar_resultado_ok(
        "cartoes/1/a", [{"questao": "1", "alternativaEstudante": "A"}]
    )
    url, body = FakeClient.posted[0]
    assert body == {
        "imageKey": "cartoes/1/a",
        "respostas": [{"questao": "1", "alternativaEstudante": "A"}],
    }


async def test_falha_monta_payload(monkeypatch):
    FakeClient.posted = []
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    await callback.enviar_resultado_falha("cartoes/1/a", "cartao_ilegivel", "sem markers")
    _, body = FakeClient.posted[0]
    assert body == {
        "imageKey": "cartoes/1/a",
        "falha": {"motivo": "cartao_ilegivel", "detalhe": "sem markers"},
    }
