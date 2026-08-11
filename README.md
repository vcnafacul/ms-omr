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

## OMRChecker (engine de leitura)

O `ms-omr` usa o [OMRChecker](https://github.com/Udayraj123/OMRChecker) (licença MIT) como
engine de OMR, invocado por **subprocess** (`app/services/omr_engine.py` é o único módulo que o
conhece).

- **Fork:** `vcnafacul/OMRChecker` — durabilidade e upstream para upgrades/patches.
- **Commit pinado:** `de3f6982822895491be760325fd43e65e90fa293`
- **Vendorizado em:** `vendor/omrchecker/` (repo inteiro, sem `.git`). Upgrade = re-copiar de um
  commit novo do fork e atualizar o SHA acima.
- **Templates:** formato nativo `template.json` (não YAML), lido de dentro do diretório de
  entrada. Versionados por diretório: `templates/<versão>/template.json`.
- **Contrato do wrapper:** `run_omr(image, template_dir)` — `template_dir` deve conter os assets do
  template (`template.json` + `config.json` + markers), **não** folhas de resposta.
- **Headless:** o wrapper força `outputs.show_image_level = 0` no config (evita `cv2.imshow`/
  `plt.show`, que travam sem display) e roda com `MPLBACKEND=Agg`. Container precisa de
  `libglib2.0-0` e `libgomp1` (opencv headless).

O teste de integração (`tests/test_omr_engine.py`, marca `integration`) roda o OMRChecker de
verdade contra um sample vendorizado.
