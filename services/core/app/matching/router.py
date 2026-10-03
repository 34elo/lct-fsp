"""Поиск кандидатов работодателем (api.md §2.5): `POST /search/candidates`."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fsp_contracts.ml import SearchFilters
from fsp_platform.app import ProblemError
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies import service as companies
from app.deps import get_redis, get_session
from app.graph.trust import TrustConfig
from app.identity.deps import require_roles
from app.identity.models import User
from app.matching import card, search
from app.matching.card import CandidateCardFull
from app.matching.scoring import MatchConfig
from app.vacancies import service as vacancies
from app.views import service as views

router = APIRouter(tags=["search"])

_employer = require_roles("employer")
_CFG = MatchConfig.load()
_TRUST = TrustConfig.load()


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: SearchFilters = Field(default_factory=SearchFilters)
    sort: search.Sort = "match"
    cursor: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=20, ge=1, le=search.MAX_LIMIT)
    vacancy_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None


class SearchPage(BaseModel):
    items: list[search.CandidateCard]
    next_cursor: str | None
    total: int
    session_id: uuid.UUID


@router.post("/search/candidates", response_model=SearchPage)
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
    page = await search.search_candidates(
        session, redis, company_id=company.id, filters=body.filters, sort=body.sort,
        cursor=body.cursor, limit=body.limit, vacancy_id=body.vacancy_id,
        vacancy_version=version, cfg=_CFG, trust=_TRUST,
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
                    "sort": body.sort,
                },
            )

    await session.commit()

    return {**page, "session_id": session_id}


@router.get("/candidates/{pseudo_id}/card", response_model=CandidateCardFull)
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
        session, cand, vacancy_id=vacancy_id, cfg=_CFG, trust=_TRUST, company_id=company.id
    )
    await views.record(
        session, candidate_id=cand.user_id, company_id=company.id, viewer_user_id=user.id,
        source=source, vacancy_id=vacancy_id,
    )  # fmt: skip
    return out


async def _get_candidate_id_by_pseudo_id(session: AsyncSession, pseudo_id: str) -> uuid.UUID | None:
    """Получить ID кандидата по его pseudo_id."""
    from sqlalchemy import select

    from app.candidates.models import Candidate

    result = await session.execute(
        select(Candidate.user_id).where(Candidate.pseudo_id == pseudo_id)
    )
    return result.scalar_one_or_none()
