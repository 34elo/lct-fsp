from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fsp_platform.app import ProblemError, create_app
from fsp_platform.db import make_engine, make_session_factory
from fsp_platform.logging import configure_logging
from fsp_platform.ratelimit import RateLimiter
from fsp_platform.storage import ObjectStorage
from redis.asyncio import Redis
from sqlalchemy import text

from app.candidates.router import router as candidates_router
from app.config import Settings
from app.consents.router import router as consents_router
from app.events_stream import UiHub
from app.events_stream import router as events_router
from app.identity.router import router as identity_router


def build_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.service_name, settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(settings.database_url)
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        app.state.redis = Redis.from_url(settings.redis_url)
        app.state.limiter = RateLimiter(app.state.redis)
        app.state.storage = ObjectStorage(
            settings.s3_endpoint,
            settings.s3_access_key,
            settings.s3_secret_key,
            settings.s3_bucket,
            settings.s3_public_url,
        )
        hub = UiHub(settings.rabbitmq_url if settings.ui_bus_enabled else None)
        app.state.ui_hub = hub
        try:
            await hub.start()
        except Exception:  # брокер недоступен: REST живёт, SSE молчит до рестарта
            logging.getLogger(__name__).exception("ui_hub_start_failed")
        yield
        await hub.stop()
        await app.state.redis.aclose()
        await engine.dispose()

    app = create_app(settings.service_name, lifespan=lifespan)
    app.state.settings = settings
    app.state.ui_hub = UiHub()  # без брокера, пока не стартовал lifespan
    app.include_router(events_router)
    app.include_router(identity_router)
    app.include_router(consents_router)
    app.include_router(candidates_router)

    @app.get("/readyz", include_in_schema=False)
    async def readyz():
        try:
            async with app.state.engine.connect() as conn:
                await conn.execute(text("select 1"))
            await app.state.redis.ping()
        except Exception as exc:
            raise ProblemError(503, "not_ready", "Зависимости недоступны") from exc
        return {"status": "ready"}

    return app


app = build_app()
