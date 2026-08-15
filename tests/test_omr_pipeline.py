from types import SimpleNamespace

import pytest

from app.services import omr_pipeline as pipe
from app.services.bucket_storage import StorageError, StorageNotFound
from app.services.omr_engine import OmrEngineError


def _leitura():
    return SimpleNamespace(
        respostas=[
            SimpleNamespace(model_dump=lambda: {"questao": "1", "alternativaEstudante": "A"})
        ]
    )


def _patch(monkeypatch, **over):
    calls = {"ok": [], "falha": []}
    monkeypatch.setattr(pipe, "obter_imagem", over.get("obter_imagem", lambda k: b"img"))
    monkeypatch.setattr(
        pipe,
        "obter_template",
        over.get("obter_template", lambda s: __import__("pathlib").Path("/tmp/x")),
    )
    monkeypatch.setattr(pipe, "ler_cartao", over.get("ler_cartao", lambda k, i, t: _leitura()))

    async def ok(k, r):
        calls["ok"].append((k, r))

    async def falha(k, m, d=None):
        calls["falha"].append((k, m, d))

    monkeypatch.setattr(pipe.callback, "enviar_resultado_ok", ok)
    monkeypatch.setattr(pipe.callback, "enviar_resultado_falha", falha)
    monkeypatch.setattr(pipe.shutil, "rmtree", lambda *a, **k: None)
    return calls


async def test_sucesso_callback_ok(monkeypatch):
    calls = _patch(monkeypatch)
    await pipe.process_cartao(None, "cartoes/665/a")
    assert calls["ok"] == [("cartoes/665/a", [{"questao": "1", "alternativaEstudante": "A"}])]
    assert calls["falha"] == []


async def test_ilegivel_callback_falha_sem_reraise(monkeypatch):
    def boom(k, i, t):
        raise OmrEngineError("sem markers")

    calls = _patch(monkeypatch, ler_cartao=boom)
    await pipe.process_cartao(None, "cartoes/665/a")  # não re-raise
    assert calls["falha"][0][1] == "cartao_ilegivel"


async def test_imagem_ausente_callback_falha(monkeypatch):
    def boom(k):
        raise StorageNotFound("imagem não encontrada")

    calls = _patch(monkeypatch, obter_imagem=boom)
    await pipe.process_cartao(None, "cartoes/665/a")
    assert calls["falha"][0][1] == "imagem_nao_encontrada"


async def test_transitorio_reraise(monkeypatch):
    def boom(k):
        raise StorageError("conexão")

    _patch(monkeypatch, obter_imagem=boom)
    with pytest.raises(StorageError):
        await pipe.process_cartao(None, "cartoes/665/a")
