"""Офферы (api.md §2.5): создание с `Idempotency-Key`, чтение, ответы, действия компании."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, Header, Query, Response
from fsp_contracts.enums import (
    DeclineReason,
    EmploymentType,
    Grade,
    OfferStatus,
    RoleSlug,
    WorkFormat,
)
from fsp_contracts.hiring import ContactMethod, OfferInitiator, SalaryBasis
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
from app.matching.p_accept import PAcceptConfig, p_accept, suggest_raise
from app.matching.p_accept import hint as p_hint
from app.matching.scoring import MatchConfig
from app.matching.search import CandidateCard
from app.offers import service, teams, why
from app.offers.models import ContactReveal, Offer, OfferMessage
from app.openapi_errors import problem_responses
from app.telegram import service as telegram
from app.vacancies import service as vacancies
from app.vacancies.service import VacancyConfig

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
_VACANCY_CFG = VacancyConfig.load()


class CreateOffer(BaseModel):
    """Приглашение работодателя. Без `vacancy_id` (ADR-022) обязателен `title`."""

    model_config = ConfigDict(extra="forbid")

    vacancy_id: uuid.UUID | None = None
    candidate_pseudo_id: str = Field(min_length=1, max_length=64)
    # обязательны по смыслу; отсутствие даёт 422 `salary_range_required`, а не общую ошибку схемы
    salary_from: int | None = Field(default=None, le=100_000_000)
    salary_to: int | None = Field(default=None, le=100_000_000)
    salary_basis: SalaryBasis | None = None  # пусто: из вакансии, иначе gross
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
    team_offer_id: uuid.UUID | None = None  # общий у офферов одной команды (E15-2)
    salary_from: int
    salary_to: int
    salary_basis: SalaryBasis = SalaryBasis.gross
    contacts_revoked_at: datetime | None = None  # кандидат отозвал доступ к контактам
    message: str | None = None
    below_candidate_min: bool
    match_snapshot: MatchSnapshot | None = None
    decline: Decline | None = None
    awaiting_reply_from: str | None = None
    # E33-1 (ADR-026): оффер начался с интереса; кандидат открыл; компания пригласила
    interest_at: datetime | None = None
    interest_opened_at: datetime | None = None
    invited_at: datetime | None = None


class CompanyBrief(BaseModel):
    id: uuid.UUID
    name: str
    logo_url: str | None = None
    responsibility_score: float | None = None
    verified: bool
    reliability: why.CompanyReliability | None = None  # E33-2: доля ответов, срок ответа


class OfferForCandidate(OfferOut):
    company: CompanyBrief
    why_you: why.WhyYou | None = None  # E33-2: только у интереса и приглашения компании


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

    vacancy_id: uuid.UUID | None = None  # интерес без вакансии (E33-5): формат и навыки неизвестны
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
    suggested_salary_to: int | None = None  # верх вилки, при котором p_accept ≥ порога high
    suggested_p_accept: float | None = None
    avg_response_hours: float | None = None  # средний срок ответа кандидатов категории
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
    reveal = await session.get(ContactReveal, o.id)
    snap = o.match_snapshot
    return {
        "id": o.id, "status": o.status, "created_at": o.created_at, "expires_at": o.expires_at,
        "vacancy": VacancyBrief.model_validate(v, from_attributes=True) if v else None,
        "title": o.title or (v.title if v else None), "description": o.description,
        "contact_method": o.contact_method, "initiator": o.initiator,
        "team_offer_id": o.team_offer_id,
        "salary_from": o.salary_from, "salary_to": o.salary_to, "salary_basis": o.salary_basis,
        "contacts_revoked_at": reveal.revoked_at if reveal else None, "message": o.message,
        "below_candidate_min": o.below_candidate_min,
        "match_snapshot": MatchSnapshot.model_validate(snap) if snap else None,
        "decline": Decline(reason=o.decline_reason, comment=o.decline_comment)
        if o.decline_reason else None,
        "awaiting_reply_from": o.awaiting_reply_from,
        "interest_at": o.interest_at, "interest_opened_at": o.interest_opened_at,
        "invited_at": o.invited_at,
    }  # fmt: skip


async def for_candidate(session: AsyncSession, o: Offer) -> OfferForCandidate:
    c = await companies.get_company(session, o.company_id)
    brief = CompanyBrief(
        id=c.id, name=c.name, responsibility_score=c.responsibility_score,
        verified=companies.badge_visible(c),
        reliability=await why.company_reliability(session, c.id, c.responsibility_score),
    )  # fmt: skip
    cand = await candidates.get(session, o.candidate_id) if o.candidate_id else None
    reasons = (
        await why.why_you(session, o, cand)
        if cand is not None and o.initiator == OfferInitiator.employer.value
        else None
    )
    return OfferForCandidate(**await _base(session, o), company=brief, why_you=reasons)


async def for_company(session: AsyncSession, o: Offer) -> OfferForCompany:
    cand = None
    if o.candidate_id is not None:
        c = await candidates.get(session, o.candidate_id)
        if c is not None:
            full = await card.build_card(session, c, vacancy_id=None, cfg=_CFG, trust=_TRUST)
            cand = CandidateCard.model_validate(full.model_dump())
    return OfferForCompany(**await _base(session, o), candidate=cand)


class TeamMemberOut(BaseModel):
    """Участник команды: только псевдоним, без ПДн."""

    pseudo_id: str
    role: str | None = None
    primary_role: str | None = None
    grade: str | None = None


class TeamOut(BaseModel):
    id: str
    name: str | None = None
    competition_title: str | None = None
    discipline: str | None = None
    best_place: int | None = None
    members: list[TeamMemberOut]


class SalaryPerMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_pseudo_id: str = Field(min_length=1, max_length=64)
    salary_from: int | None = Field(default=None, le=100_000_000)
    salary_to: int | None = Field(default=None, le=100_000_000)


class CreateTeamOffer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vacancy_id: uuid.UUID
    fsp_team_id: str = Field(min_length=1, max_length=128)
    salary_per_member: list[SalaryPerMember] = Field(min_length=1, max_length=20)
    message: str | None = Field(default=None, max_length=2000)


class TeamOfferOut(BaseModel):
    team_offer_id: uuid.UUID
    fsp_team_id: str
    team_name: str | None = None
    offers: list[OfferForCompany]


def _team_out(t: teams.TeamView) -> TeamOut:
    return TeamOut(
        id=t.id, name=t.name, competition_title=t.competition_title, discipline=t.discipline,
        best_place=t.best_place,
        members=[
            TeamMemberOut(
                pseudo_id=m.candidate.pseudo_id, role=m.role,
                primary_role=m.candidate.primary_role, grade=m.candidate.grade,
            )
            for m in t.members
        ],
    )  # fmt: skip


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
    vacancy = await vacancies.get_owned(session, user, body.vacancy_id) if body.vacancy_id else None
    cand = await card.get_visible(session, body.candidate_pseudo_id, company.id)
    if cand is None:
        raise ProblemError(404, "candidate_not_found", "Кандидат не найден")
    lo, hi = service.validate_range(body.salary_from, body.salary_to)
    slugs = (
        [slug for _, slug in (await vacancies.skills_of(session, [vacancy.id]))[vacancy.id]]
        if vacancy
        else []
    )

    def _p(to: int) -> float:
        return p_accept(
            salary_to=to, salary_min=cand.salary_min,
            vacancy_formats=vacancy.formats if vacancy else (),
            candidate_formats=cand.formats or (), vacancy_skills=slugs,
            primary_stack=cand.primary_stack or (),
            responsibility_score=company.responsibility_score,
            active=cand.search_status == "active", cfg=_PACCEPT,
        )  # fmt: skip

    p = _p(hi)
    raised = suggest_raise(hi, p, _p, _PACCEPT)
    resp_hours = await service.avg_response_hours(
        session, cand.primary_role, _PACCEPT.response_min_sample
    )
    below = cand.salary_min is not None and hi < cand.salary_min
    median = await candidates.category_median(session, cand.primary_role, cand.grade)
    wide = vacancies.range_too_wide(lo, hi, _VACANCY_CFG)
    notes = []
    if below:
        notes.append("Верх вилки ниже ожиданий кандидата.")
    if wide:
        notes.append("Вилка слишком широкая: сузьте её, так оффер выглядит честнее.")
    return SalaryHint(
        candidate_min=cand.salary_min, below_candidate_min=below, category_median=median,
        vs_category_median=round(hi / median - 1, 3) if median else 0.0, p_accept=round(p, 3),
        acceptance_hint=p_hint(p, _PACCEPT), range_too_wide=wide,
        suggested_salary_to=raised[0] if raised else None,
        suggested_p_accept=round(raised[1], 3) if raised else None,
        avg_response_hours=resp_hours, message=" ".join(notes),
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
        salary_basis=body.salary_basis,
    )  # fmt: skip
    if replay:
        response.headers["Idempotent-Replay"] = "true"
    return await for_company(session, offer)


# --- интерес до приглашения (E33-1, ADR-026) -------------------------------------------


class CreateInterest(BaseModel):
    """Отметка «интересен»: вилка обязательна, сообщение до 300 символов, вакансия — по желанию."""

    model_config = ConfigDict(extra="forbid")

    candidate_pseudo_id: str = Field(min_length=1, max_length=64)
    salary_from: int | None = Field(default=None, le=100_000_000)
    salary_to: int | None = Field(default=None, le=100_000_000)
    salary_basis: SalaryBasis | None = None
    message: str | None = Field(default=None, max_length=service.INTEREST_MESSAGE_MAX)
    vacancy_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=200)


class InviteFromInterest(BaseModel):
    """Приглашение по открытому интересу; пустые поля берутся из интереса."""

    model_config = ConfigDict(extra="forbid")

    salary_from: int | None = Field(default=None, le=100_000_000)
    salary_to: int | None = Field(default=None, le=100_000_000)
    message: str | None = Field(default=None, max_length=2000)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    contact_method: ContactMethod | None = None


class InterestsSummary(BaseModel):
    """«K компаний интересуются вами, вилки …» и карточки без контактов."""

    companies: int
    salary_from_min: int | None = None
    salary_to_max: int | None = None
    items: list[OfferForCandidate]


@router.post(
    "/interests",
    response_model=OfferForCompany,
    status_code=201,
    responses=problem_responses(401, 403, 404, 409, 422, 429),
)
async def create_interest(
    body: CreateInterest,
    response: Response,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Интерес к анонимному кандидату. Повтор отметки возвращает открытый интерес."""
    identity.require_verified_email(user)  # blocks.md §4.6
    company, _ = await companies.require_company(session, user.id)
    vacancy = await vacancies.get_owned(session, user, body.vacancy_id) if body.vacancy_id else None
    cand = await card.get_visible(session, body.candidate_pseudo_id, company.id)
    if cand is None:
        raise ProblemError(404, "candidate_not_found", "Кандидат не найден")
    offer, replay = await service.create_interest(
        session, company=company, user_id=user.id, candidate=cand, vacancy=vacancy,
        salary_from=body.salary_from, salary_to=body.salary_to, message=body.message,
        title=body.title, salary_basis=body.salary_basis, limits=_LIMITS,
    )  # fmt: skip
    if replay:
        response.headers["Idempotent-Replay"] = "true"
    return await for_company(session, offer)


