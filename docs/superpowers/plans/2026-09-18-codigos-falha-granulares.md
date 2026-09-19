# Códigos de falha granulares no ms-omr — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separar o código de falha `cartao_ilegivel` nas quatro causas reais que ele hoje engole, e fazer o timeout do motor e a falha de storage voltarem a ser re-tentáveis de fato — sem nunca deixar o histórico sem callback.

**Architecture:** Um `StrEnum` central (`app/codigos.py`) é a fonte única dos sete códigos. O `omr_engine.py` passa a carregar o código na própria exceção (`OmrEngineError.codigo`) e tira o timeout da hierarquia (`OmrTimeout`, classe irmã). O `omr_pipeline.py` continua sendo o único lugar que decide o que é falha de negócio (vira callback) e o que é transitório (vira `arq.Retry`) — e, na última tentativa permitida, converte o transitório em callback definitivo, porque o arq descarta o job sem executá-lo quando `job_try > max_tries`.

**Tech Stack:** Python 3.11, FastAPI, arq (Redis), pytest (`asyncio_mode = "auto"`), ruff, black. Gerenciador: `uv`.

**Spec:** `docs/superpowers/specs/2026-09-18-codigos-falha-granulares-design.md`

**Branch:** `feature/01b-codigos-falha-granulares` (já criada, spec já commitado)

---

## Estrutura de arquivos

| arquivo | responsabilidade | ação |
|---|---|---|
| `app/codigos.py` | Fonte única dos sete códigos de falha do contrato com o ms-simulado | **criar** |
| `app/services/omr_engine.py` | Único módulo que conhece o OMRChecker. Passa a classificar as quatro causas | modificar |
| `app/services/omr_pipeline.py` | Decide negócio × transitório; produz callback ou `Retry` | modificar |
| `app/services/template_source.py` | Troca o literal `"template_ausente"` pelo enum | modificar |
| `app/config.py` | Ganha `omr_max_tries`, a definição única do teto de tentativas | modificar |
| `app/worker.py` | Passa a ler `max_tries` do `Settings` em vez do literal `3` | modificar |
| `tests/test_codigos.py` | Protege o contrato de serialização dos códigos | **criar** |
| `tests/test_omr_engine.py` | Um teste por causa de falha do motor | modificar |
| `tests/test_omr_pipeline.py` | Um teste por código no callback + os dois caminhos do transitório | modificar |
| `README.md` | Seção do catálogo — é o que o ms-simulado referencia | modificar |

`app/services/callback.py` e `app/services/bucket_storage.py` **não mudam**. O enum é subclasse de
`str`, então serializa sozinho no payload; e manter `bucket_storage.py` sem conhecer `CodigoFalha`
é o que impede `StorageNotFound` de herdar semântica de transitório.

---

## Task 1: Catálogo de códigos

**Files:**
- Create: `app/codigos.py`
- Test: `tests/test_codigos.py`

- [ ] **Step 1: Write the failing test**

Criar `tests/test_codigos.py`:

```python
import json

from app.codigos import CodigoFalha

_ESPERADOS = {
    "imagem_nao_encontrada",
    "template_ausente",
    "cartao_nao_detectado",
    "leitura_ausente",
    "motor_falhou",
    "motor_timeout",
    "armazenamento_indisponivel",
}


def test_catalogo_tem_exatamente_os_sete_codigos_do_contrato():
    assert {c.value for c in CodigoFalha} == _ESPERADOS


def test_codigo_e_str_e_compara_com_a_string_crua():
    # o ms-simulado recebe a string, não o enum
    assert CodigoFalha.MOTOR_TIMEOUT == "motor_timeout"
    assert isinstance(CodigoFalha.MOTOR_TIMEOUT, str)


def test_codigo_serializa_como_string_no_payload_do_callback():
    # callback.py faz client.post(json=payload) → json.dumps por baixo
    payload = {"falha": {"motivo": CodigoFalha.CARTAO_NAO_DETECTADO}}
    assert json.dumps(payload) == '{"falha": {"motivo": "cartao_nao_detectado"}}'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_codigos.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.codigos'`

