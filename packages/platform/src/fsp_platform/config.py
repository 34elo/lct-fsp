"""Базовый конфиг из переменных окружения. Секреты только в .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"  # dev | demo | prod
    service_name: str = "service"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://fsp:fsp@localhost:5432/fsp"
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/fsp"
    jwt_secret: str = "dev-only-change-me"
    ml_fake: bool = False
