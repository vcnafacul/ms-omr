# Fixture: cartão sem markers (cortado)

Passo manual (o teste `test_cartao_sem_markers.py` PULA até a foto existir):

1. Pegue um cartão preenchido e fotografe com **um dos 4 markers fora do quadro / cortado**.
2. Salve como `foto.jpeg` neste diretório.
3. `uv run pytest tests/test_cartao_sem_markers.py -m integration` — `run_omr` deve levantar OmrEngineError.
