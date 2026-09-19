from types import SimpleNamespace

import pytest
from arq import Retry

from app.codigos import CodigoFalha
from app.services import omr_pipeline as pipe
from app.services.bucket_storage import StorageError, StorageNotFound
from app.services.omr_engine import OmrEngineError, OmrTimeout


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
    monkeypatch.setattr(pipe, "get_settings", lambda: SimpleNamespace(omr_max_tries=3))
    return calls


async def test_sucesso_callback_ok(monkeypatch):
    calls = _patch(monkeypatch)
    await pipe.process_cartao(None, "cartoes/665/a")
    assert calls["ok"] == [("cartoes/665/a", [{"questao": "1", "alternativaEstudante": "A"}])]
    assert calls["falha"] == []


@pytest.mark.parametrize(
    "codigo",
    [
        CodigoFalha.CARTAO_NAO_DETECTADO,
        CodigoFalha.LEITURA_AUSENTE,
        CodigoFalha.MOTOR_FALHOU,
    ],
)
async def test_falha_do_motor_vira_callback_com_o_codigo_e_o_detalhe(monkeypatch, codigo):
    def boom(k, i, t):
        raise OmrEngineError(codigo, "detalhe cru do motor")

    calls = _patch(monkeypatch, ler_cartao=boom)
    await pipe.process_cartao(None, "cartoes/665/a")  # não re-raise

    assert calls["falha"] == [("cartoes/665/a", codigo, "detalhe cru do motor")]
    assert calls["ok"] == []


async def test_imagem_ausente_callback_falha(monkeypatch):
    def boom(k):
        raise StorageNotFound("imagem não encontrada")

    calls = _patch(monkeypatch, obter_imagem=boom)
    await pipe.process_cartao(None, "cartoes/665/a")
    assert calls["falha"][0][1] == "imagem_nao_encontrada"


_TRANSITORIOS = [
    (OmrTimeout("OMRChecker excedeu 120s"), CodigoFalha.MOTOR_TIMEOUT),
    (StorageError("falha de conexão ao storage"), CodigoFalha.ARMAZENAMENTO_INDISPONIVEL),
]


def _patch_transitorio(monkeypatch, exc):
    """Injeta cada transitório no ponto real de onde ele vem: o timeout no motor,
    o StorageError no acesso ao bucket. Injetar os dois no mesmo ponto testaria
    um fluxo que não existe."""

    def boom(*a, **k):
        raise exc

    if isinstance(exc, OmrTimeout):
        return _patch(monkeypatch, ler_cartao=boom)
    return _patch(monkeypatch, obter_imagem=boom)


@pytest.mark.parametrize("exc, codigo", _TRANSITORIOS)
async def test_transitorio_com_tentativa_sobrando_pede_retry(monkeypatch, exc, codigo):
    calls = _patch_transitorio(monkeypatch, exc)

    with pytest.raises(Retry):
        await pipe.process_cartao({"job_try": 1}, "cartoes/665/a")
    assert calls["falha"] == []  # ainda vai tentar de novo — não avisa ninguém ainda


@pytest.mark.parametrize("exc, codigo", _TRANSITORIOS)
async def test_transitorio_na_ultima_tentativa_vira_callback_definitivo(monkeypatch, exc, codigo):
    calls = _patch_transitorio(monkeypatch, exc)

    # job_try == omr_max_tries: o arq descarta o job na próxima, então é aqui ou nunca
    await pipe.process_cartao({"job_try": 3}, "cartoes/665/a")

    assert calls["falha"] == [("cartoes/665/a", codigo, str(exc))]


async def test_storage_not_found_continua_sendo_falha_de_negocio(monkeypatch):
    def boom(k):
        raise StorageNotFound("imagem não encontrada: cartoes/665/a")

    calls = _patch(monkeypatch, obter_imagem=boom)
    await pipe.process_cartao({"job_try": 1}, "cartoes/665/a")  # sem Retry

    assert calls["falha"][0][1] == CodigoFalha.IMAGEM_NAO_ENCONTRADA
