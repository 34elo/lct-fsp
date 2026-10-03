"""Офферы (api.md §2.5): создание с `Idempotency-Key`, чтение, ответы, действия компании."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Response
from fsp_contracts.enums import (
    DeclineReason,
    EmploymentType,
    Grade,
    OfferStatus,
    RoleSlug,
    WorkFormat,
)
from fsp_contracts.ml import ExplanationItem
from fsp_platform.app import ProblemError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service as candidates
from app.companies import service as companies
from app.deps import get_session
from app.graph.trust import TrustConfig
from app.identity.deps import require_roles
from app.identity.models import User
from app.matching import card
from app.matching.scoring import MatchConfig
from app.matching.search import CandidateCard
from app.offers import service
from app.offers.models import Offer
from app.vacancies import service as vacancies

router = APIRouter(tags=["offers"])

_employer = require_roles("employer")
_candidate = require_roles("candidate")
_both = require_roles("employer", "candidate")
_LIMITS = service.OfferLimits.load()
_CFG = MatchConfig.load()
_TRUST = TrustConfig.load()


class CreateOffer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vacancy_id: uuid.UUID
    candidate_pseudo_id: str = Field(min_length=1, max_length=64)
    # обязательны по смыслу; отсутствие даёт 422 `salary_range_required`, а не общую ошибку схемы
    salary_from: int | None = Field(default=None, le=100_000_000)
    salary_to: int | None = Field(default=None, le=100_000_000)
    message: str | None = Field(default=None, max_length=2000)


class DeclineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: DeclineReason
    comment: str | None = Field(default=None, max_length=1000)


class StatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: OfferStatus


class VacancyBrief(BaseModel):
    id: uuid.UUID
    title: str
    role: RoleSlug
    grade_min: Grade
    grade_max: Grade
    formats: list[WorkFormat]
    employment_type: EmploymentType


class MatchSnapshot(BaseModel):
    score: float
    explanation: list[ExplanationItem]


class Decline(BaseModel):
    reason: DeclineReason
    comment: str | None = None


class OfferOut(BaseModel):
    id: uuid.UUID
    status: OfferStatus
    created_at: datetime
    expires_at: datetime
    vacancy: VacancyBrief
    salary_from: int
    salary_to: int
    message: str | None = None
    below_candidate_min: bool
    match_snapshot: MatchSnapshot | None = None
    decline: Decline | None = None
    awaiting_reply_from: str | None = None


class CompanyBrief(BaseModel):
    id: uuid.UUID
    name: str
    logo_url: str | None = None
    responsibility_score: float | None = None
    verified: bool


class OfferForCandidate(OfferOut):
    company: CompanyBrief


class OfferForCompany(OfferOut):
    candidate: CandidateCard | None = None


async def _base(session: AsyncSession, o: Offer) -> dict[str, Any]:
    v = await vacancies.get(session, o.vacancy_id)
    snap = o.match_snapshot
    return {
        "id": o.id, "status": o.status, "created_at": o.created_at, "expires_at": o.expires_at,
        "vacancy": VacancyBrief.model_validate(v, from_attributes=True),
        "salary_from": o.salary_from, "salary_to": o.salary_to, "message": o.message,
        "below_candidate_min": o.below_candidate_min,
        "match_snapshot": MatchSnapshot.model_validate(snap) if snap else None,
        "decline": Decline(reason=o.decline_reason, comment=o.decline_comment)
        if o.decline_reason else None,
        "awaiting_reply_from": o.awaiting_reply_from,
    }  # fmt: skip


async def for_candidate(session: AsyncSession, o: Offer) -> OfferForCandidate:
    c = await companies.get_company(session, o.company_id)
    brief = CompanyBrief(
        id=c.id, name=c.name, responsibility_score=c.responsibility_score,
        verified=c.status == "verified",
    )  # fmt: skip
    return OfferForCandidate(**await _base(session, o), company=brief)


async def for_company(session: AsyncSession, o: Offer) -> OfferForCompany:
    cand = None
    if o.candidate_id is not None:
        c = await candidates.get(session, o.candidate_id)
        if c is not None:
            full = await card.build_card(session, c, vacancy_id=None, cfg=_CFG, trust=_TRUST)
            cand = CandidateCard.model_validate(full.model_dump())
    return OfferForCompany(**await _base(session, o), candidate=cand)


@router.post("/offers", response_model=OfferForCompany, status_code=201)
async def create_offer(
    body: CreateOffer,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    if not idempotency_key or not idempotency_key.strip():
        raise ProblemError(422, "idempotency_key_required", "Нужен заголовок Idempotency-Key")
    company, _ = await companies.require_company(session, user.id)
    vacancy = await vacancies.get_owned(session, user, body.vacancy_id)
    cand = await card.get_visible(session, body.candidate_pseudo_id, company.id)
    if cand is None:
        raise ProblemError(404, "candidate_not_found", "Кандидат не найден")
    offer, replay = await service.create(
        session, company=company, user_id=user.id, vacancy=vacancy, candidate=cand,
        salary_from=body.salary_from, salary_to=body.salary_to, message=body.message,
        idempotency_key=idempotency_key.strip(), limits=_LIMITS,
    )  # fmt: skip
    if replay:
        response.headers["Idempotent-Replay"] = "true"
    return await for_company(session, offer)


@router.get("/offers", response_model=list[OfferForCompany])
async def list_offers(
    status: OfferStatus | None = None,
    vacancy_id: uuid.UUID | None = None,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    company, _ = await companies.require_company(session, user.id)
    rows = await service.list_for_company(
        session, company.id, status=status.value if status else None, vacancy_id=vacancy_id
    )
    return [await for_company(session, o) for o in rows]


@router.get("/candidates/me/offers", response_model=list[OfferForCandidate])
async def my_offers(
    user: User = Depends(_candidate), session: AsyncSession = Depends(get_session)
) -> Any:
    return [
        await for_candidate(session, o) for o in await service.list_for_candidate(session, user.id)
    ]


@router.get("/offers/{offer_id}", response_model=OfferForCandidate | OfferForCompany)
async def get_offer(
    offer_id: uuid.UUID,
    user: User = Depends(_both),
    session: AsyncSession = Depends(get_session),
) -> Any:
    if user.role == "candidate":
        offer = await service.get_for_candidate(session, user.id, offer_id, lock=True)
        await service.mark_viewed(session, offer)
        return await for_candidate(session, offer)
    company, _ = await companies.require_company(session, user.id)
    offer = await service.get_for_company(session, company.id, offer_id)
    return await for_company(session, offer)


@router.post("/offers/{offer_id}/accept", response_model=OfferForCandidate)
async def accept_offer(
    offer_id: uuid.UUID, user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
) -> Any:  # fmt: skip
    offer = await service.get_for_candidate(session, user.id, offer_id, lock=True)
    await service.accept(session, offer)
    return await for_candidate(session, offer)


@router.post("/offers/{offer_id}/decline", response_model=OfferForCandidate)
async def decline_offer(
    offer_id: uuid.UUID, body: DeclineIn, user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
) -> Any:  # fmt: skip
    offer = await service.get_for_candidate(session, user.id, offer_id, lock=True)
    await service.decline(session, offer, body.reason, body.comment)
    return await for_candidate(session, offer)


@router.post("/offers/{offer_id}/withdraw", response_model=OfferForCompany)
async def withdraw_offer(
    offer_id: uuid.UUID, user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:  # fmt: skip
    company, _ = await companies.require_company(session, user.id)
    offer = await service.get_for_company(session, company.id, offer_id, lock=True)
    await service.withdraw(session, offer)
    return await for_company(session, offer)


@router.post("/offers/{offer_id}/status", response_model=OfferForCompany)
async def set_offer_status(
    offer_id: uuid.UUID, body: StatusIn, user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:  # fmt: skip
    company, _ = await companies.require_company(session, user.id)
    offer = await service.get_for_company(session, company.id, offer_id, lock=True)
    await service.set_status(session, offer, body.status)
    return await for_company(session, offer)
