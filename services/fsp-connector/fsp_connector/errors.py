"""Ошибки порта ФСП: адаптеры приводят любые сбои источника к этим типам."""


class FspError(Exception):
    code = "fsp_error"


class FspNotFound(FspError):
    code = "fsp_not_found"


class FspAuthError(FspError):
    """Источник отверг наш ключ или токен."""

    code = "fsp_auth_error"


class FspBadResponse(FspError):
    """Ответ источника не сходится со схемой (маппинг или контракт сломаны)."""

    code = "fsp_bad_response"


class FspUnavailable(FspError):
    """Источник недоступен: ретраи исчерпаны или открыт circuit breaker."""

    code = "fsp_unavailable"
