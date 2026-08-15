from pathlib import Path

import pytest

from app.services.omr_engine import OmrEngineError, run_omr

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cartao-sem-markers-v1"
FOTO = FIXTURE / "foto.jpeg"


@pytest.mark.integration
@pytest.mark.skipif(
    not FOTO.exists(),
    reason="foto.jpeg da fixture sem-markers ainda não fornecida (passo manual)",
)
def test_cartao_sem_markers_levanta_omr_error():
    with pytest.raises(OmrEngineError):
        run_omr(FOTO, FIXTURE)
