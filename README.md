# ms-omr

Microserviço de OMR (leitura de cartão-resposta) — Python + FastAPI.
Stateless: recebe `imageR2Key`, baixa do R2, lê o cartão e devolve JSON.

## Rodar local (standalone)

```bash
uv venv --python 3.11
uv pip sync requirements-dev.txt
uv run uvicorn app.main:app --reload
# http://localhost:8000/health  →  {"status": "ok"}
# http://localhost:8000/docs    →  Swagger
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
