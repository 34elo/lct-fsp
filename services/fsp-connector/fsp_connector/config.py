from typing import Literal

from fsp_platform.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "fsp-connector"
    database_url: str = "postgresql+asyncpg://fspc:fspc@localhost:5432/fsp_connector"
    # fsp.md §2: выбор адаптера; organizers/real появятся в E5-8
    fsp_adapter: Literal["mock", "organizers", "real"] = "mock"
    fsp_base_url: str = "http://fsp-mock:8200"
    fsp_api_key: str = "dev-mock-key"  # X-Api-Key; настоящий — в .env
    fsp_public_url: str | None = None  # адрес для браузера (страница OAuth); None — fsp_base_url
    fsp_oauth_client_id: str = "fsp-career"
    fsp_oauth_redirect_uri: str = "http://localhost:28080/api/v1/auth/fsp/callback"
    fsp_webhook_secret: str = "dev-webhook-secret"
    # ретраи и circuit breaker (fsp.md §2)
    fsp_timeout_seconds: float = 10.0
    fsp_retries: int = 3
    fsp_retry_base_seconds: float = 0.2
    fsp_breaker_failures: int = 5
    fsp_breaker_open_seconds: float = 30.0
    # кеш ответов (messaging.md §6)
    fsp_cache_ttl_seconds: int = 600
    # сервисный токен core-api для /internal/* (security.md §1); пустой = закрыто
    service_token_core: str = ""
    # привязка по коду (fsp.md §4)
    fsp_code_ttl_seconds: int = 600
    fsp_code_max_attempts: int = 5
    # демо-кнопки для ФСП (E13-3): создание результатов и сброс
    demo_mode: bool = False
