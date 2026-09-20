import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.codigos import CodigoFalha
from app.services.omr_engine import OmrEngineError, OmrTimeout, RawOmrResult, run_omr

_SAMPLE_DIR = Path(__file__).resolve().parents[1] / "vendor" / "omrchecker" / "samples" / "sample4"


def test_run_omr_raises_on_invalid_template(tmp_path: Path):
    # template_dir vazio (sem template.json) + imagem → OMRChecker acha imagem sem template
    # → OmrEngineError (NOT "Unknown arguments" / exit 11)
    with pytest.raises(OmrEngineError) as ei:
        run_omr(b"not-a-real-image", tmp_path)

    assert ei.value.codigo == CodigoFalha.MOTOR_FALHOU
    # a falha tem que ser a do template ausente, e não qualquer morte do motor: sem esta
    # asserção o teste ficava verde no CI justamente quando o motor nem chegava a subir
    # (foi assim que o ScreenInfoError headless passou batido — ver tests/test_headless.py)
    assert "No template file found" in ei.value.detalhe


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


def _template_dir(tmp_path: Path) -> Path:
    # run_omr faz copytree(template_dir, input_dir) — basta o diretório existir
    d = tmp_path / "tpl"
    d.mkdir()
    return d


def _proc(returncode: int, stderr: str = ""):
    return SimpleNamespace(returncode=returncode, stderr=stderr, stdout="")


def test_timeout_do_motor_vira_omr_timeout(tmp_path: Path, monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="omrchecker", timeout=120)

    monkeypatch.setattr(subprocess, "run", boom)

    with pytest.raises(OmrTimeout) as ei:
        run_omr(b"img", _template_dir(tmp_path))
    # é irmã, não filha — o pipeline precisa poder tratá-las separado
    assert not isinstance(ei.value, OmrEngineError)


def test_motor_abortado_vira_motor_falhou_com_stderr_no_detalhe(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(11, "traceback do motor"))

    with pytest.raises(OmrEngineError) as ei:
        run_omr(b"img", _template_dir(tmp_path))
    assert ei.value.codigo == CodigoFalha.MOTOR_FALHOU
    assert "traceback do motor" in ei.value.detalhe


def test_sem_csv_de_results_vira_cartao_nao_detectado(tmp_path: Path, monkeypatch):
    # rodou até o fim (exit 0) e não produziu Results → não achou o cartão na foto
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0))

    with pytest.raises(OmrEngineError) as ei:
        run_omr(b"img", _template_dir(tmp_path))
    assert ei.value.codigo == CodigoFalha.CARTAO_NAO_DETECTADO


def test_imagem_fora_do_csv_vira_leitura_ausente(tmp_path: Path, monkeypatch):
    def run_criando_csv_de_outra_imagem(cmd, **kwargs):
        output_dir = Path(cmd[cmd.index("-o") + 1])
        results = output_dir / "Results"
        results.mkdir(parents=True)
        (results / "r.csv").write_text("file_id,q1\noutra_imagem.png,A\n")
        return _proc(0)

    monkeypatch.setattr(subprocess, "run", run_criando_csv_de_outra_imagem)

    with pytest.raises(OmrEngineError) as ei:
        run_omr(b"img", _template_dir(tmp_path))
    assert ei.value.codigo == CodigoFalha.LEITURA_AUSENTE
