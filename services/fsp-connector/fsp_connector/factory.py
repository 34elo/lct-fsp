"""Выбор адаптера по `FSP_ADAPTER`."""

from __future__ import annotations

from redis.asyncio import Redis

from fsp_connector.cache import CachedFspAdapter
from fsp_connector.config import Settings
from fsp_connector.http_adapter import HttpFspAdapter
from fsp_connector.mappings import get_mapping
from fsp_connector.resilience import CircuitBreaker


def build_adapter(
    settings: Settings, redis: Redis | None = None
) -> CachedFspAdapter | HttpFspAdapter:
    if settings.fsp_adapter != "mock":
        # адаптер под API организаторов — новый маппинг добавляется в mappings/
        raise NotImplementedError(f"FSP_ADAPTER={settings.fsp_adapter}: адаптер не реализован")
    http = HttpFspAdapter(
        settings.fsp_base_url,
        settings.fsp_api_key,
        get_mapping("mock"),
        public_url=settings.fsp_public_url,
        oauth_client_id=settings.fsp_oauth_client_id,
        oauth_redirect_uri=settings.fsp_oauth_redirect_uri,
        timeout=settings.fsp_timeout_seconds,
        retries=settings.fsp_retries,
        retry_base=settings.fsp_retry_base_seconds,
        breaker=CircuitBreaker(settings.fsp_breaker_failures, settings.fsp_breaker_open_seconds),
    )
    if redis is None:
        return http
    return CachedFspAdapter(http, redis, settings.fsp_cache_ttl_seconds)
