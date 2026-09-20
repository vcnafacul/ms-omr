import httpx

from app.codigos import CodigoFalha
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
        "tentativaId": None,
    }


async def test_falha_monta_payload(monkeypatch):
    FakeClient.posted = []
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    await callback.enviar_resultado_falha(
        "cartoes/1/a", CodigoFalha.CARTAO_NAO_DETECTADO, "sem markers"
    )
    _, body = FakeClient.posted[0]
    assert body == {
        "imageKey": "cartoes/1/a",
        "falha": {"motivo": "cartao_nao_detectado", "detalhe": "sem markers"},
        "tentativaId": None,
    }


async def test_ok_leva_tentativa_id(monkeypatch):
    FakeClient.posted = []
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    await callback.enviar_resultado_ok("cartoes/1/a", [], tentativa_id="T1")
    _, body = FakeClient.posted[0]
    assert body["tentativaId"] == "T1"


async def test_falha_leva_tentativa_id(monkeypatch):
    FakeClient.posted = []
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    await callback.enviar_resultado_falha(
        "cartoes/1/a", CodigoFalha.ERRO_INTERNO, "x", tentativa_id="T1"
    )
    _, body = FakeClient.posted[0]
    assert body["tentativaId"] == "T1"


async def test_sem_tentativa_id_o_campo_vai_nulo(monkeypatch):
    # ⚠️ O ms-simulado ACEITA callback sem token (job enfileirado antes do
    # deploy). O campo ir como None e' o contrato: nao pode sumir do payload
    # nem virar string vazia, que o `@IsOptional` do outro lado trataria
    # diferente.
    FakeClient.posted = []
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    await callback.enviar_resultado_ok("cartoes/1/a", [])
    _, body = FakeClient.posted[0]
    assert body["tentativaId"] is None
