"""ml-api: синхронный HTTP для core (api.md §2.10). Сейчас — заглушки `ML_FAKE=true`."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fsp_contracts.ml import (
    EmbeddingsRequest,
    EmbeddingsResponse,
    MlHealth,
    SkillCardDraft,
    SkillCardDraftRequest,
    SkillResolveItem,
    SkillsResolveRequest,
)
from fsp_platform.app import ProblemError, create_app
from fsp_platform.logging import configure_logging

from fsp_ml import answer_explain, fake, family_bank, family_key, query_parse, skill_card
from fsp_ml.config import Settings
from fsp_ml.embedder import Embedder, embed, load_embedder
from fsp_ml.llm import LlmClient, OpenAiLlm
from fsp_ml.skill_pipeline import SkillPipeline
from fsp_ml.taxonomy import TaxonomyProvider


def build_app(
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    taxonomy: TaxonomyProvider | None = None,
    llm: LlmClient | None = None,
) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.service_name, settings.log_level)
    app = create_app(settings.service_name)
    real = embedder or load_embedder(
        settings.embedding_model_path, settings.embedding_model, settings.embedding_dim
    )
    taxonomy = taxonomy or TaxonomyProvider(settings.core_url, settings.service_token_ml)
    # LLM нужен только при ML_FAKE=false и LLM_ENABLED=true; иначе конвейер навыков идёт по правилам
    if llm is None and not settings.ml_fake and settings.llm_enabled and settings.llm_base_url:
        llm = OpenAiLlm(
            settings.llm_base_url,
            settings.llm_api_key,
            settings.llm_model,
            timeout=settings.llm_timeout,
            max_tokens=settings.llm_max_tokens,
        )
    pipeline = SkillPipeline(llm=llm, embedder=real, llm_model=settings.llm_model)
    # >>> block1 (assessment, taxonomy, identity, candidates, graph, resumes)
    app.include_router(family_key.build_router(settings))  # E30-1: черновик ключа задания
    app.include_router(family_bank.build_router(settings))  # E26-4: генератор и решатель
    app.include_router(answer_explain.build_router(settings))  # E24-2: «Объясни ответ»
    # <<< block1
    # >>> block2 (matching, offers, vacancies, companies, consents, fsp, telegram, analytics)
    app.include_router(query_parse.build_router(settings, llm))  # AU-2: разбор запроса без 503
    # <<< block2
    # у ml-api свой формат /healthz (api.md §2.10), вместо базового {"status": "ok"}
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/healthz"]

    def require_fake() -> None:
        # без LLM (lite) этот путь — правиловый разбор запроса
        if not settings.ml_fake and settings.llm_enabled:
            raise ProblemError(503, "ml_unavailable", "Модели ещё не подключены (ML_FAKE=false)")

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
        if index is None:  # снимка графа нет (ML_FAKE): заглушка
            return [fake.resolve_skill(m.raw) for m in req.mentions]
        return await pipeline.resolve(req.mentions, index)

    @app.post("/v1/skills/card-draft")
    async def skills_card_draft(req: SkillCardDraftRequest) -> SkillCardDraft:
        return await skill_card.draft_card(llm, req, settings.llm_model)

    @app.get("/healthz")
    async def healthz() -> MlHealth:
        up = "up" if settings.ml_fake and settings.llm_enabled else "down"
        emb = "up" if (real is not None or settings.ml_fake) else "down"
        return MlHealth(
            llm=up, embedder=emb, model=real.model if real else fake.FAKE_MODEL, queue_depth=0
        )

    return app


app = build_app()
