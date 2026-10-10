from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from fsp_contracts.assessment import ClaimedVsConfirmed
from fsp_contracts.enums import (
    ConsentType,
    EmploymentType,
    Grade,
    RoleSlug,
    SearchStatus,
    WorkFormat,
)
from fsp_platform.app import ProblemError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import service as assessment
from app.candidates import pdf, service
from app.candidates.models import Candidate
from app.config import Settings
from app.consents import service as consents
from app.consents.deps import require_consent
from app.deps import get_limiter, get_session, get_storage
from app.graph.category import load_category
from app.graph.trust import TrustConfig
from app.identity import profile as user_profile
from app.identity import service as identity
from app.identity.deps import get_user_even_deleted, require_roles
from app.identity.models import User
from app.matching import card
from app.openapi_errors import problem_responses
from app.resumes import service as resumes
from app.taxonomy.service import SkillGraphCache
from app.views import service as views

router = APIRouter(prefix="/candidates/me", tags=["candidates"])
public_router = APIRouter(prefix="/candidates", tags=["candidates"])

_TRUST = TrustConfig.load()
_GRAPH = SkillGraphCache()
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
    full_name: bool
    companies: bool
    fsp: bool
    region: bool
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


class EducationItem(BaseModel):
    institution: str | None
    degree: str | None
    field: str | None
    year_end: int | None


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
    contacts: ContactsIO | None = None  # только владельцу; в карточку работодателя не идёт
    full_name: str | None = None  # только владельцу; работодателю — при visibility.full_name
    desired_roles: list[str] = []
    experience_months: int | None = None
    age_group: Literal["adult", "minor"] | None = None  # minor = 15–17 лет
    parent_consent: bool = False  # согласие родителя на ПДн (только для minor)
    publishable: bool = True  # false: 15–17 лет без согласия родителя, в выдачу не попадает
    fsp: card.OwnerFsp | None = None
    experience: list[ExperienceItem] = []
    claimed_vs_confirmed: list[ClaimedVsConfirmed] = []  # E23-3: заявлено (опрос/резюме) vs тест
    # E39-15: вкладка «Данные» — образование, ссылки (только владельцу), скрытые навыки и
    # неподтверждённый черновик резюме (загружено после последнего подтверждённого)
    education: list[EducationItem] = []
    links: list[str] = []
    hidden_skills: list[str] = []
    resume_draft_id: UUID | None = None
    avatar_url: str | None = None  # E41-12: только владельцу; подпись в адресе


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

    full_name: bool | None = None
    companies: bool | None = None
    fsp: bool | None = None
    region: bool | None = None
    education: bool | None = None
    repos: bool | None = None
    public_profile: bool | None = None
    teams: bool | None = None


class ContactsIO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(default=None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = Field(default=None, max_length=32, pattern=r"^\+?[0-9 ()\-]{5,32}$")
    telegram: str | None = Field(default=None, max_length=33, pattern=r"^@?[A-Za-z0-9_]{5,32}$")


class StackItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=100)
    years: float | None = Field(default=None, ge=0, le=60)


Link = Annotated[str, Field(max_length=300, pattern=r"^https?://[^\s]+$")]
Slug = Annotated[str, Field(min_length=1, max_length=100)]


class ProfileIn(BaseModel):
    """`PATCH /candidates/me/profile`: частичное обновление ручной формы (E20-4)."""

    model_config = ConfigDict(extra="forbid")

    contacts: ContactsIO | None = None  # null очищает
    full_name: str | None = Field(default=None, max_length=120)  # null или пусто очищает
    stack: list[StackItem] | None = Field(default=None, max_length=60)  # полный список
    experience_months: int | None = Field(default=None, ge=0, le=720)
    # профессии системы (E41-6)
    desired_roles: list[Slug] | None = Field(default=None, max_length=5)
    soft_skills: list[str] | None = Field(default=None, max_length=30)  # slug
    age_group: Literal["adult", "minor"] | None = None
    parent_consent: bool | None = None  # true — родитель согласен; false — отзыв
    # E39-15: полный список; null или [] очищает
    links: list[Link] | None = Field(default=None, max_length=10)
    hidden_skills: list[Slug] | None = Field(default=None, max_length=200)


