"""ml-api: синхронный HTTP для core (api.md §2.10). Сейчас — заглушки `ML_FAKE=true`."""

from __future__ import annotations

from fastapi import FastAPI
from fsp_contracts.ml import (
    EmbeddingsRequest,
    EmbeddingsResponse,
    MlHealth,
    ParsedQuery,
    QueryParseRequest,
    SkillResolveItem,
    SkillsResolveRequest,
)
from fsp_platform.app import ProblemError, create_app
from fsp_platform.logging import configure_logging

from fsp_ml import fake
from fsp_ml.config import Settings


def build_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.service_name, settings.log_level)
    app = create_app(settings.service_name)
    # у ml-api свой формат /healthz (api.md §2.10), вместо базового {"status": "ok"}
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/healthz"]

    def require_fake() -> None:
        if not settings.ml_fake:
            raise ProblemError(503, "ml_unavailable", "Модели ещё не подключены (ML_FAKE=false)")

    @app.post("/v1/query/parse")
    async def query_parse(req: QueryParseRequest) -> ParsedQuery:
        require_fake()
        return fake.parse_query(req)

    @app.post("/v1/embeddings")
    async def embeddings(req: EmbeddingsRequest) -> EmbeddingsResponse:
        require_fake()
        return fake.embeddings(req, settings.embedding_dim)

    @app.post("/v1/skills/resolve")
    async def skills_resolve(req: SkillsResolveRequest) -> list[SkillResolveItem]:
        require_fake()
        return fake.resolve_skills(req)

    @app.get("/healthz")
    async def healthz() -> MlHealth:
        up = "up" if settings.ml_fake else "down"
        return MlHealth(llm=up, embedder=up, model=fake.FAKE_MODEL, queue_depth=0)

    return app


app = build_app()
