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
    # Fallback para falha não classificada — disco cheio, erro de validação, o próprio
    # job_timeout do arq. Também re-tentado; só reportado quando as tentativas se esgotam.
    ERRO_INTERNO = "erro_interno"
