import asyncio
import shutil

from app.errors import FalhaNegocio
from app.services import callback
from app.services.bucket_storage import StorageNotFound
from app.services.cartao_reader import ler_cartao
from app.services.image_source import obter_imagem
from app.services.imagekey import parse_simulado_id
from app.services.omr_engine import OmrEngineError
from app.services.template_source import obter_template


def _ler_respostas(image_key: str) -> list[dict]:
    """Parte SÍNCRONA/bloqueante (boto3 + subprocess do OMRChecker). Roda num thread
    via run_in_executor. Levanta FalhaNegocio nos casos de negócio; propaga transitórios."""
    simulado_id = parse_simulado_id(image_key)
    tpl_dir = None
    try:
        try:
            image = obter_imagem(image_key)
        except StorageNotFound as exc:
            raise FalhaNegocio("imagem_nao_encontrada", str(exc)) from exc
        tpl_dir = obter_template(simulado_id)
        try:
            leitura = ler_cartao(image_key, image, tpl_dir)
        except OmrEngineError as exc:
            raise FalhaNegocio("cartao_ilegivel", str(exc)) from exc
        return [r.model_dump() for r in leitura.respostas]
    finally:
        if tpl_dir is not None:
            shutil.rmtree(tpl_dir, ignore_errors=True)


async def process_cartao(ctx, image_key: str) -> None:
    """Task do worker arq (roda in-process). O OMR bloqueante vai pra um thread
    (run_in_executor) → concorrência real até OMR_MAX_WORKERS sem travar a API.
    Falha de negócio → callback `falha` (sem re-raise); transitório propaga → arq re-tenta."""
    loop = asyncio.get_running_loop()
    try:
        respostas = await loop.run_in_executor(None, _ler_respostas, image_key)
        await callback.enviar_resultado_ok(image_key, respostas)
    except FalhaNegocio as fn:
        await callback.enviar_resultado_falha(image_key, fn.motivo, fn.detalhe)
