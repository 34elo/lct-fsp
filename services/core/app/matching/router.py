"""Поиск кандидатов работодателем (api.md §2.5): `POST /search/candidates`."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fsp_contracts.ml import ParsedQuery, SearchFilters
from fsp_platform.app import ProblemError
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service as candidates
from app.companies import service as companies
from app.deps import get_redis, get_session
from app.graph.trust import TrustConfig
from app.identity.deps import require_roles
from app.identity.models import User
from app.matching import card, query_parser, search, similar, uplift_service
from app.matching.card import CandidateCardFull
from app.matching.scoring import MatchConfig
from app.matching.uplift import UpliftConfig
from app.openapi_errors import problem_responses
from app.taxonomy import service as taxonomy
from app.vacancies import service as vacancies
from app.views import service as views

router = APIRouter(tags=["search"])

_employer = require_roles("employer")
_candidate = require_roles("candidate")
_CFG = MatchConfig.load()
_TRUST = TrustConfig.load()
_UPLIFT = UpliftConfig.load()

# Responses for error codes
_PARSE_RESPONSES = problem_responses(401, 403, 422)
_SEARCH_RESPONSES = problem_responses(401, 403, 404, 422)
_CARD_RESPONSES = problem_responses(401, 403, 404)
_UPLIFT_RESPONSES = problem_responses(401, 403)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: SearchFilters = Field(default_factory=SearchFilters)
    sort: search.Sort | None = None  # по умолчанию: с вакансией — mutual (H), без — match
    cursor: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=20, ge=1, le=search.MAX_LIMIT)
    vacancy_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None


class SearchPage(BaseModel):
    items: list[search.CandidateCard]
    next_cursor: str | None
    total: int
    session_id: uuid.UUID


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=query_parser.MAX_TEXT)


@router.post(
    "/search/parse", response_model=ParsedQuery, responses=problem_responses(401, 403, 422)
)
async def search_parse(
    body: ParseRequest,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Правиловый разбор текста в чипсы-фильтры (E7-5); LLM-уточнение добавит E7-6."""
    index = await taxonomy.alias_index(session)
    return query_parser.parse_query(body.text, index.forms, index.names)