- [ ] **Step 3: Write minimal implementation**

Criar `app/codigos.py`:

```python
from enum import StrEnum


class CodigoFalha(StrEnum):
    """Contrato de códigos de falha entre o ms-omr e o ms-simulado.

    Fonte única. A tabela publicada no README.md é derivada daqui — ao mexer aqui,
    atualize lá, porque é o README que o ms-simulado referencia.
    """

    # Falhas de negócio: determinísticas, viram callback `falha` na hora.
    IMAGEM_NAO_ENCONTRADA = "imagem_nao_encontrada"
    TEMPLATE_AUSENTE = "template_ausente"
    CARTAO_NAO_DETECTADO = "cartao_nao_detectado"
    LEITURA_AUSENTE = "leitura_ausente"
    MOTOR_FALHOU = "motor_falhou"

    # Transitórios: re-tentados pelo arq; só viram callback quando as tentativas se esgotam.
    MOTOR_TIMEOUT = "motor_timeout"
    ARMAZENAMENTO_INDISPONIVEL = "armazenamento_indisponivel"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_codigos.py -v`
Expected: PASS — 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/codigos.py tests/test_codigos.py
git commit -m "feat: catálogo único dos códigos de falha do ms-omr"
```

---

## Task 2: O motor distingue as quatro causas

**Files:**
- Modify: `app/services/omr_engine.py:20-22` (classe `OmrEngineError`), `:73-79` (timeout e exit code), `:110-117` (`_parse_results`)
- Test: `tests/test_omr_engine.py`

Hoje as quatro causas são a mesma classe com mensagens diferentes. Depois desta task,
`OmrEngineError` carrega `codigo` e `detalhe` separados, e o timeout vira `OmrTimeout` — uma classe
que **não** herda de `OmrEngineError`, porque é justamente isso que impede o pipeline de capturá-lo
junto com as falhas de negócio.

- [ ] **Step 1: Write the failing test**

Adicionar ao final de `tests/test_omr_engine.py` (e acrescentar os imports no topo):

```python
import subprocess
from types import SimpleNamespace

from app.codigos import CodigoFalha
from app.services.omr_engine import OmrTimeout
```

```python
def _template_dir(tmp_path: Path) -> Path:
    # run_omr faz copytree(template_dir, input_dir) — basta o diretório existir
    d = tmp_path / "tpl"
    d.mkdir()
    return d


def _proc(returncode: int, stderr: str = ""):
    return SimpleNamespace(returncode=returncode, stderr=stderr, stdout="")


def test_timeout_do_motor_vira_omr_timeout(tmp_path: Path, monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="omrchecker", timeout=120)

    monkeypatch.setattr(subprocess, "run", boom)

    with pytest.raises(OmrTimeout) as ei:
        run_omr(b"img", _template_dir(tmp_path))
    # é irmã, não filha — o pipeline precisa poder tratá-las separado
    assert not isinstance(ei.value, OmrEngineError)


def test_motor_abortado_vira_motor_falhou_com_stderr_no_detalhe(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(11, "traceback do motor"))

    with pytest.raises(OmrEngineError) as ei:
        run_omr(b"img", _template_dir(tmp_path))
    assert ei.value.codigo == CodigoFalha.MOTOR_FALHOU
    assert "traceback do motor" in ei.value.detalhe


def test_sem_csv_de_results_vira_cartao_nao_detectado(tmp_path: Path, monkeypatch):
    # rodou até o fim (exit 0) e não produziu Results → não achou o cartão na foto
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(0))

    with pytest.raises(OmrEngineError) as ei:
        run_omr(b"img", _template_dir(tmp_path))
    assert ei.value.codigo == CodigoFalha.CARTAO_NAO_DETECTADO


