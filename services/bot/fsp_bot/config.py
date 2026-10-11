from fsp_platform.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "bot"
    tg_bot_token: str = ""  # TG_BOT_TOKEN из .env; пусто → бот не стартует
    # TG_API_BASE: свой адрес Bot API (ретранслятор на VPS, infra/vps/fsp.caddy), если
    # api.telegram.org недоступен с сервера напрямую; пусто → api.telegram.org
    tg_api_base: str = ""
    service_token_bot: str = ""  # SERVICE_TOKEN_BOT из .env
    core_url: str = "http://core-api:8000"
    core_timeout: float = 10.0
    web_base_url: str = ""  # WEB_BASE_URL: адрес сайта для кнопки «Открыть сайт»
    fsm_ttl_seconds: int = 1800  # таймаут состояний 30 минут
    # Лимиты Telegram
    send_rate_global: float = 25.0
    send_rate_per_chat: float = 1.0
    send_max_retries: int = 3
    # Сколько хранить соответствие edit_of → message_id и отметки о доставке
    message_map_ttl_seconds: int = 30 * 86400
    sent_ttl_seconds: int = 86400
