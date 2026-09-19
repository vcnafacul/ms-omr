# Códigos de falha granulares no ms-omr

> Card de origem: `vcnafacul-3/docs/cards/relatorio-simulado-cursinho/01b-BACK-omr-codigos-de-erro-granulares.md`
> Repo: `vcnafacul/ms-omr` · Branch: `feature/01b-codigos-falha-granulares`

---

## O problema

O ms-omr emite três códigos de falha, e um deles — `cartao_ilegivel` — cobre quatro causas com
ações opostas: um timeout do motor, um aborto do OMRChecker, um cartão não localizado na foto e uma
imagem ausente do CSV de resultados. As quatro nascem da mesma `OmrEngineError` e só se distinguem
pelo texto da mensagem.

Enquanto for um código só, o mapa código → descrição do card `01` não tem o que mapear: ele diria
"tire outra foto" também para o timeout, mandando o cursinho refazer trabalho à toa.

## A premissa do card que não se confirmou

O card `01b` parte de que "o `arq` já re-tenta o que propaga como transitório", e o docstring do
`omr_pipeline.py` afirma o mesmo. **É falso.**

Em `arq/worker.py:610-634`, o bloco que trata exceção do job só re-enfileira em três casos:
`Retry`, `asyncio.CancelledError` e `RetryJob`. Qualquer outra exceção cai no `else`, que faz
`finish = True` e `jobs_failed += 1` — job morto, sem re-tentativa e sem callback.

Duas consequências:

1. Tirar o timeout de `FalhaNegocio` e deixá-lo propagar **não** o torna re-tentável. Só
   pioraria: hoje ele ao menos vira `failed`; propagando, o histórico ficaria em `awaiting_omr`
   para sempre. Re-tentar exige `raise Retry(defer=...)`, explícito.
2. O `StorageError` **já sofre desse defeito hoje**. Ele propaga, o job morre calado, e o
   histórico fica em limbo. O teste `test_transitorio_reraise` documenta esse comportamento como
   se fosse o correto.

## Decisões tomadas

| ponto | decisão |
|---|---|
| Escopo da sessão | Só o `01b`. O `01` (persistir o motivo no ms-simulado) fica para depois |
| Como o motor distingue as causas | `OmrEngineError` ganha um campo `codigo`; o timeout vira classe própria, fora da hierarquia |
| Tentativas esgotadas | A última tentativa manda callback de falha definitiva, em vez de deixar o histórico em limbo |
| `StorageError` | Entra no card, com o mesmo tratamento do timeout |

---

## Desenho

### 1. Catálogo de códigos — `app/codigos.py`

Um `StrEnum` (Python 3.11, versão do repo) como fonte única:

| código | causa | classe |
|---|---|---|
| `imagem_nao_encontrada` | objeto ausente no bucket | negócio |
| `template_ausente` | template do simulado não publicado | negócio |
| `cartao_nao_detectado` | OMRChecker rodou e não gerou CSV de Results | negócio |
| `leitura_ausente` | CSV existe, mas sem a linha desta imagem | negócio |
| `motor_falhou` | OMRChecker saiu com código ≠ 0 | negócio |
| `motor_timeout` | OMRChecker excedeu o tempo, e as tentativas se esgotaram | transitório esgotado |
| `armazenamento_indisponivel` | falha de conexão/credencial no storage, tentativas esgotadas | transitório esgotado |

Por ser subclasse de `str`, o enum serializa sozinho no payload do callback — `callback.py` não muda.

O `ms-simulado` não importa Python, então o contrato publicado é uma seção nova no `README.md`
do ms-omr com essa tabela. O enum é a fonte; o README é o que o outro repo referencia.

### 2. O motor — `app/services/omr_engine.py`

```python
class OmrEngineError(Exception):
    """Falha determinística do OMRChecker — vira callback `falha`, NÃO re-tenta."""
    def __init__(self, codigo: CodigoFalha, detalhe: str) -> None:
        super().__init__(f"{codigo}: {detalhe}")
        self.codigo = codigo
        self.detalhe = detalhe


class OmrTimeout(Exception):
    """OMRChecker excedeu o tempo. Transitório, re-tentável.
    NÃO herda de OmrEngineError — é o que impede o pipeline de capturá-lo junto."""
```

Os quatro pontos de `raise`:

| hoje | passa a ser |
|---|---|
| `OmrEngineError(f"OMRChecker excedeu {N}s")` | `OmrTimeout(f"OMRChecker excedeu {N}s")` |
| `OmrEngineError(f"OMRChecker saiu com código {rc}: {stderr}")` | `OmrEngineError(MOTOR_FALHOU, ...)` |
| `OmrEngineError("OMRChecker não gerou CSV de Results")` | `OmrEngineError(CARTAO_NAO_DETECTADO, ...)` |
| `OmrEngineError(f"leitura de '{img}' ausente no CSV…")` | `OmrEngineError(LEITURA_AUSENTE, ...)` |

