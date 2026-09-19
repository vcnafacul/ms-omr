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

## Códigos de falha (contrato com o ms-simulado)

Quando a leitura não conclui, o ms-omr faz `POST` no callback com
`{"imageKey": "...", "falha": {"motivo": "<código>", "detalhe": "<texto cru>"}}`.

Fonte única: `app/codigos.py` (`CodigoFalha`). Esta tabela é derivada dele — ao acrescentar um
código, atualize os dois.

| código | o que aconteceu | classe |
|---|---|---|
| `imagem_nao_encontrada` | o objeto não existe no bucket | negócio |
| `template_ausente` | o template do simulado não está publicado | negócio |
| `cartao_nao_detectado` | o OMRChecker rodou e não gerou CSV de Results — não achou o cartão na foto | negócio |
| `leitura_ausente` | o CSV existe, mas sem a linha desta imagem | negócio |
| `motor_falhou` | o OMRChecker saiu com código ≠ 0 (o `detalhe` traz o `stderr`) | negócio |
| `motor_timeout` | o OMRChecker excedeu o tempo, e as re-tentativas se esgotaram | transitório esgotado |
| `armazenamento_indisponivel` | falha de conexão/credencial no storage, e as re-tentativas se esgotaram | transitório esgotado |
| `erro_interno` | falha inesperada no processamento (disco cheio, erro de validação), e as re-tentativas se esgotaram | transitório esgotado |

**Negócio** é determinístico: vira callback na hora, re-tentar daria o mesmo resultado.

**Transitório esgotado** é o oposto — a falha é intermitente, o job foi re-tentado até
`OMR_MAX_TRIES` (default 3, backoff linear de 30s) e só então o callback foi enviado. Ou seja:
**quando um desses códigos chega, não haverá mais nenhuma tentativa automática.** Uma mensagem do
tipo "tentaremos de novo" seria falsa aqui.

⚠️ Dois desfechos não geram callback nenhum, e o histórico do ms-simulado fica em `awaiting_omr`
até a varredura periódica resgatá-lo:

- **O POST do callback não foi entregue nas três tentativas.** O ms-omr apenas registra no log —
  nunca inventa um status de falha para um cartão que pode ter sido lido com sucesso.
- **O `job_timeout` do arq (180s) estourou.** Ele nasce no `asyncio.wait_for` do próprio arq, fora
  da coroutine do pipeline, então o pipeline não tem como convertê-lo em callback. Manter o
  orçamento interno abaixo dos 180s é o que evita isso: hoje o subprocess do OMRChecker são 120s e
  o boto3 está sem timeout explícito (padrão 60s de connect + 60s de read, com re-tentativas
  próprias), então uma leitura de storage lenta o bastante alcança esse limite.

⚠️ Um código desconhecido pelo consumidor não pode virar tela em branco: o ms-simulado precisa de
um caso padrão que mostre algo útil e registre o código não mapeado no log.
