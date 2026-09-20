from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.queue import enfileirar
from app.services.imagekey import is_valid

router = APIRouter(tags=["omr"])


class ProcessIn(BaseModel):
    imageKey: str
    # ⚠️ Opcional de propósito: o ms-simulado ainda não implantado não manda o
    # campo, e recusar aqui prenderia todo cartão do período em `awaiting_omr`.
    tentativaId: str | None = None


@router.post("/omr/process", status_code=202)
async def process(body: ProcessIn, request: Request) -> dict:
    if not is_valid(body.imageKey):
        raise HTTPException(status_code=400, detail="imageKey inválido")
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="fila indisponível")
    await enfileirar(pool, body.imageKey, body.tentativaId)
    return {"status": "enqueued", "imageKey": body.imageKey}
