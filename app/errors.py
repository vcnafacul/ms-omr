class FalhaNegocio(Exception):
    """Falha determinística de leitura — vira callback `falha`, NÃO re-tenta."""

    def __init__(self, motivo: str, detalhe: str | None = None) -> None:
        super().__init__(f"{motivo}: {detalhe}" if detalhe else motivo)
        self.motivo = motivo
        self.detalhe = detalhe
