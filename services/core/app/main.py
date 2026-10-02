from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fsp_platform.app import ProblemError, create_app
from fsp_platform.db import make_engine, make_session_factory
from fsp_platform.logging import configure_logging
from fsp_platform.ratelimit import RateLimiter
from fsp_platform.storage import ObjectStorage
from redis.asyncio import Redis
from sqlalchemy import text

from app.config import Settings


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
        yield
        await app.state.redis.aclose()
        await engine.dispose()

    app = create_app(settings.service_name, lifespan=lifespan)

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
