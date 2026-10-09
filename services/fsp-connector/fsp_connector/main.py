"""fsp-connector api: healthz, internal API привязки и реестра ФСП (E39-28); вебхук ФСП (E5-6)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fsp_platform.app import create_app, problem_response
from fsp_platform.db import make_engine, make_session_factory
from fsp_platform.logging import configure_logging
from redis.asyncio import Redis

from fsp_connector.api import STATUS, router
from fsp_connector.config import Settings
from fsp_connector.errors import FspError
from fsp_connector.factory import build_adapter
from fsp_connector.linking import LinkService
from fsp_connector.registry import RegistryAdapter, RegistryService
from fsp_connector.registry_api import router as registry_router
from fsp_connector.sync import SyncService
from fsp_connector.webhook import router as webhook_router

settings = Settings()
configure_logging(settings.service_name, settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    redis = Redis.from_url(settings.redis_url)
    engine = make_engine(settings.database_url)
    app.state.settings = settings
    app.state.session_factory = make_session_factory(engine)
    # реестр ФСП поверх источника (ADR-052): синхронизация и привязка видят оба
    app.state.adapter = RegistryAdapter(build_adapter(settings, redis), app.state.session_factory)
    app.state.redis = redis
    app.state.sync = SyncService(app.state.adapter, app.state.session_factory)
    app.state.links = LinkService(
        app.state.adapter,
        app.state.session_factory,
        redis,
        code_ttl=settings.fsp_code_ttl_seconds,
        max_attempts=settings.fsp_code_max_attempts,
    )
    app.state.registry = RegistryService(app.state.session_factory, app.state.links, app.state.sync)
    try:
        yield
    finally:
        await app.state.adapter.aclose()
        await redis.aclose()
        await engine.dispose()


def build() -> FastAPI:
    application = create_app(settings.service_name, lifespan=lifespan)
    application.include_router(router)
    application.include_router(registry_router)
    application.include_router(webhook_router)

    @application.exception_handler(FspError)
    async def _fsp_error(_: Request, exc: FspError):
        status, title = STATUS.get(exc.code, STATUS["fsp_error"])
        return problem_response(status, exc.code, title)

    return application


app = build()