class StoplistIO(BaseModel):
    company_ids: list[UUID] = Field(max_length=service.STOPLIST_MAX)


async def profile_out(session: AsyncSession, c: Candidate, settings: Settings) -> CandidateProfile:
    vis = service.visibility_of(c)
    parts = await card.build_owner_parts(session, c, _TRUST)
    contacts = service.contacts_of(c, settings.pii_key)
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
        contacts=ContactsIO(**contacts) if contacts else None,
        full_name=service.full_name_of(c, settings.pii_key),
        desired_roles=list(c.desired_roles or []),
        experience_months=c.experience_months,
        age_group=c.age_group,
        parent_consent=c.parent_consent_at is not None,
        publishable=service.is_publishable(c),
        fsp=await card.owner_fsp(session, c),
        experience=await resumes.experience_for_profile(session, c.user_id),
        claimed_vs_confirmed=await assessment.claimed_vs_confirmed(session, c.user_id),
        education=[
            EducationItem(**e) for e in await resumes.education_for_profile(session, c.user_id)
        ],
        links=service.links_of(c, settings.pii_key),
        hidden_skills=sorted(service.hidden_skills_of(c)),
        resume_draft_id=await resumes.draft_id_for_profile(session, c.user_id),
        avatar_url=service.avatar_url(c, settings.jwt_secret),
    )


async def _cand(request: Request, session: AsyncSession, user: User) -> Candidate:
    return await service.get_or_create(
        session, user.id, request.app.state.settings.pseudo_id_secret
    )


@router.get("/profile", response_model=CandidateProfile, responses=problem_responses(401, 403))
async def get_profile(
    request: Request,
    user: User = Depends(owner),
    session: AsyncSession = Depends(get_session),
):
    return await profile_out(
        session, await _cand(request, session, user), request.app.state.settings
    )


AVATAR_LIMIT = 20  # загрузок в час
AVATAR_WINDOW = 3600


@router.put(
    "/avatar",
    response_model=CandidateProfile,
    responses=problem_responses(401, 403, 413, 415, 422, 429),
)
async def put_avatar(
    request: Request,
    file: Annotated[UploadFile, File()],
    user: User = Depends(owner),
    session: AsyncSession = Depends(get_session),
    limiter=Depends(get_limiter),
):
    """Аватар кандидата (E41-12): PNG, JPEG или WebP по сигнатуре, до 2 МБ. Работодатель видит
    его только после приглашения, как ФИО; в анонимную карточку он не попадает."""
    await limiter.check(f"avatar:{user.id}", AVATAR_LIMIT, AVATAR_WINDOW)
    data = await file.read(user_profile.AVATAR_MAX_BYTES + 1)
    storage = get_storage(request)
    if not getattr(request.app.state, "bucket_ready", False):
        await storage.ensure_bucket()
        request.app.state.bucket_ready = True
    cand = await _cand(request, session, user)
    await service.set_avatar(session, storage, cand, data)
    return await profile_out(session, cand, request.app.state.settings)


@router.delete("/avatar", response_model=CandidateProfile, responses=problem_responses(401, 403))
async def delete_avatar(
    request: Request,
    user: User = Depends(owner),
    session: AsyncSession = Depends(get_session),
):
    cand = await _cand(request, session, user)
    await service.clear_avatar(session, get_storage(request), cand)
    return await profile_out(session, cand, request.app.state.settings)


