import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from pydantic import BaseModel

from app.codigos import CodigoFalha

# ms-omr/app/services/omr_engine.py → parents[2] = ms-omr/
VENDOR_MAIN = Path(__file__).resolve().parents[2] / "vendor" / "omrchecker" / "main.py"

_TIMEOUT_SECONDS = 120
_INPUT_STEM = "__omr_input__"
# colunas de bookkeeping do OMRChecker (não são leitura de campo)
_METADATA_COLUMNS = ("file_id", "input_path", "output_path", "score")


class OmrEngineError(Exception):
    """Falha determinística do OMRChecker — vira callback `falha`, NÃO re-tenta.

    Carrega `codigo` (contrato com o ms-simulado) e `detalhe` (texto cru, para investigação).
    """

    def __init__(self, codigo: CodigoFalha, detalhe: str) -> None:
        super().__init__(f"{codigo}: {detalhe}")
        self.codigo = codigo
        self.detalhe = detalhe


class OmrTimeout(Exception):
    """O OMRChecker excedeu o tempo. Transitório — o pipeline re-tenta via arq.Retry.

    NÃO herda de OmrEngineError de propósito: é essa separação que impede o pipeline
    de tratá-lo como falha determinística, que é o bug que esta classe existe para corrigir.
    """


class RawOmrResult(BaseModel):
    fields: dict[str, str]
    file_id: str | None = None


def run_omr(image: bytes | str | Path, template_dir: str | Path) -> RawOmrResult:
    """Roda o OMRChecker (subprocess) contra uma imagem, usando o template.json de template_dir.

    Único ponto do serviço que conhece o OMRChecker. O OMRChecker lê o template.json de dentro do
    diretório de entrada, então copiamos template_dir (template.json + config/assets) pro input e
    adicionamos a imagem. Se template_dir contiver outras imagens, elas também são lidas
    (desperdício), mas devolvemos só a leitura da imagem passada. Limpa os temporários ao final.
    """
    with tempfile.TemporaryDirectory(prefix="omr-") as tmp:
        tmp_path = Path(tmp)
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"

        # copytree cria input_dir com o conteúdo do template (template.json, config.json, markers…)
        shutil.copytree(template_dir, input_dir)
        output_dir.mkdir()

        # serviço headless: nunca deixar o OMRChecker exibir imagens (trava em waitKey/plt.show)
        _force_headless_config(input_dir)

        image_name = f"{_INPUT_STEM}{_image_suffix(image)}"
        target = input_dir / image_name
        if isinstance(image, bytes):
            target.write_bytes(image)
        else:
            shutil.copyfile(image, target)

        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(VENDOR_MAIN),
                    "-i",
                    str(input_dir),
                    "-o",
                    str(output_dir),
                ],
                cwd=str(VENDOR_MAIN.parent),
                env={**os.environ, "MPLBACKEND": "Agg"},
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise OmrTimeout(f"OMRChecker excedeu {_TIMEOUT_SECONDS}s") from exc

        if proc.returncode != 0:
            raise OmrEngineError(
                CodigoFalha.MOTOR_FALHOU,
                f"OMRChecker saiu com código {proc.returncode}: {proc.stderr[-2000:]}",
            )

        return _parse_results(output_dir, image_name)


def _image_suffix(image: bytes | str | Path) -> str:
    if isinstance(image, bytes):
        return ".png"
    return Path(image).suffix or ".png"


def _force_headless_config(input_dir: Path) -> None:
    """Força ``outputs.show_image_level = 0`` no config.json do input dir.

    O OMRChecker, com ``show_image_level`` > 0, abre janelas (cv2.imshow/plt.show) que travam
    num ambiente headless/serviço. O default do OMRChecker é 0, mas um template pode trazer um
    config.json com valor maior — aqui garantimos que nunca haja display, seja qual for o template.
    """
    config_path = input_dir / "config.json"
    if not config_path.exists():
        return
    try:
        config = json.loads(config_path.read_text())
        outputs = config.setdefault("outputs", {})
        outputs["show_image_level"] = 0
        config_path.write_text(json.dumps(config))
    except (OSError, ValueError, TypeError, AttributeError):
        # config.json malformado: deixa o OMRChecker lidar (usa defaults / erra explicitamente)
        return


def _parse_results(output_dir: Path, image_name: str) -> RawOmrResult:
    csvs = sorted(output_dir.rglob("Results/*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not csvs:
        raise OmrEngineError(
            CodigoFalha.CARTAO_NAO_DETECTADO, "OMRChecker não gerou CSV de Results"
        )

    row = _find_row(csvs, image_name)
    if row is None:
        raise OmrEngineError(
            CodigoFalha.LEITURA_AUSENTE, f"leitura de '{image_name}' ausente no CSV de Results"
        )

    file_id = (row.get("file_id") or "").strip() or None
    fields = {k: (v or "") for k, v in row.items() if k not in _METADATA_COLUMNS}
    return RawOmrResult(fields=fields, file_id=file_id)


def _find_row(csvs: list[Path], image_name: str) -> dict[str, str] | None:
    for candidate in csvs:
        with candidate.open(newline="") as fh:
            for r in csv.DictReader(fh):
                if Path((r.get("file_id") or "").strip()).name == image_name:
                    return r
    return None
