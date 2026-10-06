"""Поиск кандидатов работодателем (api.md §2.5): `POST /search/candidates`."""

from __future__ import annotations

import uuid
from datetime import datetime
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
from app.matching import card, navigator, query_llm, query_parser, search, similar, uplift_service
from app.matching.card import CandidateCardFull
from app.matching.scoring import MatchConfig
from app.matching.uplift import UpliftConfig
from app.openapi_errors import problem_responses
from app.recommendations.tuning import TuningConfig
from app.taxonomy import service as taxonomy
from app.vacancies import service as vacancies
from app.views import service as views

router = APIRouter(tags=["search"])

_employer = require_roles("employer")
_candidate = require_roles("candidate")
_CFG = MatchConfig.load()
_TRUST = TrustConfig.load()
_UPLIFT = UpliftConfig.load()
_TUNING = TuningConfig.load()

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


class TuningChip(BaseModel):
    feature: str
    text: str
    change: float


class TuningHint(BaseModel):
    kind: str
    reason: str
    text: str
    count: int


class SearchTuning(BaseModel):
    """Подстройка выдачи в сессии (matching.md §7): включается после ≥ 3 реакций."""

    active: bool
    signals: int
    chips: list[TuningChip]
    hints: list[TuningHint]


class SearchPage(BaseModel):
    items: list[search.CandidateCard]
    next_cursor: str | None
    total: int
    session_id: uuid.UUID
    tuning: SearchTuning | None = None


def _query_llm(request: Request) -> query_llm.QueryLlmClient | None:
    """Клиент ml-api для разбора запроса; `ML_API_URL` пуст — только правила."""
    state = request.app.state
    client = getattr(state, "query_llm", None)
    if client is None:
        url = state.settings.ml_api_url
        if not url:
            return None
        client = query_llm.QueryLlmClient(url, timeout=state.settings.query_parse_timeout_seconds)
        state.query_llm = client
    client.redis = getattr(state, "redis", None)
    return client


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=query_parser.MAX_TEXT)


@router.post(
    "/search/parse", response_model=ParsedQuery, responses=problem_responses(401, 403, 422)
)
async def search_parse(
    body: ParseRequest,
    request: Request,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Разбор текста в чипсы-фильтры: правила (E7-5) + LLM-уточнение и слияние (E7-6).

    LLM недоступна или ответила невалидно — отдаём правиловый результат (`refining=false`).
    """
    index = await taxonomy.alias_index(session)
    rule = query_parser.parse_query(body.text, index.forms, index.names)
    client = _query_llm(request)
    if client is None:
        return rule
    return await query_llm.refine(
        client,
        body.text,
        rule,
        taxonomy_version=await taxonomy.get_version(session),
        forms=index.forms,
        names=index.names,
    )


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
    signals = None
    if body.session_id is not None:  # подстройка только по своей сессии (matching.md §7)
        signals = await rec_service.session_signals(
            session, redis, user.id, str(body.session_id), _TUNING
        )
    page = await search.search_candidates(
        session, redis, company_id=company.id, filters=body.filters, sort=sort,
        cursor=body.cursor, limit=body.limit, vacancy_id=body.vacancy_id,
        vacancy_version=version, cfg=_CFG, trust=_TRUST,
        responsibility_score=company.responsibility_score, session_signals=signals,
        tuning_cfg=_TUNING,
    )  # fmt: skip
    features = page.pop("features", None) or {}

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
                    "x": features.get(item["pseudo_id"]),
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


class NavTarget(BaseModel):
    role: str
    grade: str


class NavCurrent(BaseModel):
    profession: str
    grade: str
    valid_until: datetime
    needs_confirmation: bool


class NavNextGrade(BaseModel):
    points_needed: float
    hints: list[str]


class NavTest(BaseModel):
    profession: str
    grade: str
    path: str  # маршрут блока 1: /me/assessment?profession=&grade=


class NavGap(BaseModel):
    skill: str
    name: str
    weight: float
    confidence: float
    testable: bool


class NavCompetition(BaseModel):
    id: str
    title: str
    start_date: str
    registration_url: str | None = None
    skills: list[str]


class NavigatorOut(BaseModel):
    target: NavTarget | None = None
    current_grade: NavCurrent | None = None
    next_grade: NavNextGrade | None = None
    test: NavTest | None = None
    skill_gaps: list[NavGap]
    competitions: list[NavCompetition]
    uplift: list[UpliftItem]


@router.get(
    "/candidates/me/navigator",
    response_model=NavigatorOut,
    response_model_exclude_none=True,
    responses=problem_responses(401, 403),
)
async def my_navigator(
    user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> Any:
    """Путь к следующему грейду: пробелы по профессии, тест, соревнования ФСП, uplift."""
    cand = await candidates.get(session, user.id)
    if cand is None:
        return {"skill_gaps": [], "competitions": [], "uplift": []}
    up = await uplift_service.compute(session, redis, cand, _CFG, _TRUST, _UPLIFT)
    return await navigator.compute(session, cand, up["items"], _UPLIFT)


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