def test_imagem_fora_do_csv_vira_leitura_ausente(tmp_path: Path, monkeypatch):
    def run_criando_csv_de_outra_imagem(cmd, **kwargs):
        output_dir = Path(cmd[cmd.index("-o") + 1])
        results = output_dir / "Results"
        results.mkdir(parents=True)
        (results / "r.csv").write_text("file_id,q1\noutra_imagem.png,A\n")
        return _proc(0)

    monkeypatch.setattr(subprocess, "run", run_criando_csv_de_outra_imagem)

    with pytest.raises(OmrEngineError) as ei:
        run_omr(b"img", _template_dir(tmp_path))
    assert ei.value.codigo == CodigoFalha.LEITURA_AUSENTE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_omr_engine.py -v -m "not integration"`
Expected: FAIL — `ImportError: cannot import name 'OmrTimeout' from 'app.services.omr_engine'`

- [ ] **Step 3: Write minimal implementation**

Em `app/services/omr_engine.py`, acrescentar o import no topo (depois de `from pydantic import BaseModel`):

```python
from app.codigos import CodigoFalha
```

Substituir a classe `OmrEngineError` (linhas 20-22) por:

```python
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
```

Substituir os dois `raise` das linhas 73-79 por:

```python
        except subprocess.TimeoutExpired as exc:
            raise OmrTimeout(f"OMRChecker excedeu {_TIMEOUT_SECONDS}s") from exc

        if proc.returncode != 0:
            raise OmrEngineError(
                CodigoFalha.MOTOR_FALHOU,
                f"OMRChecker saiu com código {proc.returncode}: {proc.stderr[-2000:]}",
            )
