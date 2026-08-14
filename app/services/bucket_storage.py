from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings


class StorageError(Exception):
    """Falha ao acessar o storage (key inexistente, credenciais, conexão)."""


@lru_cache
def _client():
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.aws_endpoint,
        region_name=s.aws_region,
        aws_access_key_id=s.aws_access_key_id,
        aws_secret_access_key=s.aws_secret_access_key,
        config=Config(s3={"addressing_style": "path"}),  # MinIO precisa path-style
    )


def baixar_imagem(key: str) -> bytes:
    """Baixa os bytes do objeto `key` do bucket dos cartões. Levanta StorageError em falha."""
    s = get_settings()
    try:
        resp = _client().get_object(Bucket=s.omr_bucket, Key=key)
        return resp["Body"].read()
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404"):
            raise StorageError(f"imagem não encontrada: {key}") from exc
        raise StorageError(f"erro de storage ({code}) ao ler {key}") from exc
    except BotoCoreError as exc:
        raise StorageError(f"falha de conexão ao storage ao ler {key}") from exc