@router.post(
    "/interests/{offer_id}/invite",
    response_model=OfferForCompany,
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def invite_from_interest(
    offer_id: uuid.UUID,
    body: InviteFromInterest | None = None,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Кандидат открыл интерес → приглашение (`interest_opened → sent`)."""
    company, _ = await companies.require_company(session, user.id)
    offer = await _interest_for_company(session, company.id, offer_id)
    b = body or InviteFromInterest()
    await service.invite_from_interest(
        session, offer, limits=_LIMITS, title=b.title, description=b.description,
        contact_method=b.contact_method, message=b.message, salary_from=b.salary_from,
        salary_to=b.salary_to,
    )  # fmt: skip
    return await for_company(session, offer)


@router.get(
    "/candidates/me/interests",
    response_model=InterestsSummary,
    responses=problem_responses(401, 403),
)
async def my_interests(
    user: User = Depends(_candidate), session: AsyncSession = Depends(get_session)
) -> Any:
    rows = await service.interests_for(session, user.id)
    return InterestsSummary(
        companies=len({o.company_id for o in rows}),
        salary_from_min=min((o.salary_from for o in rows), default=None),
        salary_to_max=max((o.salary_to for o in rows), default=None),
        items=[await for_candidate(session, o) for o in rows],
    )


@router.post(
    "/interests/{offer_id}/open",
    response_model=OfferForCandidate,
    responses=problem_responses(401, 403, 404, 409),
)
async def open_interest(
    offer_id: uuid.UUID, user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
) -> Any:  # fmt: skip
    """«Открыть»: компания получает уведомление и может отправить приглашение. Повтор — no-op."""
    offer = await _interest_for_candidate(session, user.id, offer_id)
    await service.open_interest(session, offer)
    return await for_candidate(session, offer)


@router.post(
    "/interests/{offer_id}/decline",
    response_model=OfferForCandidate,
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def decline_interest(
    offer_id: uuid.UUID, body: DeclineIn, user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
) -> Any:  # fmt: skip
    """«Не интересно» с причиной (вилка, формат, компания, не ищу). Повтор — no-op."""
    offer = await _interest_for_candidate(session, user.id, offer_id)
    await service.decline_interest(session, offer, body.reason, body.comment)
    return await for_candidate(session, offer)


async def _interest_for_candidate(
    session: AsyncSession, candidate_id: uuid.UUID, offer_id: uuid.UUID
) -> Offer:
    try:
        offer = await service.get_for_candidate(session, candidate_id, offer_id, lock=True)
    except ProblemError:
        raise service.interest_not_found() from None
    if offer.interest_at is None:
        raise service.interest_not_found()
    return offer


async def _interest_for_company(
    session: AsyncSession, company_id: uuid.UUID, offer_id: uuid.UUID
) -> Offer:
    try:
        offer = await service.get_for_company(session, company_id, offer_id, lock=True)
    except ProblemError:
        raise service.interest_not_found() from None
    if offer.interest_at is None:
        raise service.interest_not_found()
    return offer


@router.get("/teams", response_model=list[TeamOut], responses=problem_responses(401, 403))
async def list_fsp_teams(
    discipline: str | None = Query(default=None, max_length=64),
    min_place: int | None = Query(default=None, ge=1),
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Команды ФСП, где есть минимум два видимых кандидата платформы (анонимно, E15-2)."""
    company, _ = await companies.require_company(session, user.id)
    found = await teams.list_teams(session, company.id, discipline=discipline, min_place=min_place)
    return [_team_out(t) for t in found]


@router.post(
    "/team-offers",
    response_model=TeamOfferOut,
    status_code=201,
    responses=problem_responses(401, 403, 404, 409, 422, 429),
)
async def create_team_offer(
    body: CreateTeamOffer,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=100),
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Командный оффер: по офферу на участника с общим `team_offer_id`, вилка у каждого своя."""
    if not idempotency_key or not idempotency_key.strip():
        raise ProblemError(422, "idempotency_key_required", "Нужен заголовок Idempotency-Key")
    identity.require_verified_email(user)  # blocks.md §4.6
    company, _ = await companies.require_company(session, user.id)
    vacancy = await vacancies.get_owned(session, user, body.vacancy_id)
    team = await teams.get_team(session, company.id, body.fsp_team_id)
    pseudo = [m.candidate_pseudo_id for m in body.salary_per_member]
    if len(set(pseudo)) != len(pseudo) or len(pseudo) < teams.MIN_TEAM:
        raise ProblemError(
            422, "team_members_invalid", "Нужно минимум два разных участника команды"
        )
    key = idempotency_key.strip()
    by_pseudo = {pid: teams.member_by_pseudo(team, pid) for pid in pseudo}
    existing = await service.find_by_key(session, company.id, f"{key}#{pseudo[0]}")
    tid = existing.team_offer_id if existing and existing.team_offer_id else uuid.uuid4()
    description = f"Командный оффер: команда «{team.name or team.id}»"
    created: list[Offer] = []
    replays = []
    async with session.begin_nested():  # ошибка на любом участнике откатывает все офферы
        for item in body.salary_per_member:
            offer, replay = await service.create(
                session, company=company, user_id=user.id, vacancy=vacancy,
                candidate=by_pseudo[item.candidate_pseudo_id], salary_from=item.salary_from,
                salary_to=item.salary_to, message=body.message,
                idempotency_key=f"{key}#{item.candidate_pseudo_id}", limits=_LIMITS,
                description=description, team_offer_id=tid,
            )  # fmt: skip
            created.append(offer)
            replays.append(replay)
    if all(replays):
        response.headers["Idempotent-Replay"] = "true"
    return TeamOfferOut(
        team_offer_id=tid, fsp_team_id=team.id, team_name=team.name,
        offers=[await for_company(session, o) for o in created],
    )  # fmt: skip


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


@router.post(
    "/offers/{offer_id}/contacts/revoke",
    response_model=OfferForCandidate,
    responses=problem_responses(401, 403, 404, 409),
)
async def revoke_contacts(
    offer_id: uuid.UUID, user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
) -> Any:  # fmt: skip
    """Отзыв доступа к контактам: компания перестаёт их видеть (E32-5a). Повтор — no-op."""
    offer = await service.get_for_candidate(session, user.id, offer_id, lock=True)
    await service.revoke_contacts(session, offer)
    return await for_candidate(session, offer)


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
