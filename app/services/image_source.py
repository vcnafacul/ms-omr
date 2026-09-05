from app.services.bucket_storage import baixar_imagem
from app.services.image_cache import cache_get, cache_set


def obter_imagem(key: str) -> bytes:
    """Bytes da imagem do cartão por key. Cache-first read-through:
    Redis (se on) → miss → bucket → grava no cache. Bucket = fonte da verdade.
    Propaga StorageError se o bucket falhar.
    """
    cached = cache_get(key)
    if cached is not None:
        return cached
    data = baixar_imagem(key)
    cache_set(key, data)
    return data
