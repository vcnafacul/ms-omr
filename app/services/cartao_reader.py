import re
from pathlib import Path

from pydantic import BaseModel

from app.services.omr_engine import run_omr

_ALTERNATIVAS = ("A", "B", "C", "D", "E")
_QUESTAO_KEY = re.compile(r"q(\d+)")
# Matrícula (m1..m8): o cartão de hoje não a lê, e quem lê não a usa — fica fora de `campos`.
_MATRICULA_KEY = re.compile(r"m\d+")


class RespostaCartao(BaseModel):
    questao: str
    alternativaEstudante: str


class LeituraCartao(BaseModel):
    idImage: str
    respostas: list[RespostaCartao]
    # tickets/038 (R13): os demais campos do template, crus e SEM interpretar — ex.:
    # {"idioma": "ING" | "ESP" | "" | "INGESP"} no cartão da prova do ENEM Dia 1 do cursinho.
    # Quem decide o simulado é o ms-simulado. Cartão sem campo extra → {}.
    campos: dict[str, str] = {}


def ler_cartao(id_image: str, image: bytes | str | Path, template_dir: str | Path) -> LeituraCartao:
    """Lê o cartão e devolve as respostas estruturadas, ecoando o idImage.

    Camada pura sobre run_omr (card 02). Propaga OmrEngineError em falha de leitura.
    """
    raw = run_omr(image, template_dir)
    return LeituraCartao(
        idImage=id_image,
        respostas=_estruturar_respostas(raw.fields),
        campos=_demais_campos(raw.fields),
    )


def _estruturar_respostas(fields: dict[str, str]) -> list[RespostaCartao]:
    """Filtra as chaves q<n> com UMA letra A–E. Omite branco ("") e dupla ("AE").

    Ignora m1..m8 (matrícula) e qualquer metadado. Ordena por número da questão.
    """
    out: list[RespostaCartao] = []
    for key, val in fields.items():
        m = _QUESTAO_KEY.fullmatch(key)
        if m and val in _ALTERNATIVAS:
            out.append(RespostaCartao(questao=m.group(1), alternativaEstudante=val))
    out.sort(key=lambda r: int(r.questao))
    return out


def _demais_campos(fields: dict[str, str]) -> dict[str, str]:
    """Tudo que não é questão (q<n>) nem matrícula (m<n>), como o OMRChecker leu.

    O metadado da planilha já sai no `run_omr` (`_METADATA_COLUMNS`). O valor vai cru: com
    várias bolinhas marcadas o OMRChecker concatena ("INGESP"), e com nenhuma devolve "".
    """
    return {
        k: v
        for k, v in fields.items()
        if not _QUESTAO_KEY.fullmatch(k) and not _MATRICULA_KEY.fullmatch(k)
    }
