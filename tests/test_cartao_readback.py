from pathlib import Path

import cv2
import pytest

from app.services.omr_engine import run_omr
from tests.helpers.synthetic_card import render_synthetic_card

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cartao-v1"


@pytest.mark.integration
def test_readback_sintetico(tmp_path):
    marcas = {
        "matricula": [1, 2, 3, 4, 5, 6, 7, 8],
        "q1": 0,  # A
        "q2": 4,  # E
        "q30": 2,  # C
        "q61": 3,  # D
    }
    img = render_synthetic_card(FIXTURE, marcas)
    img_path = tmp_path / "sintetico.png"
    cv2.imwrite(str(img_path), img)

    result = run_omr(img_path, FIXTURE)

    matricula = "".join(result.fields.get(f"m{i}", "") for i in range(1, 9))
    assert matricula == "12345678", f"matrícula lida: {matricula!r} | fields={result.fields}"
    assert result.fields.get("q1") == "A", result.fields
    assert result.fields.get("q2") == "E", result.fields
    assert result.fields.get("q30") == "C", result.fields
    assert result.fields.get("q61") == "D", result.fields
