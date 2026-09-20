import httpx

from app.config import get_settings

_TIMEOUT = 10.0


async def _post(payload: dict) -> None:
    url = get_settings().callback_url
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        # 4xx/5xx → HTTPStatusError; quem re-tenta é o pipeline, via arq.Retry
        resp.raise_for_status()


async def enviar_resultado_ok(
    image_key: str, respostas: list[dict], tentativa_id: str | None = None
) -> None:
    await _post({"imageKey": image_key, "respostas": respostas, "tentativaId": tentativa_id})


async def enviar_resultado_falha(
    image_key: str,
    motivo: str,
    detalhe: str | None = None,
    tentativa_id: str | None = None,
) -> None:
    await _post(
        {
            "imageKey": image_key,
            "falha": {"motivo": motivo, "detalhe": detalhe},
            "tentativaId": tentativa_id,
        }
    )
