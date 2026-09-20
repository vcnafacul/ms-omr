"""O motor OMR tem que importar num ambiente sem monitor nenhum (container headless).

Regressão do bug de homolog: ``vendor/omrchecker/src/utils/interaction.py`` chamava
``get_monitors()[0]`` em tempo de import. No container (python:3.11-slim, sem X11 e sem
/dev/dri) o screeninfo não acha enumerador algum e levanta
``ScreenInfoError("No enumerators available")`` — o motor morria com exit 1 antes de olhar
a imagem, e todo cartão virava MOTOR_FALHOU no callback.

O headless é simulado (stub do screeninfo) em vez de depender do ambiente: assim o teste
vale também no Mac do dev, onde ``get_monitors()`` funciona de verdade e o bug some.
"""

import subprocess
import sys
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[1] / "vendor" / "omrchecker"

# roda num subprocess porque o stub precisa estar em sys.modules ANTES do primeiro import
_IMPORTA_SEM_MONITOR = """
import sys
import types


class ScreenInfoError(Exception):
    pass


def get_monitors(*args, **kwargs):
    raise ScreenInfoError("No enumerators available")


common = types.ModuleType("screeninfo.common")
common.ScreenInfoError = ScreenInfoError

fake = types.ModuleType("screeninfo")
fake.common = common
fake.ScreenInfoError = ScreenInfoError
fake.get_monitors = get_monitors

sys.modules["screeninfo"] = fake
sys.modules["screeninfo.common"] = common

# mesma cadeia do traceback de homolog: entry -> template -> core -> utils.interaction
import src.entry  # noqa: F401

print("import ok")
"""


def test_motor_importa_sem_monitor_disponivel():
    proc = subprocess.run(
        [sys.executable, "-c", _IMPORTA_SEM_MONITOR],
        cwd=str(VENDOR),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert proc.returncode == 0, f"motor não importa headless:\n{proc.stderr[-2000:]}"
    assert "ScreenInfoError" not in proc.stderr