@public_router.get(
    "/{pseudo_id}/avatar",
    response_class=Response,
    responses={200: {"content": {"image/*": {}}}, **problem_responses(404)},
)
async def get_avatar(
    pseudo_id: str,
    request: Request,
    sig: str = Query(max_length=64),
    session: AsyncSession = Depends(get_session),
):
    """Без токена, но с подписью из адреса: её выдаёт сервер владельцу и работодателю после
    приглашения. Нет кандидата, файла или подпись не сходится — одинаковый 404."""
    cand = await service.by_pseudo_id(session, pseudo_id)
    secret = request.app.state.settings.jwt_secret
    if cand is None or not service.avatar_sig_ok(cand, secret, sig):
        raise ProblemError(404, "avatar_not_found", "Аватар не найден")
    try:
        data = await get_storage(request).get(cand.avatar_key)
    except Exception as exc:
        raise ProblemError(404, "avatar_not_found", "Аватар не найден") from exc
    return Response(
        content=data,
        media_type=user_profile.content_type(cand.avatar_key),
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


@router.get(
    "/profile.pdf",
    response_class=Response,
    responses={**problem_responses(401, 403), 200: {"content": {"application/pdf": {}}}},
)
async def profile_pdf(
    request: Request,
    user: User = Depends(owner),
    session: AsyncSession = Depends(get_session),
):
    """PDF-профиль владельца (E20-6): категория, грейд, навыки с доверием, ФСП, тесты."""
    cand = await _cand(request, session, user)
    profile = await profile_out(session, cand, request.app.state.settings)
    grades = await assessment.get_grades(session, cand.user_id)
    photo = None
    if cand.avatar_key:
        try:
            photo = (await get_storage(request).get(cand.avatar_key), cand.avatar_key)
        except Exception:  # файл пропал из хранилища: резюме без фото
            photo = None
    html = pdf.build_html(profile, grades, photo=photo)
    data = await asyncio.to_thread(pdf.render_pdf, html)
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{cand.pseudonym}.pdf"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get(
    "/skills/{skill_id}/evidence",
    response_model=list[card.EvidenceBrief],
    responses=problem_responses(401, 403, 404),
)
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


@router.patch(
    "/profile",
    response_model=CandidateProfile,
    responses=problem_responses(401, 403, 422),
)
async def patch_profile(
    body: ProfileIn,
    request: Request,
    user: User = Depends(writer),
    session: AsyncSession = Depends(get_session),
):
    cand = await _cand(request, session, user)
    changes = body.model_dump(exclude_unset=True, mode="json")
    for key in (
        "stack",
        "experience_months",
        "desired_roles",
        "soft_skills",
        "links",
        "hidden_skills",
    ):
        if key in changes and changes[key] is None and key != "experience_months":
            changes[key] = []  # null и [] для списков одно и то же
    await service.update_profile(session, cand, changes, pii_key=request.app.state.settings.pii_key)
    return await profile_out(session, cand, request.app.state.settings)


@router.patch(
    "/preferences",
    response_model=CandidateProfile,
    responses=problem_responses(401, 403, 422),
)
async def patch_preferences(
    body: PreferencesIn,
    request: Request,
    user: User = Depends(writer),
    session: AsyncSession = Depends(get_session),
):
    cand = await _cand(request, session, user)
    await service.update_preferences(session, cand, body.model_dump(exclude_unset=True))
    return await profile_out(session, cand, request.app.state.settings)


@router.patch(
    "/visibility",
    response_model=CandidateProfile,
    responses=problem_responses(401, 403, 422),
)
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
    return await profile_out(session, cand, request.app.state.settings)


@router.put("/stoplist", response_model=StoplistIO, responses=problem_responses(401, 403, 422))
async def put_stoplist(
    body: StoplistIO,
    request: Request,
    user: User = Depends(writer),
    session: AsyncSession = Depends(get_session),
):
    cand = await _cand(request, session, user)
    await service.set_stoplist(session, cand, body.company_ids)
    return StoplistIO(company_ids=[UUID(c) for c in cand.stoplist_company_ids])


@router.get("/views", responses=problem_responses(401, 403))
async def my_views(
    user: User = Depends(owner), session: AsyncSession = Depends(get_session)
) -> dict:
    """«Вас смотрели N компаний» — только агрегаты, без названий (security.md §3)."""
    return await views.stats(session, user.id)


class CategoryRole(BaseModel):
    role: str
    weight: float  # доля метки среди выбранных
    score: float  # role_score (ml.md §4)


class CategoryContribution(BaseModel):
    skill: str
    weight: float
    confidence: float
    level: int
    sources: list[str]
    contribution: float


class DisputeOut(BaseModel):
    id: UUID
    claimed_role: str
    claimed_grade: str
    comment: str | None
    status: str  # open | resolved
    created_at: datetime


