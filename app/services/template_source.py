import shutil
import tempfile
from pathlib import Path

from app.codigos import CodigoFalha
from app.errors import FalhaNegocio
from app.services.bucket_storage import StorageNotFound, baixar_imagem
from app.services.image_cache import cache_get, cache_set

_TPL_PREFIX = "omr:tpl:"
_MARKER = Path(__file__).resolve().parent.parent / "assets" / "omr_marker.png"


def _baixar_texto(key: str) -> bytes:
    cached = cache_get(key, _TPL_PREFIX)
    if cached is not None:
        return cached
    try:
        data = baixar_imagem(key)  # get genérico por key (Card 05)
    except StorageNotFound as exc:
        raise FalhaNegocio(CodigoFalha.TEMPLATE_AUSENTE, str(exc)) from exc
    cache_set(key, data, _TPL_PREFIX)
    return data


def obter_template(simulado_id: str) -> Path:
    """Baixa template.json + config.json do R2 (cacheados por key), monta um temp dir
    com o marker estático e devolve o Path. FalhaNegocio(template_ausente) se sumir.
    StorageError de conexão propaga (transitório → arq re-tenta). O caller remove o dir."""
    base = f"templates/{simulado_id}"
    template = _baixar_texto(f"{base}/template.json")
    config = _baixar_texto(f"{base}/config.json")
    d = Path(tempfile.mkdtemp(prefix="omr-tpl-"))
    (d / "template.json").write_bytes(template)
    (d / "config.json").write_bytes(config)
    shutil.copy(_MARKER, d / "omr_marker.png")
    return d