O `detalhe` é a mensagem que já existe hoje, preservada inteira — inclusive o `stderr[-2000:]` do
`motor_falhou`, que é o que salva a investigação de um caso novo.

### 3. O pipeline — `app/services/omr_pipeline.py`

`_ler_respostas` deixa de achatar as causas num código só:

```python
except OmrEngineError as exc:
    raise FalhaNegocio(exc.codigo, exc.detalhe) from exc
```

`OmrTimeout` e `StorageError` não são capturados ali. Atravessam o `run_in_executor` (o `finally`
que remove o diretório do template continua rodando) e chegam em `process_cartao`:

```python
except FalhaNegocio as fn:
    await callback.enviar_resultado_falha(image_key, fn.motivo, fn.detalhe)
except (OmrTimeout, StorageError) as exc:
    codigo = (CodigoFalha.MOTOR_TIMEOUT if isinstance(exc, OmrTimeout)
              else CodigoFalha.ARMAZENAMENTO_INDISPONIVEL)
    tentativa = (ctx or {}).get("job_try", 1)
    if tentativa >= get_settings().omr_max_tries:
        await callback.enviar_resultado_falha(image_key, codigo, str(exc))
        return
    raise Retry(defer=tentativa * _BACKOFF_SEGUNDOS)
```

**Por que um par explícito de tipos e não uma classe-base `FalhaTransitoria`.** `StorageNotFound`
herda de `StorageError`; uma classe-base marcadora o tornaria transitório por herança, quando ele é
justamente um caso de negócio (`imagem_nao_encontrada` / `template_ausente`). Funciona hoje só
porque ele é convertido antes de escapar — exatamente o tipo de armadilha por ordenação que este
card existe para eliminar. A lista explícita vive no pipeline, que já é o lugar que decide o que é
negócio e o que é transitório.

**`max_tries` não vem do `ctx`.** O `job_ctx` do arq traz apenas `job_id`, `job_try`,
`enqueue_time` e `score` (`arq/worker.py:576`). Então vira `omr_max_tries` no `Settings`, e o
`worker.py` passa a lê-lo de lá em vez do literal `3` — uma definição só, em vez de duas que
divergem em silêncio.

**Por que a última tentativa manda o callback.** O arq descarta o job **antes** de executá-lo
quando `job_try > max_tries` (`worker.py:550`), então não há execução posterior em que avisar. A
tentativa que ainda roda é a última chance de fechar o ciclo — sem isso, o histórico fica em
`awaiting_omr` indefinidamente, que é o pior dos desfechos para quem coordena o cursinho.

Com `defer = job_try × 30s`, o pior caso até a falha definitiva fica em torno de 7 min
(120 + 30 + 120 + 60 + 120). É mais lento que hoje de propósito: hoje o timeout vira `failed` em
2 min e ninguém tenta de novo.

### 4. Testes

Um por causa, como o critério de aceite pede.

**No motor** (`tests/test_omr_engine.py`), com `subprocess.run` e o diretório de saída forjados:

- `TimeoutExpired` → `OmrTimeout`
- exit ≠ 0 → `OmrEngineError` com `codigo == motor_falhou` e o `stderr` no `detalhe`
- sem CSV de Results → `cartao_nao_detectado`
- CSV presente, sem a linha da imagem → `leitura_ausente`

**No pipeline** (`tests/test_omr_pipeline.py`):

- cada um dos três códigos de negócio chegando ao callback com o `detalhe` junto
- `job_try=1` num timeout → levanta `Retry`, **nenhum** callback
- `job_try == omr_max_tries` num timeout → callback `motor_timeout`, **sem** `Retry`
- o mesmo par para `StorageError` → `armazenamento_indisponivel`
- regressão: `imagem_nao_encontrada` e `template_ausente` continuam vindo como `FalhaNegocio`,
  provando que `StorageNotFound` não é arrastado pelo caminho transitório

O `test_ilegivel_callback_falha_sem_reraise` atual é reescrito: ele afirma um código que deixa de
existir. O `test_transitorio_reraise` também, já que `StorageError` passa a virar `Retry`.

---

## Segurança entre repos

Não há lockstep. O `ms-simulado` hoje faz `if (input.falha) → updateStatus(Failed)` e **descarta o
`motivo`** — nenhuma linha lê aquela string. Códigos novos não têm como quebrá-lo, e o `01b` pode
subir sozinho, antes do `01`.

A única mudança visível em produção antes do `01`: um timeout deixa de virar `failed` em 2 min e
passa a ficar ~7 min em `awaiting_omr` antes de falhar em definitivo.

## O que isto muda no card 01

⚠️ A tabela do card `01` traz `motor_timeout` como *"A leitura demorou mais que o esperado.
Tentaremos de novo automaticamente."* com `acaoSugerida: aguardar`. **Essa linha fica errada com
este desenho:** o callback de `motor_timeout` só é enviado depois de esgotadas as tentativas, então
quando a mensagem chegar não haverá mais nenhuma tentativa automática. O texto e a ação precisam
refletir uma falha definitiva.

