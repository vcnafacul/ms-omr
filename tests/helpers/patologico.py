_ALTERNATIVAS = {"A", "B", "C", "D", "E"}


def assert_patologico(respostas, n: int, dupla: str, branco: str) -> None:
    """Asserta o comportamento do modelo Card 04 num cartão com 1 dupla-marcação e 1 branco:
    ambas as questões omitidas, exatamente n-2 respostas, todas single A–E."""
    nums = {r.questao for r in respostas}
    assert dupla not in nums, f"questão dupla-marcada {dupla} deveria ser omitida"
    assert branco not in nums, f"questão em branco {branco} deveria ser omitida"
    assert len(respostas) == n - 2, f"esperado {n - 2} respostas, veio {len(respostas)}"
    for r in respostas:
        assert (
            r.alternativaEstudante in _ALTERNATIVAS
        ), f"alt inválida em q{r.questao}: {r.alternativaEstudante!r}"
