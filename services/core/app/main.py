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

from app.analytics.dashboard_router import router as analytics_dashboard_router
from app.analytics.metrics_router import router as analytics_metrics_router
from app.analytics.router import internal as analytics_internal_router
from app.analytics.router import router as analytics_router
from app.analytics.runs_router import admin as live_runs_admin_router
from app.analytics.runs_router import public as live_runs_public_router

# >>> block1 (assessment, taxonomy, identity, candidates, graph, resumes)
from app.assessment.admin_router import router as admin_families_router
from app.assessment.constructor_router import router as families_router
from app.assessment.demo_router import router as admin_demo_router
from app.assessment.router import router as assessment_router
from app.assessment.tasks_router import candidate_router as candidate_tasks_router
from app.assessment.tasks_router import employer_router as employer_tasks_router

# <<< block1
# >>> block2 (matching, offers, vacancies, companies, consents, fsp, telegram, analytics)
# <<< block2
from app.candidates.router import router as candidates_router
from app.companies.router import admin_router as admin_companies_router
from app.companies.router import invites_router as company_invites_router
from app.companies.router import router as companies_router
from app.config import Settings
from app.consents.router import router as consents_router
from app.credentials.router import router as credentials_router
from app.events_stream import UiHub
from app.events_stream import router as events_router
from app.fsp.router import router as fsp_router
from app.graph.router import router as graph_router
from app.identity.profile_router import router as profile_router
from app.identity.router import router as identity_router
from app.matching.needs_router import router as needs_router
from app.matching.router import router as search_router
from app.matching.subscriptions_router import router as subscriptions_router
from app.offers.activity import router as employer_activity_router
from app.offers.router import admin_router as admin_complaints_router
from app.offers.router import router as offers_router
from app.recommendations.router import router as recommendations_router
from app.resumes.router import router as resumes_router
from app.taxonomy.admin_router import router as admin_taxonomy_router
from app.taxonomy.router import router as taxonomy_router
from app.taxonomy.skills_router import router as admin_skills_router
from app.telegram.router import internal as telegram_internal_router
from app.telegram.router import router as telegram_router
from app.vacancies.router import router as vacancies_router
from app.views.router import router as views_router


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
    app.include_router(telegram_router)
    app.include_router(telegram_internal_router)
    app.include_router(candidates_router)
    app.include_router(fsp_router)
    app.include_router(resumes_router)
    app.include_router(taxonomy_router)
    app.include_router(companies_router)
    app.include_router(admin_companies_router)
    app.include_router(vacancies_router)
    app.include_router(search_router)
    app.include_router(recommendations_router)
    app.include_router(offers_router)
    app.include_router(admin_complaints_router)
    # >>> block1 (assessment, taxonomy, identity, candidates, graph, resumes)
    app.include_router(assessment_router)
    app.include_router(admin_families_router)
    app.include_router(admin_demo_router)
    app.include_router(admin_taxonomy_router)
    app.include_router(admin_skills_router)
    app.include_router(families_router)
    app.include_router(employer_tasks_router)
    app.include_router(candidate_tasks_router)
    app.include_router(graph_router)  # /candidates/me/graph раньше {pseudo_id}
    # <<< block1
    # >>> block2 (matching, offers, vacancies, companies, consents, fsp, telegram, analytics)
    app.include_router(employer_activity_router)
    app.include_router(analytics_router)
    app.include_router(analytics_internal_router)
    app.include_router(live_runs_admin_router)
    app.include_router(live_runs_public_router)
    app.include_router(analytics_dashboard_router)
    app.include_router(analytics_metrics_router)
    app.include_router(needs_router)
    app.include_router(subscriptions_router)
    app.include_router(views_router)
    app.include_router(credentials_router)
    app.include_router(profile_router)
    app.include_router(company_invites_router)
    # <<< block2

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
