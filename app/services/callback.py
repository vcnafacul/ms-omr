import httpx

from app.config import get_settings

_TIMEOUT = 10.0


async def _post(payload: dict) -> None:
    url = get_settings().callback_url
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()  # 4xx/5xx → HTTPStatusError (transitório → arq re-tenta)


async def enviar_resultado_ok(image_key: str, respostas: list[dict]) -> None:
    await _post({"imageKey": image_key, "respostas": respostas})


async def enviar_resultado_falha(image_key: str, motivo: str, detalhe: str | None = None) -> None:
    await _post({"imageKey": image_key, "falha": {"motivo": motivo, "detalhe": detalhe}})
