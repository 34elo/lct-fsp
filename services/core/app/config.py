from fsp_platform.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "core"
    # SSE: heartbeat каждые 20 с; шина ui отключается в тестах без брокера
    sse_heartbeat_seconds: float = 20.0
    ui_bus_enabled: bool = True
    # refresh-cookie `rt`; за gateway путь включает префикс /api/v1
    auth_cookie_path: str = "/api/v1/auth"
    # CORS/Origin: SPA (CSRF). Пусто — проверка отключена
    allowed_origins: list[str] = []
    # pseudo_id = HMAC(secret, user_id)[:12]; в проде секрет из PSEUDO_ID_SECRET
    pseudo_id_secret: str = "dev-only-pseudo-secret"
    # сервисные токены internal API; пусто = эндпоинт закрыт
    service_token_ml: str = ""
    service_token_bot: str = ""
    # Telegram: токен бота проверяет подпись Login Widget
    tg_bot_token: str = ""
    tg_bot_username: str = ""
    # публичный адрес SPA для magic-ссылок из бота
    web_base_url: str = "http://localhost:5173"
    # data/scoring.yaml (доверие, грейд, матчинг); пусто — файл из корня репозитория
    scoring_config_path: str = ""
    # ml-api: эмбеддинг профиля; пусто — эмбеддинги не считаются
    ml_api_url: str = ""
    embed_model: str = "BAAI/bge-m3"
    embed_dim: int = 1024
    embed_timeout_seconds: float = 10.0
    # разбор текстового запроса через LLM: таймаут, после него — только правила
    query_parse_timeout_seconds: float = 5.0
    # соль псевдонимов аналитики HMAC(id, ANALYTICS_SALT); в проде из .env
    analytics_salt: str = "dev-only-analytics-salt"
    # fsp-connector: OAuth и привязка ФСП; пусто — эндпоинты отвечают 503
    fsp_connector_url: str = ""
    service_token_core: str = ""

    # подтверждение email перед приглашением и откликом
    email_verification_required: bool = False
    # SMTP для кода подтверждения; пусто — письма не отправляются (dev: Mailpit)
    smtp_host: str = ""
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@fsp-career.local"
    email_code_ttl_minutes: int = 15
    email_resend_cooldown_seconds: int = 60
    email_code_max_attempts: int = 5
    # LLM для резюме, навыков, теста; false — ml-воркеры не ходят в llama-server (ML_FAKE и т.п.)
    llm_enabled: bool = True
    # Fernet-ключ шифрования ПДн в БД (contacts_enc); в проде из PII_KEY
    pii_key: str = "ZGV2LW9ubHktcGlpLWtleS0wMTIzNDU2Nzg5YWJjZGU="
    # черновик ключа задания конструктора через ml-api; таймаут синхронного запроса
    assessment_key_draft_timeout_seconds: float = 30.0
    # заказы LLM-заданий из админки в сутки (UTC), на всю платформу
    family_orders_per_day: int = 20
    # демо-кнопки для ФСП: создание результатов и сброс
    demo_mode: bool = False
    # профиль без ФИО и контакта не попадает в выдачу работодателям (демо-аккаунты — попадают)
    require_candidate_contacts: bool = False
    # Open Badge 3.0: seed Ed25519 в base64url (32 байта); пусто: временный ключ процесса
    ob_signing_key: str = ""
    ob_issuer_domain: str = "fsp.patissons.tech"
