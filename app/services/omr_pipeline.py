import asyncio
import logging
import shutil

from arq import Retry

from app.codigos import CodigoFalha
from app.config import get_settings
from app.errors import FalhaNegocio
from app.services import callback
from app.services.bucket_storage import StorageError, StorageNotFound
from app.services.cartao_reader import ler_cartao
from app.services.image_source import obter_imagem
from app.services.imagekey import parse_simulado_id
from app.services.omr_engine import OmrEngineError, OmrTimeout
from app.services.template_source import obter_template

logger = logging.getLogger(__name__)

# Espera entre tentativas de um transitório: job_try × isto. Backoff linear (30s, 60s).
_BACKOFF_SEGUNDOS = 30

# Transitório conhecido → código definitivo quando as tentativas se esgotam.
# Lista explícita, e não uma classe-base marcadora: StorageNotFound herda de StorageError
# e é falha de NEGÓCIO (convertida em _ler_respostas). Marcar por herança o tornaria
# transitório sem ninguém perceber.
_CODIGO_POR_TRANSITORIO: dict[type[Exception], CodigoFalha] = {
    OmrTimeout: CodigoFalha.MOTOR_TIMEOUT,
    StorageError: CodigoFalha.ARMAZENAMENTO_INDISPONIVEL,
}


def _tentativa(ctx) -> int:
    """Nº da tentativa atual. O arq sempre entrega um ctx com `job_try` — o default
    existe para um chamador fora do worker, e erra para o lado seguro (mais tentativas)."""
    return (ctx or {}).get("job_try", 1)


def _tem_tentativa_sobrando(ctx) -> bool:
    return _tentativa(ctx) < get_settings().omr_max_tries


def _codigo_transitorio(exc: Exception) -> CodigoFalha:
    for tipo, codigo in _CODIGO_POR_TRANSITORIO.items():
        if isinstance(exc, tipo):
            return codigo
    return CodigoFalha.ERRO_INTERNO


def _ler_respostas(image_key: str) -> list[dict]:
    """Parte SÍNCRONA/bloqueante (boto3 + subprocess do OMRChecker). Roda num thread
    via run_in_executor. Levanta FalhaNegocio nos casos de negócio; propaga transitórios."""
    simulado_id = parse_simulado_id(image_key)
    tpl_dir = None
    try:
        try:
            image = obter_imagem(image_key)
        except StorageNotFound as exc:
            raise FalhaNegocio(CodigoFalha.IMAGEM_NAO_ENCONTRADA, str(exc)) from exc
        tpl_dir = obter_template(simulado_id)
        try:
            leitura = ler_cartao(image_key, image, tpl_dir)
        except OmrEngineError as exc:
            raise FalhaNegocio(exc.codigo, exc.detalhe) from exc
        return [r.model_dump() for r in leitura.respostas]
    finally:
        if tpl_dir is not None:
            shutil.rmtree(tpl_dir, ignore_errors=True)


async def _entregar_ok(
    ctx, image_key: str, respostas: list[dict], tentativa_id: str | None = None
) -> None:
    try:
        await callback.enviar_resultado_ok(image_key, respostas, tentativa_id)
    except Exception as exc:
        _retry_ou_desistir(ctx, image_key, exc)


async def _entregar_falha(
    ctx,
    image_key: str,
    motivo: CodigoFalha,
    detalhe: str | None,
    tentativa_id: str | None = None,
) -> None:
    try:
        await callback.enviar_resultado_falha(image_key, motivo, detalhe, tentativa_id)
    except Exception as exc:
        _retry_ou_desistir(ctx, image_key, exc)


def _retry_ou_desistir(ctx, image_key: str, exc: Exception) -> None:
    """O POST do callback falhou. Re-tenta o job inteiro enquanto houver tentativa — relê
    o cartão, o que é caro mas correto. Esgotado, só resta logar: inventar um status aqui
    marcaria como falho um cartão que pode ter sido lido com sucesso."""
    if _tem_tentativa_sobrando(ctx):
        raise Retry(defer=_tentativa(ctx) * _BACKOFF_SEGUNDOS) from exc
    logger.error(
        "callback de %s não entregue após %d tentativas; histórico segue em awaiting_omr: %s",
        image_key,
        get_settings().omr_max_tries,
        exc,
    )


async def process_cartao(ctx, image_key: str, tentativa_id: str | None = None) -> None:
    """Task do worker arq (roda in-process). O OMR bloqueante vai pra um thread
    (run_in_executor) → concorrência real até OMR_MAX_WORKERS sem travar a API.

    Nenhum caminho pode terminar sem callback: o histórico do ms-simulado fica em
    `awaiting_omr` até um chegar, e o arq NÃO re-tenta exceção comum — só Retry,
    CancelledError e RetryJob (arq/worker.py:610-634). Por isso tudo que não é falha
    de negócio vira `Retry` enquanto houver tentativa, e na última vira callback
    definitivo: o arq descarta o job sem executá-lo quando job_try > max_tries
    (arq/worker.py:550), então a última tentativa é a última chance de avisar.

    ⚠️ Duas saídas ficam fora deste alcance, por construção:
    - o `job_timeout` do arq (worker.py:9, 180s). Ele nasce no `asyncio.wait_for` do próprio
      arq, fora desta coroutine: aqui chega um `CancelledError`, que é BaseException e NÃO é
      capturado (suprimi-lo seria pior), e o `TimeoutError` que o arq enxerga cai no `else`
      dele. Mitigar exige manter o orçamento interno abaixo dos 180s — hoje o subprocess são
      120s e o boto3 está sem timeout explícito. Ver o spec.
    - o POST do callback falhando nas três tentativas; aí `_retry_ou_desistir` só loga.

    Nos dois casos o histórico fica em `awaiting_omr` até a varredura periódica (card próprio).

    ⚠️ `tentativa_id` tem default `None` por obrigação, não por estilo: os jobs já
    enfileirados no Redis no momento do deploy foram serializados com UM argumento.
    Exigir dois posicionais os quebraria na execução, e os cartões correspondentes
    ficariam presos em `awaiting_omr` até a varredura do card 13.
    """
    loop = asyncio.get_running_loop()
    try:
        respostas = await loop.run_in_executor(None, _ler_respostas, image_key)
    except FalhaNegocio as fn:
        await _entregar_falha(ctx, image_key, fn.motivo, fn.detalhe, tentativa_id)
    except Exception as exc:
        # Leitura falhou por algo transitório ou inesperado — OSError de disco cheio,
        # ValidationError, o que for. Antes disso tudo matava o job calado.
        if _tem_tentativa_sobrando(ctx):
            raise Retry(defer=_tentativa(ctx) * _BACKOFF_SEGUNDOS) from exc
        await _entregar_falha(ctx, image_key, _codigo_transitorio(exc), str(exc), tentativa_id)
    else:
        await _entregar_ok(ctx, image_key, respostas, tentativa_id)
