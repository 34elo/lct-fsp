from fsp_platform.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "fsp-mock"
    fsp_mock_api_key: str = "dev-mock-key"  # X-Api-Key; настоящий — в .env
    fsp_webhook_url: str | None = None  # куда слать result.published; None — не слать
    fsp_webhook_secret: str = "dev-webhook-secret"
    code_ttl_seconds: int = 600
    code_max_attempts: int = 5
