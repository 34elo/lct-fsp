"""Офферы (api.md §2.5): создание с `Idempotency-Key`, чтение, ответы, действия компании."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, Header, Response
from fsp_contracts.enums import (
    DeclineReason,
    EmploymentType,
    Grade,
    OfferStatus,
    RoleSlug,
    WorkFormat,
)
from fsp_contracts.hiring import ContactMethod, OfferInitiator
from fsp_contracts.ml import ExplanationItem
from fsp_platform.app import ProblemError
from fsp_platform.ratelimit import RateLimiter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service as candidates
from app.companies import service as companies
from app.deps import get_limiter, get_session
from app.graph.trust import TrustConfig
from app.identity import service as identity
from app.identity.deps import require_roles
from app.identity.models import User
from app.matching import card
from app.matching.p_accept import PAcceptConfig, p_accept
from app.matching.p_accept import hint as p_hint
from app.matching.scoring import MatchConfig
from app.matching.search import CandidateCard
from app.offers import service
from app.offers.models import Offer, OfferMessage
from app.openapi_errors import problem_responses
from app.telegram import service as telegram
from app.vacancies import service as vacancies

router = APIRouter(tags=["offers"])
admin_router = APIRouter(prefix="/admin/complaints", tags=["admin"])
log = structlog.get_logger()

_employer = require_roles("employer")
_candidate = require_roles("candidate")
_admin = require_roles("fsp_admin")
_both = require_roles("employer", "candidate")
_LIMITS = service.OfferLimits.load()
_CFG = MatchConfig.load()
_TRUST = TrustConfig.load()
_PACCEPT = PAcceptConfig.load()


class CreateOffer(BaseModel):
    """Приглашение работодателя. Без `vacancy_id` (ADR-022) обязателен `title`."""

    model_config = ConfigDict(extra="forbid")

    vacancy_id: uuid.UUID | None = None
    candidate_pseudo_id: str = Field(min_length=1, max_length=64)
    # обязательны по смыслу; отсутствие даёт 422 `salary_range_required`, а не общую ошибку схемы
    salary_from: int | None = Field(default=None, le=100_000_000)
    salary_to: int | None = Field(default=None, le=100_000_000)
    message: str | None = Field(default=None, max_length=2000)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    contact_method: ContactMethod | None = None


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
    vacancy: VacancyBrief | None = None  # пусто у приглашения без вакансии (ADR-022)
    title: str | None = None
    description: str | None = None
    contact_method: ContactMethod | None = None
    initiator: OfferInitiator = OfferInitiator.employer
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


class Contacts(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    telegram: str | None = None


class OfferForCompany(OfferOut):
    candidate: CandidateCard | None = None
    contacts: Contacts | None = None  # только после accepted, см. GET /offers/{id}/contacts


class SalaryHintIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vacancy_id: uuid.UUID
    candidate_pseudo_id: str = Field(min_length=1, max_length=64)
    salary_from: int | None = Field(default=None, le=100_000_000)
    salary_to: int | None = Field(default=None, le=100_000_000)


class SalaryHint(BaseModel):
    candidate_min: int | None = None
    below_candidate_min: bool
    category_median: int | None = None
    vs_category_median: float = 0.0
    p_accept: float
    acceptance_hint: str  # low | medium | high
    range_too_wide: bool
    message: str


class OfferEventOut(BaseModel):
    id: int
    from_status: str | None = None
    to_status: str
    actor: str  # candidate | company | system
    created_at: datetime


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    id: uuid.UUID
    author_side: str
    text: str
    created_at: datetime
    channel: str | None = None


class ComplaintIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=40)
    comment: str | None = Field(default=None, max_length=2000)


class ComplaintOut(BaseModel):
    id: uuid.UUID
    offer_id: uuid.UUID
    reason: str
    status: str
    created_at: datetime


class AdminComplaintOut(BaseModel):
    """Жалоба для админа: без данных жалобщика (кандидат анонимен для компании и логов)."""

    id: uuid.UUID
    offer_id: uuid.UUID
    company_id: uuid.UUID
    company_name: str | None
    reason: str
    comment: str | None
    status: str
    created_at: datetime


class ResolveComplaintIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["resolved", "dismissed"] = "resolved"


def _admin_complaint(row: Any, offer: Offer, company: Any) -> AdminComplaintOut:
    return AdminComplaintOut(
        id=row.id, offer_id=offer.id, company_id=offer.company_id,
        company_name=company.name if company else None, reason=row.reason,
        comment=row.comment, status=row.status, created_at=row.created_at,
    )  # fmt: skip


async def _base(session: AsyncSession, o: Offer) -> dict[str, Any]:
    v = await vacancies.get(session, o.vacancy_id) if o.vacancy_id else None
    snap = o.match_snapshot
    return {
        "id": o.id, "status": o.status, "created_at": o.created_at, "expires_at": o.expires_at,
        "vacancy": VacancyBrief.model_validate(v, from_attributes=True) if v else None,
        "title": o.title or (v.title if v else None), "description": o.description,
        "contact_method": o.contact_method, "initiator": o.initiator,
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


@router.post(
    "/offers/salary-hint",
    response_model=SalaryHint,
    responses=problem_responses(401, 403, 404, 422),
)
async def salary_hint(
    body: SalaryHintIn,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Подсказка по вилке до отправки: `p_accept`, «ниже ожиданий», «слишком широкая»."""
    company, _ = await companies.require_company(session, user.id)
    vacancy = await vacancies.get_owned(session, user, body.vacancy_id)
    cand = await card.get_visible(session, body.candidate_pseudo_id, company.id)
    if cand is None:
        raise ProblemError(404, "candidate_not_found", "Кандидат не найден")
    lo, hi = service.validate_range(body.salary_from, body.salary_to)
    slugs = [slug for _, slug in (await vacancies.skills_of(session, [vacancy.id]))[vacancy.id]]
    p = p_accept(
        salary_to=hi, salary_min=cand.salary_min, vacancy_formats=vacancy.formats,
        candidate_formats=cand.formats or (), vacancy_skills=slugs,
        primary_stack=cand.primary_stack or (), responsibility_score=company.responsibility_score,
        active=cand.search_status == "active", cfg=_PACCEPT,
    )  # fmt: skip
    below = cand.salary_min is not None and hi < cand.salary_min
    median = await candidates.category_median(session, cand.primary_role, cand.grade)
    wide = vacancies.range_too_wide(lo, hi)
    notes = []
    if below:
        notes.append("Верх вилки ниже ожиданий кандидата.")
    if wide:
        notes.append("Вилка слишком широкая: сузьте её, так оффер выглядит честнее.")
    return SalaryHint(
        candidate_min=cand.salary_min, below_candidate_min=below, category_median=median,
        vs_category_median=round(hi / median - 1, 3) if median else 0.0, p_accept=round(p, 3),
        acceptance_hint=p_hint(p, _PACCEPT), range_too_wide=wide, message=" ".join(notes),
    )  # fmt: skip


