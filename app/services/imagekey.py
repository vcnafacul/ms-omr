import re

_RE = re.compile(r"^cartoes/(?P<sid>[^/]+)/(?P<img>[^/]+)$")


def is_valid(image_key: str) -> bool:
    return bool(_RE.match(image_key or ""))


def parse_simulado_id(image_key: str) -> str:
    m = _RE.match(image_key or "")
    if not m:
        raise ValueError(f"imageKey inválido: {image_key!r}")
    return m.group("sid")
