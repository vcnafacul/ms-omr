# Deploy do ms-omr em Homologação

Espelha o padrão dos outros serviços (api/ms-simulado/form): a pipeline builda a imagem
Docker, publica no Docker Hub e faz SSH no servidor de homolog rodando um script `subir_*.sh`
que sobe o container na rede `network-vcnafacul`.

Servidor homol: **VPS Hostinger `85.31.61.20`**, **1 vCPU / 4GB RAM** — máquina separada da de
produção (também Hostinger, 2 vCPU / 8GB). Auth SSH por **senha** nos dois.

## Arquivos deste PR/pasta

| Arquivo | O quê | Vai pra onde |
|---|---|---|
| `.github/workflows/ci-homol.yml` | Workflow de homolog: **CI** (ruff/black/pytest no PR) → **PUSH** (build+push `vcnafacul/ms-omr:latest`) → **DEPLOY_HOMOL** (SSH roda `subir_ms_omr.sh`) | repo ms-omr |
| `.github/workflows/ci-prod.yml` | Workflow de produção (push de tag `1.2.0`): **BUILD_AND_PUSH** (`:<tag>` + `:stable`) → **DEPLOY_PROD** → **CREATE_RELEASE**. Igual ao `ci-prod.yml` do api/ms-simulado/form | repo ms-omr |
| `deploy/subir_ms_omr.sh` | Script de subida do container em **homol** (`:latest`, interno, sem porta publicada) | **copiar pra `~/subir_ms_omr.sh`** no servidor de homol |
| `deploy/subir_ms_omr.prod.sh` | Mesmo script para **prod** (`:stable`, limites maiores) | **copiar pra `~/subir_ms_omr.sh`** no servidor de prod |
| `deploy/subir_redis.sh` | Sobe um Redis leve na rede (**homol não tem Redis hoje**) | **copiar pra `~/subir_redis.sh`** e rodar 1x |
| `deploy/.env.omr.example` | Template das envs do ms-omr | **preencher → `~/env/.env.omr`** no servidor |
| `deploy/README.md` | Este guia | repo ms-omr |

> Nada aqui foi pushado/deployado — é tudo pra você revisar. Os scripts/env **não** são
> auto-copiados pro servidor; você coloca `subir_ms_omr.sh`, `subir_redis.sh` e `env/.env.omr`
> no `~` do servidor (uma vez).

## ⚠️ Dois pré-requisitos que descobri no servidor

### 1. Não existe Redis em homol
`REDIS_HOST=localhost` no `~/env/.env` do api aponta pra nada (nenhum container/host escutando
6379). O **ms-omr precisa de Redis** (fila `arq`; sem ele `/omr/process` = 503) e o **ms-simulado
também** (fila de respostas disparada pelo callback do cartão). Solução: `subir_redis.sh`
(container `vcnafacul_redis` na rede). Rodar 1x:
```bash
chmod +x ~/subir_redis.sh && ~/subir_redis.sh
```

### 2. Em homol o gargalo é CPU, não RAM
Homol tem 4GB (folga de sobra pro opencv) mas **1 vCPU só**, dividido com api/ms-simulado/redis.
O OMR é CPU-bound: sem limite, uma leitura monopoliza o núcleo e a API engasga junto. Daí
`--cpus 0.75` + `--memory 1g` no `subir_ms_omr.sh`, e `OMR_MAX_WORKERS=1` no `.env.omr`
(1 núcleo → não adianta paralelizar).

**Produção (2 vCPU / 8GB)** tem folga maior: `subir_ms_omr.prod.sh` usa `--memory 2g --cpus 1.5`.
`OMR_MAX_WORKERS=1` continua adequado mesmo lá.

## Passo a passo no servidor (uma vez)

```bash
# 1) Redis (novo)
#   copie deploy/subir_redis.sh -> ~/subir_redis.sh
chmod +x ~/subir_redis.sh && ~/subir_redis.sh

# 2) Env do ms-omr
#   copie deploy/.env.omr.example -> ~/env/.env.omr e PREENCHA as credenciais R2 (iguais às do api)

# 3) Script de subida
#   copie deploy/subir_ms_omr.sh -> ~/subir_ms_omr.sh
chmod +x ~/subir_ms_omr.sh
```
Depois disso, cada merge de PR pra `develop` no ms-omr roda o deploy sozinho (PUSH → DEPLOY_HOMOL).

