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


_TRANSITORIOS = [
    (lambda: OmrTimeout("OMRChecker excedeu 120s"), CodigoFalha.MOTOR_TIMEOUT),
    (lambda: StorageError("falha de conexão ao storage"), CodigoFalha.ARMAZENAMENTO_INDISPONIVEL),
]


def _patch_transitorio(monkeypatch, exc_factory):
    """Injeta cada transitório no ponto real de onde ele vem: o timeout no motor,
    o StorageError no acesso ao bucket. Injetar os dois no mesmo ponto testaria
    um fluxo que não existe."""
    exc = exc_factory()

    def boom(*a, **k):
        raise exc

    if isinstance(exc, OmrTimeout):
        return _patch(monkeypatch, ler_cartao=boom), exc
    return _patch(monkeypatch, obter_imagem=boom), exc


@pytest.mark.parametrize("exc_factory, codigo", _TRANSITORIOS)
async def test_transitorio_com_tentativa_sobrando_pede_retry(monkeypatch, exc_factory, codigo):
    calls, _exc = _patch_transitorio(monkeypatch, exc_factory)

    with pytest.raises(Retry):
        await pipe.process_cartao({"job_try": 1}, "cartoes/665/a")
    assert calls["falha"] == []  # ainda vai tentar de novo — não avisa ninguém ainda


@pytest.mark.parametrize("exc_factory, codigo", _TRANSITORIOS)
async def test_transitorio_na_ultima_tentativa_vira_callback_definitivo(
    monkeypatch, exc_factory, codigo
):
    calls, exc = _patch_transitorio(monkeypatch, exc_factory)

    # job_try == omr_max_tries: o arq descarta o job na próxima, então é aqui ou nunca
    await pipe.process_cartao({"job_try": 3}, "cartoes/665/a")

    assert calls["falha"] == [("cartoes/665/a", codigo, str(exc))]


async def test_storage_not_found_continua_sendo_falha_de_negocio(monkeypatch):
    def boom(k):
        raise StorageNotFound("imagem não encontrada: cartoes/665/a")

    calls = _patch(monkeypatch, obter_imagem=boom)
    await pipe.process_cartao({"job_try": 1}, "cartoes/665/a")  # sem Retry

    assert calls["falha"][0][1] == CodigoFalha.IMAGEM_NAO_ENCONTRADA


async def test_retry_usa_backoff_linear_por_tentativa(monkeypatch):
    def boom(*a, **k):
        raise OmrTimeout("OMRChecker excedeu 120s")

    _patch(monkeypatch, ler_cartao=boom)

    with pytest.raises(Retry) as primeira:
        await pipe.process_cartao({"job_try": 1}, "cartoes/665/a")
    with pytest.raises(Retry) as segunda:
        await pipe.process_cartao({"job_try": 2}, "cartoes/665/a")

    assert primeira.value.defer_score == 30_000  # ms
    assert segunda.value.defer_score == 60_000


async def test_erro_inesperado_na_leitura_re_tenta_e_depois_avisa(monkeypatch):
    # disco cheio, ValidationError, o TimeoutError do job_timeout do arq: antes matava
    # o job em silêncio e o histórico ficava preso em awaiting_omr
    def boom(*a, **k):
        raise OSError("No space left on device")

    calls = _patch(monkeypatch, ler_cartao=boom)

    with pytest.raises(Retry):
        await pipe.process_cartao({"job_try": 1}, "cartoes/665/a")
    assert calls["falha"] == []

    await pipe.process_cartao({"job_try": 3}, "cartoes/665/a")
    assert calls["falha"] == [
        ("cartoes/665/a", CodigoFalha.ERRO_INTERNO, "No space left on device")
    ]


async def test_callback_de_sucesso_que_falha_re_tenta_o_job(monkeypatch):
    _patch(monkeypatch)

    async def post_quebrado(*a, **k):
        raise RuntimeError("ms-simulado fora do ar")

    monkeypatch.setattr(pipe.callback, "enviar_resultado_ok", post_quebrado)

    with pytest.raises(Retry):
        await pipe.process_cartao({"job_try": 1}, "cartoes/665/a")


async def test_callback_de_sucesso_esgotado_nao_inventa_falha(monkeypatch):
    # o cartão FOI lido; marcar como falho por não conseguir entregar seria mentir
    calls = _patch(monkeypatch)

    async def post_quebrado(*a, **k):
        raise RuntimeError("ms-simulado fora do ar")

    monkeypatch.setattr(pipe.callback, "enviar_resultado_ok", post_quebrado)

    await pipe.process_cartao({"job_try": 3}, "cartoes/665/a")  # não levanta
    assert calls["falha"] == []


async def test_callback_de_falha_que_falha_re_tenta_o_job(monkeypatch):
    def boom(k, i, t):
        raise OmrEngineError(CodigoFalha.CARTAO_NAO_DETECTADO, "sem CSV")

    _patch(monkeypatch, ler_cartao=boom)

    async def post_quebrado(*a, **k):
        raise RuntimeError("ms-simulado fora do ar")

    monkeypatch.setattr(pipe.callback, "enviar_resultado_falha", post_quebrado)

    with pytest.raises(Retry):
        await pipe.process_cartao({"job_try": 1}, "cartoes/665/a")


async def test_pipeline_honra_o_teto_configurado(monkeypatch):
    # prova que o pipeline lê omr_max_tries de verdade: com teto 1, a primeira
    # tentativa já é a última e vai direto para o callback, sem Retry
    def boom(*a, **k):
        raise OmrTimeout("OMRChecker excedeu 120s")

    calls = _patch(monkeypatch, ler_cartao=boom)
    monkeypatch.setattr(pipe, "get_settings", lambda: SimpleNamespace(omr_max_tries=1))

    await pipe.process_cartao({"job_try": 1}, "cartoes/665/a")  # não levanta Retry
    assert calls["falha"][0][1] == CodigoFalha.MOTOR_TIMEOUT