class CategoryExplanation(BaseModel):
    """`CategoryExplanation` (api.md §3): почему такая категория и как подняться."""

    primary_role: str | None
    roles: list[CategoryRole]
    primary_stack: list[str]
    explanation: list[CategoryContribution]  # топ-навыки основной роли по вкладу w·conf
    grade: card.GradeInfo  # разбивка, уверенность, next_grade с подсказками
    dispute: DisputeOut | None = None


class DisputeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claimed_role: RoleSlug
    claimed_grade: Grade
    comment: str | None = Field(default=None, max_length=2000)


def _dispute_out(d) -> DisputeOut:
    return DisputeOut(
        id=d.id, claimed_role=d.claimed_role, claimed_grade=d.claimed_grade, comment=d.comment,
        status="resolved" if d.resolved_at else "open", created_at=d.created_at,
    )  # fmt: skip


@router.get("/category", response_model=CategoryExplanation, responses=problem_responses(401, 403))
async def get_category(
    request: Request,
    user: User = Depends(owner),
    session: AsyncSession = Depends(get_session),
):
    cand = await _cand(request, session, user)
    cat = await load_category(session, cand.user_id, await _GRAPH.get(session), _TRUST.category)
    d = await service.open_dispute(session, cand.user_id)
    return CategoryExplanation(
        primary_role=cat.primary_role,
        roles=[CategoryRole(role=r.role, weight=r.weight, score=cat.scores.get(r.role, 0.0))
               for r in cat.roles],
        primary_stack=cat.primary_stack,
        explanation=[CategoryContribution(skill=e.slug, weight=e.weight, confidence=e.confidence,
                                          level=e.level, sources=list(e.sources),
                                          contribution=e.contribution)
                     for e in cat.explanation],
        grade=card._grade_info(cand),
        dispute=_dispute_out(d) if d else None,
    )  # fmt: skip


@router.post(
    "/category/dispute",
    response_model=DisputeOut,
    status_code=201,
    responses=problem_responses(401, 403, 422),
)
async def dispute_category(
    body: DisputeIn,
    request: Request,
    user: User = Depends(writer),
    session: AsyncSession = Depends(get_session),
):
    cand = await _cand(request, session, user)
    row = await service.add_dispute(
        session, cand, role=body.claimed_role.value, grade=body.claimed_grade.value,
        comment=body.comment,
    )  # fmt: skip
    return _dispute_out(row)


DELETE_CONFIRM_PHRASE = "УДАЛИТЬ"


class DeleteIn(BaseModel):
    """Подтверждение необратимого удаления: пароль; без пароля (вход через Telegram) — фраза."""

    model_config = ConfigDict(extra="forbid")

    password: str | None = Field(default=None, max_length=256)
    confirm: str | None = Field(default=None, max_length=32)


@router.delete("", status_code=204, responses=problem_responses(401, 403, 404, 429))
async def delete_me(
    body: DeleteIn,
    user: User = Depends(get_user_even_deleted),
    session: AsyncSession = Depends(get_session),
    storage=Depends(get_storage),
    limiter=Depends(get_limiter),
):
    """Удаление профиля (F13, 152-ФЗ): необратимо, ПДн стираются, остаётся псевдоним в офферах.

    Подтверждение: `password` (если он задан у аккаунта) или `confirm="УДАЛИТЬ"`. Повторный
    вызов и чужая/удалённая анкета — 404.
    """
    if user.role != "candidate":
        raise ProblemError(403, "forbidden", "Недостаточно прав")
    if user.deleted_at is not None:
        raise ProblemError(404, "candidate_not_found", "Профиль не найден")
    await limiter.check(f"delete_account:{user.id}", 5, 3600)
    if user.password_hash:
        confirmed = body.password is not None and identity.password_matches(user, body.password)
    else:
        confirmed = body.confirm == DELETE_CONFIRM_PHRASE
    if not confirmed:
        raise ProblemError(
            403, "confirmation_failed", "Удаление не подтверждено", "Неверный пароль или фраза"
        )
    await service.erase(session, storage, user)
    return Response(status_code=204)
