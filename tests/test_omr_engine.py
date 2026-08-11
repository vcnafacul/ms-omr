from pathlib import Path

import pytest

from app.services.omr_engine import OmrEngineError, run_omr


def test_run_omr_raises_on_invalid_template(tmp_path: Path):
    # template_dir vazio (sem template.json) + imagem → OMRChecker acha imagem sem template
    # → OmrEngineError (NOT "Unknown arguments" / exit 11)
    with pytest.raises(OmrEngineError):
        run_omr(b"not-a-real-image", tmp_path)
