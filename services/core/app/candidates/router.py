from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fsp_contracts.enums import ConsentType, EmploymentType, SearchStatus, WorkFormat
from fsp_platform.app import ProblemError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service
from app.candidates.models import Candidate
from app.consents import service as consents
from app.consents.deps import require_consent
from app.deps import get_session
from app.graph.trust import TrustConfig
from app.identity.deps import require_roles
from app.identity.models import User
from app.matching import card
from app.resumes import service as resumes
from app.views import service as views

router = APIRouter(prefix="/candidates/me", tags=["candidates"])

_TRUST = TrustConfig.load()
_owner = require_roles("candidate")
_writer = require_consent(ConsentType.pd_processing)


async def owner(user: User = Depends(_owner)) -> User:
    return user


async def writer(user: User = Depends(owner), _: User = Depends(_writer)) -> User:
    return user


class Preferences(BaseModel):
    salary_min: int | None
    formats: list[WorkFormat]
    employment_types: list[EmploymentType]
    city: str | None
    relocation: bool


class Visibility(BaseModel):
    companies: bool
    education: bool
    repos: bool
    public_profile: bool
    teams: bool


class ExperienceItem(BaseModel):
    title: str | None
    company: str | None
    start: str | None
    end: str | None
    skills: list[str]


class CandidateProfile(BaseModel):
    """`CandidateProfile` (api.md §3). Пока без `code`, `completeness`."""

    pseudonym: str
    profile_version: int
    search_status: SearchStatus
    active_until: datetime | None
    preferences: Preferences
    visibility: Visibility
    category: card.Category | None = None
    grade: card.GradeInfo
    skills: list[card.SkillWithTrust] = []
    team_signals: list[card.TeamSignal] = []
    claimed_soft: list[str] = []
    fsp: card.OwnerFsp | None = None
    experience: list[ExperienceItem] = []


class PreferencesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    salary_min: int | None = Field(default=None, ge=0, le=100_000_000)
    formats: list[WorkFormat] | None = None
    employment_types: list[EmploymentType] | None = None
    city: str | None = Field(default=None, max_length=100)
    relocation: bool | None = None
    search_status: SearchStatus | None = None


class VisibilityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    companies: bool | None = None
    education: bool | None = None
    repos: bool | None = None
    public_profile: bool | None = None
    teams: bool | None = None


class StoplistIO(BaseModel):
    company_ids: list[UUID] = Field(max_length=service.STOPLIST_MAX)


async def profile_out(session: AsyncSession, c: Candidate) -> CandidateProfile:
    vis = {**{"teams": True}, **c.visibility}
    parts = await card.build_owner_parts(session, c, _TRUST)
    return CandidateProfile(
        pseudonym=c.pseudonym,
        profile_version=c.profile_version,
        search_status=service.effective_status(c),
        active_until=c.active_until,
        preferences=Preferences(
            salary_min=c.salary_min,
            formats=c.formats or [],
            employment_types=c.employment_types or [],
            city=c.city,
            relocation=c.relocation,
        ),
        visibility=Visibility(**{k: bool(vis.get(k, False)) for k in Visibility.model_fields}),
        category=parts.category,
        grade=parts.grade,
        skills=parts.skills,
        team_signals=parts.team_signals,
        claimed_soft=list(c.claimed_soft or []),
        fsp=await card.owner_fsp(session, c),
        experience=await resumes.experience_for_profile(session, c.user_id),
    )


async def _cand(request: Request, session: AsyncSession, user: User) -> Candidate:
    return await service.get_or_create(
        session, user.id, request.app.state.settings.pseudo_id_secret
    )


@router.get("/profile", response_model=CandidateProfile)
async def get_profile(
    request: Request,
    user: User = Depends(owner),
    session: AsyncSession = Depends(get_session),
):
    return await profile_out(session, await _cand(request, session, user))


@router.get("/skills/{skill_id}/evidence", response_model=list[card.EvidenceBrief])
async def skill_evidence(
    skill_id: str,
    request: Request,
    user: User = Depends(owner),
    session: AsyncSession = Depends(get_session),
):
    """«Откуда взялся навык»: `skill_id` — id или slug; чужого/отсутствующего навыка нет — 404."""
    cand = await _cand(request, session, user)
    items = await card.skill_evidence(session, cand, skill_id, _TRUST)
    if items is None:
        raise ProblemError(404, "skill_not_found", "Навык не найден")
    return items


@router.patch("/preferences", response_model=CandidateProfile)
async def patch_preferences(
    body: PreferencesIn,
    request: Request,
    user: User = Depends(writer),
    session: AsyncSession = Depends(get_session),
):
    cand = await _cand(request, session, user)
    await service.update_preferences(session, cand, body.model_dump(exclude_unset=True))
    return await profile_out(session, cand)


@router.patch("/visibility", response_model=CandidateProfile)
async def patch_visibility(
    body: VisibilityIn,
    request: Request,
    user: User = Depends(writer),
    session: AsyncSession = Depends(get_session),
):
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if changes.get("public_profile") and not await consents.has_consent(
        session, user.id, ConsentType.public_profile
    ):
        raise ProblemError(
            403,
            "consent_required",
            "Нужно согласие",
            "Выдайте согласие public_profile",
            errors=[{"field": "consent", "message": "public_profile"}],
        )
    cand = await _cand(request, session, user)
    await service.update_visibility(session, cand, changes)
    return await profile_out(session, cand)


@router.put("/stoplist", response_model=StoplistIO)
async def put_stoplist(
    body: StoplistIO,
    request: Request,
    user: User = Depends(writer),
    session: AsyncSession = Depends(get_session),
):
    cand = await _cand(request, session, user)
    await service.set_stoplist(session, cand, body.company_ids)
    return StoplistIO(company_ids=[UUID(c) for c in cand.stoplist_company_ids])


@router.get("/views")
async def my_views(
    user: User = Depends(owner), session: AsyncSession = Depends(get_session)
) -> dict:
    """«Вас смотрели N компаний» — только агрегаты, без названий (security.md §3)."""
    return await views.stats(session, user.id)
