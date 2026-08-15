import shutil

from app.errors import FalhaNegocio
from app.services import callback
from app.services.bucket_storage import StorageNotFound
from app.services.cartao_reader import ler_cartao
from app.services.image_source import obter_imagem
from app.services.imagekey import parse_simulado_id
from app.services.omr_engine import OmrEngineError
from app.services.template_source import obter_template


async def process_cartao(ctx, image_key: str) -> None:
    """Task do worker arq. Falha de negócio → callback `falha` (sem re-raise).
    Erro transitório (StorageError de conexão, callback caiu) propaga → arq re-tenta."""
    simulado_id = parse_simulado_id(image_key)
    tpl_dir = None
    try:
        try:
            image = obter_imagem(image_key)
        except StorageNotFound as exc:
            raise FalhaNegocio("imagem_nao_encontrada", str(exc)) from exc
        tpl_dir = obter_template(simulado_id)  # FalhaNegocio(template_ausente) se sumir
        try:
            leitura = ler_cartao(image_key, image, tpl_dir)
        except OmrEngineError as exc:
            raise FalhaNegocio("cartao_ilegivel", str(exc)) from exc
        await callback.enviar_resultado_ok(image_key, [r.model_dump() for r in leitura.respostas])
    except FalhaNegocio as fn:
        await callback.enviar_resultado_falha(image_key, fn.motivo, fn.detalhe)
    finally:
        if tpl_dir is not None:
            shutil.rmtree(tpl_dir, ignore_errors=True)
