# ms-omr

Microserviço de OMR (*optical mark recognition*) do **Você na Facul** — Python 3.11 + FastAPI.

Recebe a chave de uma foto de cartão-resposta preenchido à mão, baixa a imagem do storage, lê as
marcações com o [OMRChecker](#omrchecker-engine-de-leitura) e devolve o resultado por callback.
Stateless: nada é guardado entre requisições.

## Arquitetura

```
client-vcnafacul  →  api-vcnafacul  →  ms-simulado  →  ms-omr      ← você está aqui
  (React SPA)       (NestJS gateway)    (provas)       (FastAPI + OMRChecker)
                                             ↑              ↓
                                             └─── callback ─┘
```

| Serviço | Stack | Banco | Porta |
|---------|-------|-------|-------|
| **ms-omr** (este) | Python 3.11 + FastAPI | Redis (fila e cache) | `8000` |
| ms-simulado | NestJS 10 + Mongoose | MongoDB | `3000` |
| api-vcnafacul | NestJS 10 + TypeORM | MySQL 8+ | `3333` |
| vcnafacul-form | NestJS 11 + Mongoose | MongoDB | `3001` |
| client-vcnafacul | React 19 + Vite 6 | — | `5173` |

Quem chama o ms-omr é o `ms-simulado` — nunca o frontend. O serviço não é exposto ao público.

## Fluxo de uma leitura

1. `POST /omr/process` com `{"imageKey": "..."}` responde `202` na hora e enfileira o job (arq + Redis)
2. o worker baixa a imagem do bucket (S3 / Cloudflare R2 / MinIO local), com cache no Redis
3. o OMRChecker lê o cartão usando o `template.json` da versão correspondente
4. o resultado vai por `POST` na `CALLBACK_URL` (o `ms-simulado`, em `v1/cartao-resposta/callback`):
   - sucesso → `{"imageKey": "...", "respostas": [...]}`
   - falha → `{"imageKey": "...", "falha": {"motivo": "<código>", "detalhe": "..."}}`

Falhas transitórias são re-tentadas pelo arq até `OMR_MAX_TRIES` (default 3, backoff linear de 30s)
antes de virarem callback. Ver [códigos de falha](#códigos-de-falha-contrato-com-o-ms-simulado).

## Endpoints

| método | rota | o que faz |
|---|---|---|
| `GET` | `/health` | liveness — `{"status": "ok"}` |
| `POST` | `/omr/process` | enfileira a leitura de um `imageKey`; `202` = aceito, não lido ainda |
| `GET` | `/docs` | Swagger |

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

## Rodar junto dos outros serviços

No workspace de desenvolvimento do time (os repositórios clonados lado a lado), `../dev.sh` sobe o
ms-omr junto dos demais — incluindo o MinIO e o Redis de que ele depende — e `../dev.sh stop`
encerra tudo. O script não faz parte deste repositório.

## Qualidade

```bash
uv run ruff check .
uv run black --check .
uv run pytest
```

## Configuração

Variáveis lidas por `app/config.py` (via `.env`). O `.env.example` traz só o subconjunto
necessário para rodar local:

| variável | default | para que serve |
|---|---|---|
| `OMR_PORT` | `8000` | porta do serviço |
| `LOG_LEVEL` | `INFO` | nível de log |
| `TEMPLATE_DIR` | `templates` | raiz dos templates versionados |
| `OMR_BUCKET` | `vcnafacul-cartoes` | bucket das fotos de cartão |
| `AWS_ENDPOINT` / `AWS_REGION` / `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | — | storage (R2 em produção, MinIO local) |
| `REDIS_URL` | — | fila (arq) e cache das imagens |
| `OMR_CACHE_TTL_SECONDS` | `3600` | validade do cache da imagem |
| `CALLBACK_URL` | — | endpoint do `ms-simulado` que recebe o resultado |
| `OMR_MAX_TRIES` | `3` | tentativas antes de desistir de uma falha transitória |
| `OMR_MAX_WORKERS` | `nproc - 1` | leituras simultâneas |
| `OMR_INPROCESS_WORKER` | `true` | roda o worker arq dentro do processo da API |

## Deploy

- `ci-homol.yml` — no merge de um PR em `develop`: builda a imagem, publica no Docker Hub e sobe em
  homologação. Antes de publicar, roda um smoke do motor OMR dentro da imagem.
- `ci-prod.yml` — deploy em produção.

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
  `libglib2.0-0` e `libgomp1` (opencv headless). Nada do motor pode exigir display **em tempo de
  import** — ver o patch abaixo.
- **Patches locais no vendor** (marcados com `# [patch vcnafacul]` no código):
  - `src/utils/interaction.py`: o módulo chamava `get_monitors()[0]` no import e o motor morria no
    container com `ScreenInfoError: No enumerators available` (sem X11 e sem `/dev/dri` o
    `screeninfo` não acha enumerador algum) — todo cartão virava `motor_falhou`. Virou `try/except`
    com dimensão fixa; as dimensões só posicionam janelas, que nunca abrem headless.

  Ao re-copiar o fork, **reaplique os patches** (ou suba-os para o fork antes). `tests/test_headless.py`
  trava a regressão e o CI roda um smoke do import dentro da imagem antes de publicá-la.

Os testes de integração (marca `integration`) rodam o OMRChecker de verdade — contra um sample
vendorizado (`tests/test_omr_engine.py`) e contra uma foto real de cartão preenchido
(`tests/test_cartao_real.py`). O CI só roda `-m "not integration"`, então rode-os localmente antes
de mexer no motor ou no vendor.

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
