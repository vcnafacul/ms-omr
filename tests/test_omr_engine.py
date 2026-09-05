import shutil
from pathlib import Path

import pytest

from app.services.omr_engine import OmrEngineError, RawOmrResult, run_omr

_SAMPLE_DIR = Path(__file__).resolve().parents[1] / "vendor" / "omrchecker" / "samples" / "sample4"


def test_run_omr_raises_on_invalid_template(tmp_path: Path):
    # template_dir vazio (sem template.json) + imagem → OMRChecker acha imagem sem template
    # → OmrEngineError (NOT "Unknown arguments" / exit 11)
    with pytest.raises(OmrEngineError):
        run_omr(b"not-a-real-image", tmp_path)


@pytest.mark.integration
def test_run_omr_returns_structured_result(tmp_path: Path):
    # template_dir "limpo": só os assets do template (template.json + config.json), sem folhas.
    # O config.json do sample4 traz show_image_level=5 (display) — passamos de propósito pra
    # exercitar o headless-guard do wrapper (deve forçar 0 e NÃO travar).
    template_dir = tmp_path / "template"
    template_dir.mkdir()
    shutil.copy(_SAMPLE_DIR / "template.json", template_dir)
    shutil.copy(_SAMPLE_DIR / "config.json", template_dir)

    image = sorted(_SAMPLE_DIR.glob("*.jpg"))[0]

    result = run_omr(image, template_dir)

    assert isinstance(result, RawOmrResult)
    assert len(result.fields) > 0
    assert result.file_id == "__omr_input__.jpg"
