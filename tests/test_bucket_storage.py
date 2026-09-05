import io

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.services import bucket_storage
from app.services.bucket_storage import StorageError, baixar_imagem


class _FakeBody:
    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)

    def read(self) -> bytes:
        return self._buf.read()


def _fake_client(get_object):
    class _C:
        def get_object(self, **kwargs):
            return get_object(**kwargs)

    return _C()


def test_baixar_imagem_sucesso(monkeypatch):
    def get_object(**kwargs):
        assert kwargs["Key"] == "cartoes/abc.jpg"
        return {"Body": _FakeBody(b"IMG-BYTES")}

    monkeypatch.setattr(bucket_storage, "_client", lambda: _fake_client(get_object))
    assert baixar_imagem("cartoes/abc.jpg") == b"IMG-BYTES"


def test_baixar_imagem_key_inexistente_vira_storage_error(monkeypatch):
    def get_object(**kwargs):
        raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")

    monkeypatch.setattr(bucket_storage, "_client", lambda: _fake_client(get_object))
    with pytest.raises(StorageError, match="não encontrada"):
        baixar_imagem("cartoes/faltando.jpg")


def test_baixar_imagem_falha_conexao_vira_storage_error(monkeypatch):
    def get_object(**kwargs):
        raise EndpointConnectionError(endpoint_url="http://localhost:9000")

    monkeypatch.setattr(bucket_storage, "_client", lambda: _fake_client(get_object))
    with pytest.raises(StorageError, match="conexão"):
        baixar_imagem("cartoes/x.jpg")
