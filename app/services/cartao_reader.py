import re
from pathlib import Path

from pydantic import BaseModel

from app.services.omr_engine import run_omr

_ALTERNATIVAS = ("A", "B", "C", "D", "E")


class RespostaCartao(BaseModel):
    questao: str
    alternativaEstudante: str


class LeituraCartao(BaseModel):
    idImage: str
    respostas: list[RespostaCartao]


def ler_cartao(id_image: str, image: bytes | str | Path, template_dir: str | Path) -> LeituraCartao:
    """Lê o cartão e devolve as respostas estruturadas, ecoando o idImage.

    Camada pura sobre run_omr (card 02). Propaga OmrEngineError em falha de leitura.
    """
    raw = run_omr(image, template_dir)
    return LeituraCartao(idImage=id_image, respostas=_estruturar_respostas(raw.fields))


def _estruturar_respostas(fields: dict[str, str]) -> list[RespostaCartao]:
    """Filtra as chaves q<n> com UMA letra A–E. Omite branco ("") e dupla ("AE").

    Ignora m1..m8 (matrícula) e qualquer metadado. Ordena por número da questão.
    """
    out: list[RespostaCartao] = []
    for key, val in fields.items():
        m = re.fullmatch(r"q(\d+)", key)
        if m and val in _ALTERNATIVAS:
            out.append(RespostaCartao(questao=m.group(1), alternativaEstudante=val))
    out.sort(key=lambda r: int(r.questao))
    return out