@router.post(
    "/search/candidates", response_model=SearchPage, responses=problem_responses(401, 403, 404, 422)
)
async def search_candidates(
    body: SearchRequest,
    request: Request,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> Any:
    from app.recommendations import service as rec_service

    company, _ = await companies.require_company(session, user.id)
    version = None
    if body.vacancy_id is not None:  # чужая или несуществующая вакансия → 404
        version = (await vacancies.get_owned(session, user, body.vacancy_id)).version
    sort = body.sort or ("mutual" if body.vacancy_id else "match")
    page = await search.search_candidates(
        session, redis, company_id=company.id, filters=body.filters, sort=sort,
        cursor=body.cursor, limit=body.limit, vacancy_id=body.vacancy_id,
        vacancy_version=version, cfg=_CFG, trust=_TRUST,
        responsibility_score=company.responsibility_score,
    )  # fmt: skip

    session_id = body.session_id or uuid.uuid4()
    context_type = "vacancy" if body.vacancy_id else "search"
    context_id = str(body.vacancy_id) if body.vacancy_id else ""

    # Логировать impressions для каждого кандидата в выдаче (E17-1)
    for position, item in enumerate(page["items"], 1):
        candidate_id = await _get_candidate_id_by_pseudo_id(session, item["pseudo_id"])
        if candidate_id:
            match = item.get("match") or {}
            await rec_service.record_impression(
                session,
                company_id=company.id,
                user_id=user.id,
                session_id=str(session_id),
                context_type=context_type,
                context_id=context_id,
                candidate_id=candidate_id,
                position=position,
                score=match.get("score", 0.0),
                features={
                    "search_filters": body.filters.model_dump(mode="json"),
                    "sort": sort,
                },
            )

    await session.commit()

    return {**page, "session_id": session_id}


@router.get(
    "/candidates/{pseudo_id}/card",
    response_model=CandidateCardFull,
    responses=problem_responses(401, 403, 404),
)
async def candidate_card(
    pseudo_id: str,
    vacancy_id: uuid.UUID | None = None,
    source: Literal["search", "match", "similar", "direct"] = "direct",
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    company, _ = await companies.require_company(session, user.id)
    if vacancy_id is not None:  # чужая или несуществующая вакансия → 404
        await vacancies.get_owned(session, user, vacancy_id)
    cand = await card.get_visible(session, pseudo_id, company.id)
    if cand is None:
        raise ProblemError(404, "candidate_not_found", "Кандидат не найден")
    out = await card.build_card(
        session,
        cand,
        vacancy_id=vacancy_id,
        cfg=_CFG,
        trust=_TRUST,
        company_id=company.id,
        responsibility_score=company.responsibility_score,
    )
    await views.record(
        session, candidate_id=cand.user_id, company_id=company.id, viewer_user_id=user.id,
        source=source, vacancy_id=vacancy_id,
    )  # fmt: skip
    return out


class SimilarPage(BaseModel):
    items: list[similar.SimilarCard]
    session_id: uuid.UUID


@router.get(
    "/candidates/{pseudo_id}/similar",
    response_model=SimilarPage,
    responses=problem_responses(401, 403, 404),
)
async def candidate_similar(
    pseudo_id: str,
    limit: int = Query(default=10, ge=1, le=similar.MAX_LIMIT),
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Похожие на открытого кандидата (matching.md §1); скрытый или несуществующий → 404."""
    from app.recommendations import service as rec_service

    company, _ = await companies.require_company(session, user.id)
    cand = await card.get_visible(session, pseudo_id, company.id)
    if cand is None:
        raise ProblemError(404, "candidate_not_found", "Кандидат не найден")
    items = await similar.find_similar(
        session, cand, company_id=company.id, trust=_TRUST, limit=limit
    )
    session_id = uuid.uuid4()
    for position, item in enumerate(items, 1):
        cid = await _get_candidate_id_by_pseudo_id(session, item["pseudo_id"])
        if cid:
            await rec_service.record_impression(
                session, company_id=company.id, user_id=user.id, session_id=str(session_id),
                context_type="similar", context_id=pseudo_id, candidate_id=cid,
                position=position, score=item["similarity"], features={"sort": "similar"},
            )  # fmt: skip
    await session.commit()
    return {"items": items, "session_id": session_id}


async def _get_candidate_id_by_pseudo_id(session: AsyncSession, pseudo_id: str) -> uuid.UUID | None:
    """Получить ID кандидата по его pseudo_id."""
    from sqlalchemy import select

    from app.candidates.models import Candidate

    result = await session.execute(
        select(Candidate.user_id).where(Candidate.pseudo_id == pseudo_id)
    )
    return result.scalar_one_or_none()


class UpliftConfirm(BaseModel):
    kind: Literal["test", "github", "fsp_competition"]
    minutes: int | None = None
    id: str | None = None
    title: str | None = None
    start_date: str | None = None
    registration_url: str | None = None


class UpliftItem(BaseModel):
    skill: str
    name: str
    current_level: int
    extra: int
    pct: float
    median_salary_delta: int
    how_to_confirm: list[UpliftConfirm]


class UpliftCombo(BaseModel):
    skills: list[str]
    extra: int
    pct: float


class UpliftOut(BaseModel):
    relevant_total: int
    base: int
    items: list[UpliftItem]
    combo: UpliftCombo | None = None


@router.get(
    "/candidates/me/uplift",
    response_model=UpliftOut,
    response_model_exclude_none=True,
    responses=problem_responses(401, 403),
)
async def my_uplift(
    user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> Any:
    """Какой навык подтвердить, чтобы подойти под больше вакансий (matching.md §6)."""
    cand = await candidates.get(session, user.id)
    if cand is None:
        return uplift_service.empty()
    out = await uplift_service.compute(session, redis, cand, _CFG, _TRUST, _UPLIFT)
    out.setdefault("combo", None)
    return out