```

Substituir os dois `raise` de `_parse_results` (linhas 112-117) por:

```python
    if not csvs:
        raise OmrEngineError(
            CodigoFalha.CARTAO_NAO_DETECTADO, "OMRChecker não gerou CSV de Results"
        )

    row = _find_row(csvs, image_name)
    if row is None:
        raise OmrEngineError(
            CodigoFalha.LEITURA_AUSENTE, f"leitura de '{image_name}' ausente no CSV de Results"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_omr_engine.py -v -m "not integration"`
Expected: PASS — 5 passed (os 4 novos + `test_run_omr_raises_on_invalid_template`, que continua
verde porque o OMRChecker sai com código ≠ 0 e a classe `OmrEngineError` segue existindo)

- [ ] **Step 5: Verificar que o pipeline quebrou, e que quebrou pelo motivo certo**

Run: `uv run pytest tests/test_omr_pipeline.py -v`
Expected: FAIL em `test_ilegivel_callback_falha_sem_reraise` — `OmrEngineError.__init__()`
agora exige dois argumentos. É o esperado: a Task 3 conserta o pipeline.

- [ ] **Step 6: Commit**

```bash
git add app/services/omr_engine.py tests/test_omr_engine.py
git commit -m "feat: um código por causa de falha no motor OMR"
```

---

## Task 3: O pipeline repassa o código em vez de achatar tudo

**Files:**
- Modify: `app/services/omr_pipeline.py:25-28`
- Test: `tests/test_omr_pipeline.py`

- [ ] **Step 1: Write the failing test**

Em `tests/test_omr_pipeline.py`, acrescentar o import no topo:

```python
from app.codigos import CodigoFalha
```

**Substituir** o teste `test_ilegivel_callback_falha_sem_reraise` (que afirma o código
`cartao_ilegivel`, que deixa de existir) por estes três:

```python
@pytest.mark.parametrize(
    "codigo",
    [
        CodigoFalha.CARTAO_NAO_DETECTADO,
        CodigoFalha.LEITURA_AUSENTE,
        CodigoFalha.MOTOR_FALHOU,
    ],
)
async def test_falha_do_motor_vira_callback_com_o_codigo_e_o_detalhe(monkeypatch, codigo):
    def boom(k, i, t):
        raise OmrEngineError(codigo, "detalhe cru do motor")

    calls = _patch(monkeypatch, ler_cartao=boom)
    await pipe.process_cartao(None, "cartoes/665/a")  # não re-raise

    assert calls["falha"] == [("cartoes/665/a", codigo, "detalhe cru do motor")]
    assert calls["ok"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_omr_pipeline.py -v`
Expected: FAIL — os três casos recebem `cartao_ilegivel` no lugar do código esperado

- [ ] **Step 3: Write minimal implementation**

Em `app/services/omr_pipeline.py`, substituir as linhas 25-28 por:

```python
        try:
            leitura = ler_cartao(image_key, image, tpl_dir)
        except OmrEngineError as exc:
            raise FalhaNegocio(exc.codigo, exc.detalhe) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_omr_pipeline.py -v`
Expected: PASS nos três casos novos. `test_transitorio_reraise` continua verde (a Task 5 muda ele).

- [ ] **Step 5: Commit**

```bash
git add app/services/omr_pipeline.py tests/test_omr_pipeline.py
git commit -m "feat: pipeline repassa o código do motor em vez de achatar em cartao_ilegivel"
```

---

## Task 4: `max_tries` com uma definição só

**Files:**
- Modify: `app/config.py` (bloco "Worker in-process"), `app/worker.py:9-10`
- Test: `tests/test_config.py`

O teto de tentativas precisa ser legível pelo `omr_pipeline.py`, e o `ctx` do arq **não** o
carrega (`arq/worker.py:576` monta o `job_ctx` só com `job_id`, `job_try`, `enqueue_time`,
`score`). Como o `worker.py` importa o pipeline, o pipeline não pode importar o `worker.py` de
volta — então o valor desce para o `Settings`, que os dois já conhecem.

- [ ] **Step 1: Write the failing test**

Acrescentar a `tests/test_config.py` (o import de `Settings` já existe no topo):

```python
def test_teto_de_tentativas_tem_default_3():
    # pelo model_fields, e não por Settings().omr_max_tries, para não depender do .env da máquina
    assert Settings.model_fields["omr_max_tries"].default == 3


def test_worker_e_pipeline_leem_o_mesmo_teto_de_tentativas():
    from app.config import get_settings
    from app.worker import WorkerSettings

    assert WorkerSettings.max_tries == get_settings().omr_max_tries
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'omr_max_tries'`

- [ ] **Step 3: Write minimal implementation**

Em `app/config.py`, no bloco `# Worker in-process (Opção A)`, acrescentar depois de
`omr_inprocess_worker`:

```python
    # Teto de tentativas do arq. Lido pelo worker E pelo pipeline (que decide, na última
    # tentativa, converter o transitório em callback definitivo). Uma definição só.
    omr_max_tries: int = 3
```

Em `app/worker.py`, substituir a linha 10:

```python
    max_tries = get_settings().omr_max_tries
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/worker.py tests/test_config.py
git commit -m "refactor: max_tries vira omr_max_tries no Settings, lido pelo worker e pelo pipeline"
```

---

## Task 5: Transitórios voltam a ser re-tentados, e nunca morrem calados

**Files:**
- Modify: `app/services/omr_pipeline.py:1-11` (imports), `:35-44` (`process_cartao`)
- Test: `tests/test_omr_pipeline.py`

O arq só re-enfileira em três casos — `Retry`, `asyncio.CancelledError` e `RetryJob`
(`arq/worker.py:610-634`). Exceção comum cai no `else`: job morto, sem re-tentativa e sem
callback. Por isso o transitório precisa virar `Retry` explícito. E como o arq descarta o job
**antes** de executá-lo quando `job_try > max_tries` (`arq/worker.py:550`), a última tentativa que
ainda roda é a única chance de avisar o ms-simulado — senão o histórico fica em `awaiting_omr`
para sempre.

- [ ] **Step 1: Write the failing test**

Em `tests/test_omr_pipeline.py`, acrescentar os imports no topo:

```python
from arq import Retry

from app.services.bucket_storage import StorageError
from app.services.omr_engine import OmrTimeout
```

Acrescentar ao final de `_patch`, **antes** do `return calls`, para tornar o teto determinístico
independentemente do `.env` da máquina:

```python
    monkeypatch.setattr(pipe, "get_settings", lambda: SimpleNamespace(omr_max_tries=3))
```

**Substituir** `test_transitorio_reraise` (que documenta o comportamento defeituoso: hoje o
`StorageError` propaga cru e o arq não re-tenta) por estes quatro testes:

```python
_TRANSITORIOS = [
    (OmrTimeout("OMRChecker excedeu 120s"), CodigoFalha.MOTOR_TIMEOUT),
    (StorageError("falha de conexão ao storage"), CodigoFalha.ARMAZENAMENTO_INDISPONIVEL),
]


def _patch_transitorio(monkeypatch, exc):
    """Injeta cada transitório no ponto real de onde ele vem: o timeout no motor,
    o StorageError no acesso ao bucket. Injetar os dois no mesmo ponto testaria
    um fluxo que não existe."""

    def boom(*a, **k):
        raise exc

    if isinstance(exc, OmrTimeout):
        return _patch(monkeypatch, ler_cartao=boom)
    return _patch(monkeypatch, obter_imagem=boom)


@pytest.mark.parametrize("exc, codigo", _TRANSITORIOS)
async def test_transitorio_com_tentativa_sobrando_pede_retry(monkeypatch, exc, codigo):
    calls = _patch_transitorio(monkeypatch, exc)

    with pytest.raises(Retry):
        await pipe.process_cartao({"job_try": 1}, "cartoes/665/a")
    assert calls["falha"] == []  # ainda vai tentar de novo — não avisa ninguém ainda


@pytest.mark.parametrize("exc, codigo", _TRANSITORIOS)
async def test_transitorio_na_ultima_tentativa_vira_callback_definitivo(monkeypatch, exc, codigo):
    calls = _patch_transitorio(monkeypatch, exc)

    # job_try == omr_max_tries: o arq descarta o job na próxima, então é aqui ou nunca
    await pipe.process_cartao({"job_try": 3}, "cartoes/665/a")

    assert calls["falha"] == [("cartoes/665/a", codigo, str(exc))]
```

⚠️ `_TRANSITORIOS` é avaliado uma vez, no import, então as duas instâncias de exceção são
reusadas entre os testes. É seguro aqui porque nada as muta — mas não acrescente estado a elas.

E este, que prova que `StorageNotFound` não é arrastado pelo caminho transitório (ele é subclasse
de `StorageError`, e só não vaza porque é convertido antes):

```python
async def test_storage_not_found_continua_sendo_falha_de_negocio(monkeypatch):
    def boom(k):
        raise StorageNotFound("imagem não encontrada: cartoes/665/a")

    calls = _patch(monkeypatch, obter_imagem=boom)
    await pipe.process_cartao({"job_try": 1}, "cartoes/665/a")  # sem Retry

    assert calls["falha"][0][1] == CodigoFalha.IMAGEM_NAO_ENCONTRADA
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_omr_pipeline.py -v`
Expected: FAIL — `test_transitorio_com_tentativa_sobrando_pede_retry` levanta `OmrTimeout`/
`StorageError` em vez de `Retry`, e `test_transitorio_na_ultima_tentativa...` propaga a exceção
em vez de mandar o callback

- [ ] **Step 3: Write minimal implementation**

Em `app/services/omr_pipeline.py`, substituir o bloco de imports (linhas 1-11) por:

```python
import asyncio
import shutil

from arq import Retry

from app.codigos import CodigoFalha
from app.config import get_settings
from app.errors import FalhaNegocio
from app.services import callback
from app.services.bucket_storage import StorageError, StorageNotFound
from app.services.cartao_reader import ler_cartao
from app.services.image_source import obter_imagem
from app.services.imagekey import parse_simulado_id
from app.services.omr_engine import OmrEngineError, OmrTimeout
from app.services.template_source import obter_template

# Espera entre tentativas de um transitório: job_try × isto. Backoff linear (30s, 60s).
_BACKOFF_SEGUNDOS = 30
```

Substituir `process_cartao` (linhas 35-44) por:

```python
async def process_cartao(ctx, image_key: str) -> None:
    """Task do worker arq (roda in-process). O OMR bloqueante vai pra um thread
    (run_in_executor) → concorrência real até OMR_MAX_WORKERS sem travar a API.

    Falha de negócio → callback `falha`, sem re-raise.
    Transitório → `Retry` explícito: o arq NÃO re-tenta exceção comum, só Retry,
    CancelledError e RetryJob (arq/worker.py:610-634). Na última tentativa permitida
    vira callback definitivo, porque o arq descarta o job sem executá-lo quando
    job_try > max_tries (arq/worker.py:550) — seria a última chance de avisar.
    """
    loop = asyncio.get_running_loop()
    try:
        respostas = await loop.run_in_executor(None, _ler_respostas, image_key)
        await callback.enviar_resultado_ok(image_key, respostas)
    except FalhaNegocio as fn:
        await callback.enviar_resultado_falha(image_key, fn.motivo, fn.detalhe)
    except (OmrTimeout, StorageError) as exc:
        # Lista explícita, e não uma classe-base marcadora: StorageNotFound herda de
        # StorageError e é falha de NEGÓCIO (convertida acima). Marcar por herança o
        # tornaria transitório sem ninguém perceber.
        codigo = (
            CodigoFalha.MOTOR_TIMEOUT
            if isinstance(exc, OmrTimeout)
            else CodigoFalha.ARMAZENAMENTO_INDISPONIVEL
        )
        tentativa = (ctx or {}).get("job_try", 1)
        if tentativa >= get_settings().omr_max_tries:
            await callback.enviar_resultado_falha(image_key, codigo, str(exc))
            return
        raise Retry(defer=tentativa * _BACKOFF_SEGUNDOS) from exc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_omr_pipeline.py -v`
Expected: PASS — todos, incluindo os 5 casos novos

- [ ] **Step 5: Commit**

```bash
git add app/services/omr_pipeline.py tests/test_omr_pipeline.py
git commit -m "fix: transitório vira arq.Retry e nunca morre sem callback

O arq só re-enfileira Retry/CancelledError/RetryJob — exceção comum mata o job
em silêncio, deixando o histórico em awaiting_omr para sempre. Vale para o
timeout do motor e para o StorageError."
```

---

## Task 6: Os dois códigos antigos passam a vir do enum

**Files:**
- Modify: `app/services/omr_pipeline.py:23`, `app/services/template_source.py:20`
- Test: `tests/test_omr_pipeline.py`, `tests/test_template_source.py`

Sobraram dois literais soltos. Enquanto existirem, o enum não é fonte única — e um erro de
digitação num deles vira um código que nenhum mapa conhece.

- [ ] **Step 1: Write the failing test**

Em `tests/test_omr_pipeline.py`, **substituir** a asserção de
`test_imagem_ausente_callback_falha` para comparar com o enum:

```python
async def test_imagem_ausente_callback_falha(monkeypatch):
    def boom(k):
        raise StorageNotFound("imagem não encontrada")

    calls = _patch(monkeypatch, obter_imagem=boom)
    await pipe.process_cartao(None, "cartoes/665/a")
    assert calls["falha"][0][1] == CodigoFalha.IMAGEM_NAO_ENCONTRADA
```

Em `tests/test_template_source.py` já existe `test_template_ausente_vira_falha_negocio`. Não crie
outro: acrescente `from app.codigos import CodigoFalha` no topo e troque a última linha dele de

```python
    assert ei.value.motivo == "template_ausente"
```

para

```python
    assert ei.value.motivo == CodigoFalha.TEMPLATE_AUSENTE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_omr_pipeline.py tests/test_template_source.py -v`
Expected: PASS nos dois — porque `CodigoFalha.X == "x"` é verdadeiro por ser `StrEnum`. Os testes
**travam o contrato** para que a troca do Step 3 seja provadamente segura; eles não falham antes.
Isto é deliberado: a mudança é de procedência do valor, não de comportamento.

- [ ] **Step 3: Write the implementation**

Em `app/services/omr_pipeline.py`, linha 23:

```python
            raise FalhaNegocio(CodigoFalha.IMAGEM_NAO_ENCONTRADA, str(exc)) from exc
```

Em `app/services/template_source.py`, acrescentar o import no topo:

```python
from app.codigos import CodigoFalha
```

e substituir a linha 20:

```python
        raise FalhaNegocio(CodigoFalha.TEMPLATE_AUSENTE, str(exc)) from exc
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -m "not integration" -v`
Expected: PASS — suíte inteira verde

- [ ] **Step 5: Commit**

```bash
git add app/services/omr_pipeline.py app/services/template_source.py \
        tests/test_omr_pipeline.py tests/test_template_source.py
git commit -m "refactor: imagem_nao_encontrada e template_ausente saem do enum"
```

---

## Task 7: Publicar o contrato no README

**Files:**
- Modify: `README.md`

É o critério de aceite "os códigos estão documentados num lugar só, e o ms-simulado referencia
essa lista". O ms-simulado é TypeScript e não importa o enum — o README é a superfície publicada.

- [ ] **Step 1: Escrever a seção**

Acrescentar ao `README.md`, depois da seção "OMRChecker (engine de leitura)":

````markdown
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

**Negócio** é determinístico: vira callback na hora, re-tentar daria o mesmo resultado.

**Transitório esgotado** é o oposto — a falha é intermitente, o job foi re-tentado até
`OMR_MAX_TRIES` (default 3, backoff linear de 30s) e só então o callback foi enviado. Ou seja:
**quando um desses códigos chega, não haverá mais nenhuma tentativa automática.** Uma mensagem do
tipo "tentaremos de novo" seria falsa aqui.

⚠️ Um código desconhecido pelo consumidor não pode virar tela em branco: o ms-simulado precisa de
um caso padrão que mostre algo útil e registre o código não mapeado no log.
````

- [ ] **Step 2: Rodar lint, formatação e a suíte inteira**

```bash
uv run ruff check .
uv run black --check .
uv run pytest -m "not integration" -v
```

Expected: ruff sem achados, black sem reformatação pendente, suíte verde.

- [ ] **Step 3: Rodar o teste de integração, que exercita o OMRChecker de verdade**

Run: `uv run pytest -m integration -v`
Expected: PASS — confirma que o caminho feliz não regrediu com a troca das exceções

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: publica o catálogo de códigos de falha no README"
```

---

## Verificação final

- [ ] `uv run pytest -v` — suíte inteira, incluindo integração
- [ ] `uv run ruff check . && uv run black --check .`
- [ ] `grep -rn "cartao_ilegivel" app/ tests/ README.md` não devolve nada
- [ ] `grep -rn '"imagem_nao_encontrada"\|"template_ausente"' app/` só devolve `app/codigos.py`

## Depois do merge — o que o card 01 herda

⚠️ A tabela do card `01` traz `motor_timeout` como *"A leitura demorou mais que o esperado.
Tentaremos de novo automaticamente."* com `acaoSugerida: aguardar`. **Essa linha fica errada:** o
callback só chega depois de esgotadas as tentativas. Texto e ação precisam refletir falha
definitiva.

⚠️ O card `01` precisa acomodar o sétimo código, `armazenamento_indisponivel`, que não estava na
tabela original.

⚠️ Continua em aberto (card próprio, já previsto no `09`): a varredura de `awaiting_omr` órfãos.
Este plano fecha os caminhos de timeout e storage, mas o processo ainda pode morrer entre o
`createAwaitingOmr` e o callback.