@router.post(
    "/offers",
    response_model=OfferForCompany,
    status_code=201,
    responses=problem_responses(401, 403, 404, 409, 422, 429),
)
async def create_offer(
    body: CreateOffer,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    if not idempotency_key or not idempotency_key.strip():
        raise ProblemError(422, "idempotency_key_required", "Нужен заголовок Idempotency-Key")
    identity.require_verified_email(user)  # blocks.md §4.6
    company, _ = await companies.require_company(session, user.id)
    vacancy = await vacancies.get_owned(session, user, body.vacancy_id) if body.vacancy_id else None
    cand = await card.get_visible(session, body.candidate_pseudo_id, company.id)
    if cand is None:
        raise ProblemError(404, "candidate_not_found", "Кандидат не найден")
    offer, replay = await service.create(
        session, company=company, user_id=user.id, vacancy=vacancy, candidate=cand,
        salary_from=body.salary_from, salary_to=body.salary_to, message=body.message,
        idempotency_key=idempotency_key.strip(), limits=_LIMITS, title=body.title,
        description=body.description, contact_method=body.contact_method,
    )  # fmt: skip
    if replay:
        response.headers["Idempotent-Replay"] = "true"
    return await for_company(session, offer)


@router.get("/offers", response_model=list[OfferForCompany], responses=problem_responses(401, 403))
async def list_offers(
    status: OfferStatus | None = None,
    vacancy_id: uuid.UUID | None = None,
    initiator: OfferInitiator | None = None,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Офферы компании; `initiator=candidate` - отклики на её вакансии."""
    company, _ = await companies.require_company(session, user.id)
    rows = await service.list_for_company(
        session,
        company.id,
        status=status.value if status else None,
        vacancy_id=vacancy_id,
        initiator=initiator.value if initiator else None,
    )
    return [await for_company(session, o) for o in rows]


@router.get(
    "/candidates/me/offers",
    response_model=list[OfferForCandidate],
    responses=problem_responses(401, 403),
)
async def my_offers(
    initiator: OfferInitiator | None = None,
    user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
) -> Any:
    rows = await service.list_for_candidate(
        session, user.id, initiator=initiator.value if initiator else None
    )
    return [await for_candidate(session, o) for o in rows]


@router.get(
    "/candidates/me/applications",
    response_model=list[OfferForCandidate],
    responses=problem_responses(401, 403),
)
async def my_applications(
    user: User = Depends(_candidate), session: AsyncSession = Depends(get_session)
) -> Any:
    """Мои отклики на вакансии (`initiator = candidate`) со статусами."""
    rows = await service.list_for_candidate(
        session, user.id, initiator=OfferInitiator.candidate.value
    )
    return [await for_candidate(session, o) for o in rows]


@router.post(
    "/candidates/me/applications/{offer_id}/withdraw",
    response_model=OfferForCandidate,
    responses=problem_responses(401, 403, 404, 409),
)
async def withdraw_application(
    offer_id: uuid.UUID, user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
) -> Any:  # fmt: skip
    offer = await service.get_for_candidate(session, user.id, offer_id, lock=True)
    await service.withdraw_application(session, offer)
    return await for_candidate(session, offer)


@router.get(
    "/offers/{offer_id}",
    response_model=OfferForCandidate | OfferForCompany,
    responses=problem_responses(401, 403, 404),
)
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
    offer = await service.get_for_company(session, company.id, offer_id, lock=True)
    await service.mark_viewed_by_company(session, offer)  # отклик: sent -> viewed
    out = await for_company(session, offer)
    if await service.is_revealed(session, offer):
        out.contacts = await _contacts(session, offer, user)
    return out


@router.post(
    "/offers/{offer_id}/accept",
    response_model=OfferForCandidate,
    responses=problem_responses(401, 403, 404),
)
async def accept_offer(
    offer_id: uuid.UUID, user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
) -> Any:  # fmt: skip
    offer = await service.get_for_candidate(session, user.id, offer_id, lock=True)
    await service.accept(session, offer)
    return await for_candidate(session, offer)


@router.post(
    "/offers/{offer_id}/decline",
    response_model=OfferForCandidate,
    responses=problem_responses(401, 403, 404, 422),
)
async def decline_offer(
    offer_id: uuid.UUID, body: DeclineIn, user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
) -> Any:  # fmt: skip
    offer = await service.get_for_candidate(session, user.id, offer_id, lock=True)
    await service.decline(session, offer, body.reason, body.comment)
    return await for_candidate(session, offer)


@router.post(
    "/offers/{offer_id}/withdraw",
    response_model=OfferForCompany,
    responses=problem_responses(401, 403, 404),
)
async def withdraw_offer(
    offer_id: uuid.UUID, user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:  # fmt: skip
    company, _ = await companies.require_company(session, user.id)
    offer = await service.get_for_company(session, company.id, offer_id, lock=True)
    await service.withdraw(session, offer)
    return await for_company(session, offer)


@router.post(
    "/offers/{offer_id}/status",
    response_model=OfferForCompany,
    responses=problem_responses(401, 403, 404, 422),
)
async def set_offer_status(
    offer_id: uuid.UUID, body: StatusIn, user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:  # fmt: skip
    company, _ = await companies.require_company(session, user.id)
    offer = await service.get_for_company(session, company.id, offer_id, lock=True)
    await service.set_status(session, offer, body.status)
    return await for_company(session, offer)


async def _contacts(session: AsyncSession, offer: Offer, viewer: User) -> Contacts:
    """Контакты кандидата. Источник пока — учётная запись и привязанный Telegram (анкета не хранит
    `full_name_enc`/`contacts_enc`), имя — псевдоним. Аудит без ПДн: кто, какой оффер."""
    assert offer.candidate_id is not None
    cand = await candidates.get(session, offer.candidate_id)
    u = await session.get(User, offer.candidate_id)
    tg = await telegram.account_of_user(session, offer.candidate_id)
    log.info("contacts.viewed", offer_id=str(offer.id), company_id=str(offer.company_id),
             viewer_user_id=str(viewer.id))  # fmt: skip
    return Contacts(
        name=cand.pseudonym if cand else "Кандидат",
        email=u.email if u else None,
        telegram=f"@{tg.username}" if tg and tg.username else None,
    )


@router.get(
    "/offers/{offer_id}/contacts",
    response_model=Contacts,
    responses=problem_responses(401, 403, 404),
)
async def offer_contacts(
    offer_id: uuid.UUID, user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:  # fmt: skip
    company, _ = await companies.require_company(session, user.id)
    offer = await service.get_for_company(session, company.id, offer_id)
    await service.require_revealed(session, offer)
    return await _contacts(session, offer, user)


async def _side_offer(
    session: AsyncSession, user: User, offer_id: uuid.UUID, *, lock: bool = False
) -> tuple[Offer, str]:  # fmt: skip
    if user.role == "candidate":
        return await service.get_for_candidate(session, user.id, offer_id, lock=lock), "candidate"
    company, _ = await companies.require_company(session, user.id)
    return await service.get_for_company(session, company.id, offer_id, lock=lock), "company"


def _msg(m: OfferMessage) -> MessageOut:
    return MessageOut.model_validate(m, from_attributes=True)


@router.get(
    "/offers/{offer_id}/events",
    response_model=list[OfferEventOut],
    responses=problem_responses(401, 403, 404),
)
async def list_events(
    offer_id: uuid.UUID, user: User = Depends(_both), session: AsyncSession = Depends(get_session)
) -> Any:
    offer, _ = await _side_offer(session, user, offer_id)
    return [
        OfferEventOut.model_validate(e, from_attributes=True)
        for e in await service.list_events(session, offer)
    ]


@router.get(
    "/offers/{offer_id}/messages",
    response_model=list[MessageOut],
    responses=problem_responses(401, 403, 404),
)
async def list_messages(
    offer_id: uuid.UUID, user: User = Depends(_both), session: AsyncSession = Depends(get_session)
) -> Any:
    offer, _ = await _side_offer(session, user, offer_id)
    return [_msg(m) for m in await service.list_messages(session, offer)]


@router.post(
    "/offers/{offer_id}/messages",
    response_model=MessageOut,
    status_code=201,
    responses=problem_responses(401, 403, 404, 429),
)
async def post_message(
    offer_id: uuid.UUID, body: MessageIn, user: User = Depends(_both),
    session: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_limiter),
) -> Any:  # fmt: skip
    offer, side = await _side_offer(session, user, offer_id, lock=True)
    await limiter.check(f"offer_msg:{offer.id}:{user.id}", service.MESSAGES_PER_HOUR, 3600)
    return _msg(
        await service.add_message(session, offer, side=side, user_id=user.id, text=body.text)
    )


@router.post(
    "/offers/{offer_id}/complaint",
    response_model=ComplaintOut,
    status_code=201,
    responses=problem_responses(401, 403, 404),
)
async def complain(
    offer_id: uuid.UUID, body: ComplaintIn, user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
) -> Any:  # fmt: skip
    offer = await service.get_for_candidate(session, user.id, offer_id)
    row = await service.add_complaint(
        session, offer, user_id=user.id, reason=body.reason, comment=body.comment
    )
    return ComplaintOut.model_validate(row, from_attributes=True)


@admin_router.get(
    "", response_model=list[AdminComplaintOut], responses=problem_responses(401, 403, 422)
)
async def admin_complaints(
    status: Literal["open", "resolved", "dismissed"] | None = None,
    _: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
) -> Any:
    rows = await service.list_complaints(session, status)
    return [_admin_complaint(*r) for r in rows]


@admin_router.post(
    "/{complaint_id}/resolve",
    response_model=AdminComplaintOut,
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def admin_resolve_complaint(
    complaint_id: uuid.UUID,
    body: ResolveComplaintIn | None = None,
    _: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
) -> Any:
    decision = (body or ResolveComplaintIn()).decision
    return _admin_complaint(*await service.resolve_complaint(session, complaint_id, decision))
