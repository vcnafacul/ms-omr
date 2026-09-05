# Fixture: cartão patológico (dupla-marcação + branco)

Passo manual (o teste `test_cartao_patologico.py` PULA até a foto existir):

1. Imprima o cartão: `yarn cartao:preview` no ms-simulado (layout = DEFAULT_CONFIG calibrado).
2. Preencha normal, MAS: deixe **1 questão com 2 bolhas** e **1 questão em branco**.
3. Anote os números em `expected.json` (`questaoDupla`, `questaoBranco`) e ajuste `n` se ≠ 90.
4. Fotografe plano, com os 4 markers visíveis. Salve como `foto.jpeg` neste diretório.
5. `uv run pytest tests/test_cartao_patologico.py -m integration` deve passar.
