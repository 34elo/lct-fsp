"""Потребности и категории работодателя (assessment.md §9–10, api.md): `POST /needs`,
`GET /needs/{id}/categories`, `GET /categories/{profession}/{grade}/candidates`."""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fsp_contracts.assessment import CategoryRef
from fsp_contracts.ml import SearchFilters
from fsp_platform.app import ProblemError
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import service as analytics
from app.companies import service as companies
from app.deps import get_redis, get_session
from app.graph.trust import TrustConfig
from app.identity.deps import require_roles
from app.identity.models import User
from app.matching import needs, needs_service, query_parser, search
from app.matching import query_llm as qllm
from app.matching.needs_service import NeedCategory
from app.matching.router import _query_llm
from app.matching.scoring import MatchConfig
from app.matching.strength import StrengthConfig
from app.openapi_errors import problem_responses
from app.taxonomy import service as taxonomy

router = APIRouter(tags=["needs"])

_employer = require_roles("employer")
_CFG = MatchConfig.load()
_TRUST = TrustConfig.load()
_STRENGTH = StrengthConfig.load()
_NEEDS = needs.NeedsConfig.load()


class NeedCreate(BaseModel):
    """Потребность текстом, формой (`filters`) или обоими: поля формы перекрывают текст."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, min_length=1, max_length=query_parser.MAX_TEXT)
    filters: SearchFilters | None = None


class NeedOut(BaseModel):
    id: uuid.UUID
    text: str | None
    filters: SearchFilters
    skills: dict[str, float]  # slug навыка → вес потребности
    grades: list[str]
    shortlist: list[str] = []  # pseudo_id кандидатов в шорт-листе (E23-5)
    created_at: datetime
    categories: list[NeedCategory]


class NeedCategories(BaseModel):
    need_id: uuid.UUID
    shortlist: list[str] = []  # pseudo_id кандидатов в шорт-листе (E23-5)
    categories: list[NeedCategory]


class CategoryPage(BaseModel):
    items: list[search.CandidateCard]
    next_cursor: str | None
    total: int


@router.post(
    "/needs",
    status_code=201,
    response_model=NeedOut,
    responses=problem_responses(401, 403, 404, 422),
)
async def create_need(
    body: NeedCreate,
    request: Request,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    company, _ = await companies.require_company(session, user.id)
    parsed = None
    if body.text:
        index = await taxonomy.alias_index(session)
        rule = query_parser.parse_query(body.text, index.forms, index.names)
        client = _query_llm(request)
        parsed = (
            rule
            if client is None
            else await qllm.refine(
                client, body.text, rule,
                taxonomy_version=await taxonomy.get_version(session),
                forms=index.forms, names=index.names,
            )
        ).filters  # fmt: skip
    elif body.filters is None:
        raise ProblemError(422, "need_empty", "Опишите потребность текстом или фильтрами")
    filters = needs_service.merge_filters(parsed, body.filters)
    need = await needs_service.create(session, company.id, body.text, filters, _NEEDS)
    t0 = time.perf_counter()
    cats = await needs_service.categories(session, company.id, need, _NEEDS)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    salt = request.app.state.settings.analytics_salt
    track = analytics.track_employer
    await track(
        session, salt, company.id, "need_created",
        {
            "need_id": str(need.id), "skills": len(need.weights),
            "has_vacancy": False, "grade": need.grades[0] if len(need.grades) == 1 else None,
        },
    )  # fmt: skip
    await track(
        session, salt, company.id, "need_categories_shown",
        {"need_id": str(need.id), "categories": len(cats), "latency_ms": latency_ms},
    )  # fmt: skip
    await session.commit()
    return NeedOut(
        id=need.id, text=need.text, filters=filters, skills=need.weights, grades=need.grades,
        shortlist=need.shortlist, created_at=need.created_at, categories=cats,
    )  # fmt: skip


@router.get(
    "/needs/{need_id}/categories",
    response_model=NeedCategories,
    responses=problem_responses(401, 403, 404),
)
async def need_categories(
    need_id: uuid.UUID,
    request: Request,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    company, _ = await companies.require_company(session, user.id)
    need = await needs_service.get_owned(session, company.id, need_id)
    t0 = time.perf_counter()
    cats = await needs_service.categories(session, company.id, need, _NEEDS)
    await analytics.track_employer(
        session, request.app.state.settings.analytics_salt, company.id, "need_categories_shown",
        {
            "need_id": str(need.id), "categories": len(cats),
            "latency_ms": int((time.perf_counter() - t0) * 1000),
        },
    )  # fmt: skip
    await session.commit()
    return {"need_id": need.id, "shortlist": need.shortlist, "categories": cats}


@router.get(
    "/categories/{profession}/{grade}/candidates",
    response_model=CategoryPage,
    responses=problem_responses(401, 403, 404, 422),
)
async def category_candidates(
    profession: str,
    grade: str,
    request: Request,
    need_id: uuid.UUID | None = None,
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=20, ge=1, le=search.MAX_LIMIT),
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> Any:
    """Анонимные карточки категории по `rank = 0.6·match + 0.4·strength` с объяснением."""
    try:
        category = CategoryRef(profession=profession, grade=grade)  # type: ignore[arg-type]
    except ValidationError as e:
        raise ProblemError(422, "invalid_category", "Неизвестная категория") from e
    company, _ = await companies.require_company(session, user.id)
    need = await needs_service.get_owned(session, company.id, need_id) if need_id else None
    page = await search.search_candidates(
        session, redis, company_id=company.id, filters=needs_service.listing_filters(need),
        sort="match", cursor=cursor, limit=limit, vacancy_id=None, vacancy_version=None,
        cfg=_CFG, trust=_TRUST, responsibility_score=company.responsibility_score,
        category=category, strength_cfg=_STRENGTH,
    )  # fmt: skip

    # Mark shortlisted candidates (E23-5)
    shortlist = set(need.shortlist) if need else set()
    for item in page["items"]:
        item["is_shortlisted"] = item["pseudo_id"] in shortlist

    if cursor is None:  # просмотр категории считаем по первой странице
        await analytics.track_employer(
            session, request.app.state.settings.analytics_salt, company.id, "category_viewed",
            {
                "profession": profession, "grade": grade, "candidates": page["total"],
                "need_id": str(need.id) if need else None,
            },
        )  # fmt: skip
        await session.commit()
    return {k: page[k] for k in ("items", "next_cursor", "total")}


async def _track_shortlist(
    request: Request, session: AsyncSession, company_id: uuid.UUID, need: Any, name: str
) -> None:
    await analytics.track_employer(
        session, request.app.state.settings.analytics_salt, company_id, name,
        {"need_id": str(need.id), "size": len(need.shortlist)},
    )  # fmt: skip


@router.post(
    "/needs/{need_id}/shortlist/{pseudo_id}",
    status_code=204,
    responses=problem_responses(401, 403, 404),
)
async def shortlist_add(
    need_id: uuid.UUID,
    pseudo_id: str,
    request: Request,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Добавить кандидата в шорт-лист потребности (E23-5). Фильтр не сбрасывает отмеченных."""
    company, _ = await companies.require_company(session, user.id)
    need = await needs_service.get_owned(session, company.id, need_id)
    # Проверить, что кандидат существует
    from sqlalchemy import select

    from app.candidates.models import Candidate

    result = await session.execute(
        select(Candidate.user_id).where(Candidate.pseudo_id == pseudo_id)
    )
    if result.scalar_one_or_none() is None:
        raise ProblemError(404, "candidate_not_found", "Кандидат не найден")
    # Добавить в шорт-лист, если там ещё нет
    if pseudo_id not in need.shortlist:
        # переприсвоение: изменение JSON-списка на месте SQLAlchemy не видит
        need.shortlist = [*need.shortlist, pseudo_id]
        await _track_shortlist(request, session, company.id, need, "shortlist_added")
        await session.commit()


@router.delete(
    "/needs/{need_id}/shortlist/{pseudo_id}",
    status_code=204,
    responses=problem_responses(401, 403, 404),
)
async def shortlist_remove(
    need_id: uuid.UUID,
    pseudo_id: str,
    request: Request,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Удалить кандидата из шорт-листа потребности (E23-5)."""
    company, _ = await companies.require_company(session, user.id)
    need = await needs_service.get_owned(session, company.id, need_id)
    # Удалить из шорт-листа, если там есть
    if pseudo_id in need.shortlist:
        need.shortlist = [p for p in need.shortlist if p != pseudo_id]
        await _track_shortlist(request, session, company.id, need, "shortlist_removed")
        await session.commit()
