"""ml-api: синхронный HTTP для core (api.md §2.10). Сейчас — заглушки `ML_FAKE=true`."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
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
from fsp_ml.embedder import Embedder, embed, load_embedder
from fsp_ml.taxonomy import TaxonomyProvider


def build_app(
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    taxonomy: TaxonomyProvider | None = None,
) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.service_name, settings.log_level)
    app = create_app(settings.service_name)
    real = embedder or load_embedder(settings.embedding_model_path)
    taxonomy = taxonomy or TaxonomyProvider(settings.core_url, settings.service_token_ml)
    # >>> block1 (assessment, taxonomy, identity, candidates, graph, resumes)
    # <<< block1
    # >>> block2 (matching, offers, vacancies, companies, consents, fsp, telegram, analytics)
    # <<< block2
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
        if real is None:
            require_fake()
        if len(req.texts) > settings.embedding_max_texts:
            raise ProblemError(422, "too_many_texts", "Слишком много текстов в одном запросе")
        return await run_in_threadpool(embed, req, real, settings.embedding_dim)

    @app.post("/v1/skills/resolve")
    async def skills_resolve(req: SkillsResolveRequest) -> list[SkillResolveItem]:
        index = await taxonomy.get(req.taxonomy_version)
        if index is None:
            require_fake()
        out: list[SkillResolveItem] = []
        for m in req.mentions:
            hit = index.resolve(m) if index else None
            # остальной конвейер (модерация, судья) — E16-4; до него заглушка
            out.append(hit or fake.resolve_skill(m.raw))
        return out

    @app.get("/healthz")
    async def healthz() -> MlHealth:
        up = "up" if settings.ml_fake else "down"
        emb = "up" if (real is not None or settings.ml_fake) else "down"
        return MlHealth(
            llm=up, embedder=emb, model=real.model if real else fake.FAKE_MODEL, queue_depth=0
        )

    return app


app = build_app()