⚠️ O card `01` também precisa acomodar o sétimo código, `armazenamento_indisponivel`, que não estava
previsto na tabela original.

## Emenda — o escopo cresceu depois da revisão adversarial

A revisão final subiu um worker arq real contra Redis e provou que o buraco da morte silenciosa
tinha **mais três entradas** além do timeout e do `StorageError`:

1. **O POST do callback.** `callback.py` fazia `raise_for_status()` com o comentário
   *"transitório → arq re-tenta"* — a mesma crença falsa que este spec abre refutando, deixada em
   pé sobre o único código capaz de tirar um `Historico` de `awaiting_omr`. Atinge inclusive o
   caminho de **sucesso**: um cartão lido corretamente tinha o resultado descartado se o
   ms-simulado devolvesse 502 durante um deploy.
2. **O `job_timeout` do próprio arq.** `asyncio.wait_for` levanta `TimeoutError`, que não é
   `CancelledError`, e cai no mesmo `else`. Como o botocore está em 60s de connect + 60s de read
   dentro de um orçamento de 180s, um incidente de storage **lento** caía na morte silenciosa
   enquanto só um **rápido** alcançava o `Retry`.

   ⚠️ **Este não foi corrigido, e não dá para corrigi-lo de dentro do pipeline.** Verifiquei
   experimentalmente: o `TimeoutError` nasce no `asyncio.wait_for` do arq, num frame que não é
   nosso; dentro da coroutine chega um `CancelledError`, que é `BaseException` e não é capturado
   pelo `except Exception` — e suprimi-lo seria pior do que o problema. A mitigação real é manter
   o orçamento interno abaixo dos 180s: dar timeouts explícitos e `max_attempts` ao boto3 em
   `bucket_storage.py`, e conferir a soma contra o `_TIMEOUT_SECONDS` de 120s do subprocess.
   **Card próprio** — é configuração de storage, não contrato de códigos de falha.
3. **Qualquer exceção não classificada** — `OSError` de disco cheio, `ValidationError`,
   o `ValueError` de `parse_simulado_id`.

**Decisão: os três entram**, pelo mesmo raciocínio que trouxe o `StorageError` — e porque sem eles
o critério de aceite *"nunca em job morto sem aviso"* seria falso.

A correção distingue duas fases, porque elas terminam diferente:

- **Leitura falhou** → esgotadas as tentativas, vira callback de falha. É o objetivo.
- **Entrega falhou** (o POST) → esgotadas as tentativas, apenas loga. Inventar um status aqui
  marcaria como falho um cartão que pode ter sido lido com sucesso.

Isso acrescenta um oitavo código, `erro_interno`, para o inesperado.

⚠️ Dois desfechos permanecem sem callback: o POST não entregue nas três tentativas, e o
`job_timeout` do arq (acima). Nos dois o histórico fica em `awaiting_omr` e só a varredura
periódica (card próprio) o resgata.

## Fora de escopo

- Persistir código, descrição e detalhe no `Historico` — é o card `01`.
- A varredura periódica de `awaiting_omr` órfãos. Card próprio, já previsto no `09`.
- Os códigos `imagem_nao_encontrada` e `template_ausente` ficam como estão: já são granulares.
- **`motor_falhou` ainda junta duas causas.** A revisão rodou o OMRChecker real contra bytes
  indecodificáveis e obteve exit 1 com `'NoneType' object has no attribute 'shape'` — `cv2.imread`
  devolvendo `None`, ou seja foto ilegível ("mande outra"), não bug do motor ("fale com o
  suporte"). Agrava que `_image_suffix` nomeia **todo** payload de bytes como `.png`, então
  qualquer formato que o OpenCV não decodifique (HEIC de celular é o candidato óbvio) chega aqui.
  Não é regressão — hoje isso já é um código errado — mas é a mesma classe de defeito que este
  card existe para eliminar. Card próprio: validar decodificabilidade **antes** de invocar o
  motor, em vez de casar o `stderr` por regex.

## Critérios de aceite

- [ ] Cada causa de `OmrEngineError` tem código próprio
- [ ] Timeout deixa de ser `FalhaNegocio` e passa a re-tentar de fato, via `Retry`
- [ ] `StorageError` recebe o mesmo tratamento
- [ ] O POST do callback, o `job_timeout` do arq e o inesperado também (emenda acima)
- [ ] Falha de entrega esgotada loga, e não inventa um status de falha
- [ ] Tentativas esgotadas resultam em callback de falha — nunca em job morto sem aviso
- [ ] `detalhe` continua chegando em todos os casos
- [ ] `max_tries` tem uma definição só, em `Settings`
- [ ] Os sete códigos estão no `README.md`, e o enum é a fonte
- [ ] Um teste por causa, e não um teste genérico de "falhou"
