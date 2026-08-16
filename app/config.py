import os
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    omr_port: int = 8000
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    template_dir: str = "templates"

    # S3 / MinIO — placeholders no card 01, usados de fato no card 05
    aws_endpoint: str | None = None
    aws_region: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    # Bucket dos cartões + cache (card 05)
    omr_bucket: str = "vcnafacul-cartoes"
    redis_url: str | None = None
    omr_cache_ttl_seconds: int = 3600

    # Callback do resultado do OMR (card 06)
    callback_url: str = "http://localhost:3333/omr/callback"

    # Worker in-process (Opção A)
    omr_max_workers: int = Field(default_factory=lambda: max(1, (os.cpu_count() or 2) - 1))
    omr_inprocess_worker: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
