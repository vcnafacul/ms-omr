# ms-omr

Microserviço de OMR (leitura de cartão-resposta) — Python + FastAPI.
Stateless: recebe `imageR2Key`, baixa do R2, lê o cartão e devolve JSON.

## Rodar local (standalone)

```bash
uv venv --python 3.11
uv pip install -r requirements-dev.txt
uv run uvicorn app.main:app --reload
# http://localhost:8000/health  →  {"status": "ok"}
# http://localhost:8000/docs    →  Swagger
```

## Rodar via Docker (local)

```bash
make up      # build da imagem + sobe o container (detached) em localhost:8000
make logs    # acompanha os logs do container
make down    # para e remove o container
```

## Rodar via monorepo

`../dev.sh` sobe o ms-omr junto dos demais serviços (porta 8000).
`../dev.sh stop` encerra tudo.

## Qualidade

```bash
uv run ruff check .
uv run black --check .
uv run pytest
```
