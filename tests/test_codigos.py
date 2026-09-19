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
    "erro_interno",
}


def test_catalogo_tem_exatamente_os_oito_codigos_do_contrato():
    assert {c.value for c in CodigoFalha} == _ESPERADOS


def test_codigo_e_str_e_compara_com_a_string_crua():
    # o ms-simulado recebe a string, não o enum
    assert CodigoFalha.MOTOR_TIMEOUT == "motor_timeout"
    assert isinstance(CodigoFalha.MOTOR_TIMEOUT, str)


def test_codigo_serializa_como_string_no_payload_do_callback():
    # callback.py faz client.post(json=payload) → json.dumps por baixo
    payload = {"falha": {"motivo": CodigoFalha.CARTAO_NAO_DETECTADO}}
    assert json.dumps(payload) == '{"falha": {"motivo": "cartao_nao_detectado"}}'
