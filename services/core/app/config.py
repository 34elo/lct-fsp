from fsp_platform.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "core"
    # SSE (api.md §2.8): heartbeat каждые 20 с; шина ui отключается в тестах без брокера
    sse_heartbeat_seconds: float = 20.0
    ui_bus_enabled: bool = True
    # refresh-cookie `rt` (api.md §1); за gateway путь включает префикс /api/v1
    auth_cookie_path: str = "/api/v1/auth"
    # CORS/Origin: SPA (security.md §1, CSRF). Пусто — проверка отключена
    allowed_origins: list[str] = []
    # pseudo_id = HMAC(secret, user_id)[:12] (security.md §3); в проде секрет из PSEUDO_ID_SECRET
    pseudo_id_secret: str = "dev-only-pseudo-secret"
    # сервисные токены internal API (security.md §1); пусто = эндпоинт закрыт
    service_token_ml: str = ""
    service_token_bot: str = ""
    # Telegram (telegram.md §6, security.md §1): токен бота проверяет подпись Login Widget
    tg_bot_token: str = ""
    tg_bot_username: str = ""
    # публичный адрес SPA для magic-ссылок из бота
    web_base_url: str = "http://localhost:5173"
    # data/scoring.yaml (доверие, грейд, матчинг); пусто — файл из корня репозитория
    scoring_config_path: str = ""
