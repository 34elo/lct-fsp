"""fsp-connector api: healthz; привязка, вебхук и синхронизация — E5-4…E5-6."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fsp_platform.app import create_app
from fsp_platform.db import make_engine, make_session_factory
from fsp_platform.logging import configure_logging
from redis.asyncio import Redis

from fsp_connector.config import Settings
from fsp_connector.factory import build_adapter

settings = Settings()
configure_logging(settings.service_name, settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    redis = Redis.from_url(settings.redis_url)
    engine = make_engine(settings.database_url)
    app.state.settings = settings
    app.state.adapter = build_adapter(settings, redis)
    app.state.session_factory = make_session_factory(engine)
    try:
        yield
    finally:
        inner = getattr(app.state.adapter, "inner", app.state.adapter)
        await inner.aclose()
        await redis.aclose()
        await engine.dispose()


app = create_app(settings.service_name, lifespan=lifespan)