Em **prod** o mesmo passo a passo vale, usando `subir_ms_omr.prod.sh` como `~/subir_ms_omr.sh`;
o deploy dispara no push de tag (`git tag 1.0.0 && git push origin 1.0.0`).

## Secrets do GitHub

Mesmos nomes usados por api/ms-simulado/form. SSH por **senha** nos dois ambientes.

| Secret | Homol | Prod |
|---|:---:|:---:|
| `DOCKER_USER` / `DOCKER_PASSWORD` | ✅ cadastrado | ✅ (o mesmo) |
| `DEPLOY_HOST_HOMOL` / `DEPLOY_USER_HOMOL` / `DEPLOY_PASS_HOMOL` | ✅ cadastrado | — |
| `DEPLOY_HOST_PROD` / `DEPLOY_USER_PROD` / `DEPLOY_PASS_PROD` | — | ⬜ **falta cadastrar** |

> O `ci-prod.yml` só roda em push de tag; até cadastrar os `*_PROD` não dispara nada.

## Envs a ajustar nos OUTROS projetos (pro fluxo do cartão fechar em homol)

### `~/env/.env.omr` (ms-omr — novo)
Ver `.env.omr.example`. Só precisa preencher **AWS_*** (R2, iguais ao api). O resto já vem certo.

### `~/env/.env.ms` (ms-simulado) — **adicionar**
Confirmado no servidor: hoje só tem `NODE_ENV/MS_PORT/MONGODB` → **falta todo o R2** (e o resto).
Pro cartão precisa de:
```
OMR_URL=http://vcnafacul_ms_omr:8000
CARTAO_BUCKET=vcnafacul-cartoes
AWS_ENDPOINT=<igual ao api>
AWS_REGION=<igual ao api>
AWS_ACCESS_KEY_ID=<igual ao api>
AWS_SECRET_ACCESS_KEY=<igual ao api>
REDIS_HOST=vcnafacul_redis
REDIS_PORT=6379
QUEUE_DRIVER=redis            # ativa o ValkeyQueueProducer (fila de respostas do callback)
```

### `~/env/.env` (api) — **ajustar**
Hoje (confirmado): `CACHE_DRIVER=inMemory`, `REDIS_HOST=localhost`, `QUEUE_DRIVER=memory` → o api usa o
**cache local do Nest** e nem enxerga Redis. Pra apontar pro Redis novo:
```
CACHE_DRIVER=redis           # hoje inMemory → passa a usar o Redis (CacheDriver.Redis='redis')
REDIS_HOST=vcnafacul_redis   # hoje localhost (quebrado) — tb necessário pro prime do upload (omr-cache)
REDIS_PORT=6379
QUEUE_DRIVER=redis           # opcional: joga a fila do api no Redis também (hoje memory)
# BUCKET_CARTAO já tem default 'vcnafacul-cartoes' — só adicione se for sobrescrever
```
> Todos (api, ms-simulado, ms-omr) apontando pro mesmo `vcnafacul_redis` (DB 0). O prime do
> `omr:img:*` feito pelo api é lido pelo ms-omr; sem colisão com o cache do Nest (namespace `vcnafacul`).

> Obs.: essas mudanças em ms-simulado/api só têm efeito quando esses serviços forem
> **redeployados** com as imagens novas (que contêm os endpoints do cartão dos PRs #169/#511).

## Topologia resultante (rede `network-vcnafacul`)

```
[nginx :80/:443] → [vcnafacul :5271→3333 (api)]
                        │  A3 → OMR_URL
                        ▼
[vcnafacul_ms_omr :8000] ⇄ [vcnafacul_redis :6379]   (fila arq + cache do template/folha)
        │ callback
        ▼
[vcnafacul_simulado_prod :3000] ⇄ [vcnafacul_redis]  (fila de respostas)
        │
        ▼  R2 (bucket vcnafacul-cartoes)  ← api(upload) / ms-simulado(template) / ms-omr(leitura)
```
