import asyncio
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

# Espera entre tentativas de um transitório: job_try × isto. Backoff linear (30s, 60s).
_BACKOFF_SEGUNDOS = 30


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


async def process_cartao(ctx, image_key: str) -> None:
    """Task do worker arq (roda in-process). O OMR bloqueante vai pra um thread
    (run_in_executor) → concorrência real até OMR_MAX_WORKERS sem travar a API.

    Falha de negócio → callback `falha`, sem re-raise.
    Transitório → `Retry` explícito: o arq NÃO re-tenta exceção comum, só Retry,
    CancelledError e RetryJob (arq/worker.py:610-634). Na última tentativa permitida
    vira callback definitivo, porque o arq descarta o job sem executá-lo quando
    job_try > max_tries (arq/worker.py:550) — seria a última chance de avisar.
    """
    loop = asyncio.get_running_loop()
    try:
        respostas = await loop.run_in_executor(None, _ler_respostas, image_key)
        await callback.enviar_resultado_ok(image_key, respostas)
    except FalhaNegocio as fn:
        await callback.enviar_resultado_falha(image_key, fn.motivo, fn.detalhe)
    except (OmrTimeout, StorageError) as exc:
        # Lista explícita, e não uma classe-base marcadora: StorageNotFound herda de
        # StorageError e é falha de NEGÓCIO (convertida acima). Marcar por herança o
        # tornaria transitório sem ninguém perceber.
        codigo = (
            CodigoFalha.MOTOR_TIMEOUT
            if isinstance(exc, OmrTimeout)
            else CodigoFalha.ARMAZENAMENTO_INDISPONIVEL
        )
        tentativa = (ctx or {}).get("job_try", 1)
        if tentativa >= get_settings().omr_max_tries:
            await callback.enviar_resultado_falha(image_key, codigo, str(exc))
            return
        raise Retry(defer=tentativa * _BACKOFF_SEGUNDOS) from exc
