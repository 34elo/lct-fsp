from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fsp_contracts.enums import CompanyMemberRole, CompanyStatus
from fsp_platform.app import ProblemError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies import service
from app.companies.models import Company
from app.deps import get_limiter, get_session, get_storage
from app.identity import profile
from app.identity.deps import require_roles
from app.identity.mailer import SmtpMailer
from app.identity.models import User
from app.openapi_errors import problem_responses

router = APIRouter(tags=["companies"])
admin_router = APIRouter(prefix="/admin/companies", tags=["admin"])
invites_router = APIRouter(prefix="/company-invites", tags=["companies"])

_employer = require_roles("employer")
_admin = require_roles("fsp_admin")


class Contacts(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    telegram: str | None = None


class CompanyOut(BaseModel):
    id: UUID
    name: str
    inn: str | None
    site: str | None
    description: str | None
    logo_url: str | None = None  # `/companies/{id}/logo?v=`, публичный (E41-12)
    contacts: dict[str, Any] | None
    direction: str | None
    status: CompanyStatus
    show_verified_badge: bool = True
    responsibility_score: float | None
    created_at: datetime
    my_role: CompanyMemberRole | None = None


class CompanyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=200)
    inn: str | None = Field(default=None, pattern=r"^(\d{10}|\d{12})$")
    site: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    contacts: Contacts | None = Field(default=None)
    direction: str | None = Field(default=None, max_length=1000)
    show_verified_badge: bool = True


class CompanyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=200)
    inn: str | None = Field(default=None, pattern=r"^(\d{10}|\d{12})$")
    site: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    contacts: Contacts | None = Field(default=None)
    direction: str | None = Field(default=None, max_length=1000)
    show_verified_badge: bool | None = None


class MemberIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    role: CompanyMemberRole = CompanyMemberRole.member


class MemberOut(BaseModel):
    user_id: UUID
    role: CompanyMemberRole


def company_out(c: Company, my_role: str | None = None) -> CompanyOut:
    return CompanyOut(
        id=c.id,
        name=c.name,
        inn=c.inn,
        site=c.site,
        description=c.description,
        logo_url=service.logo_url(c),
        contacts=c.contacts,
        direction=c.direction,
        status=CompanyStatus(c.status),
        show_verified_badge=c.show_verified_badge,
        responsibility_score=c.responsibility_score,
        created_at=c.created_at,
        my_role=CompanyMemberRole(my_role) if my_role else None,
    )


@router.post(
    "/companies",
    response_model=CompanyOut,
    status_code=201,
    responses=problem_responses(401, 403, 422),
)
async def register_company(
    body: CompanyIn,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    company = await service.create_company(session, user, body.model_dump())
    return company_out(company, CompanyMemberRole.admin.value)


@router.get("/companies/me", response_model=CompanyOut, responses=problem_responses(401, 403))
async def get_my_company(
    user: User = Depends(_employer), session: AsyncSession = Depends(get_session)
):
    company, member = await service.require_company(session, user.id)
    return company_out(company, member.role)


@router.patch(
    "/companies/me", response_model=CompanyOut, responses=problem_responses(401, 403, 422)
)
async def patch_my_company(
    body: CompanyPatch,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    company, member = await service.require_company(session, user.id, admin=True)
    changes = body.model_dump(exclude_unset=True)
    for key in ("name", "show_verified_badge"):
        if changes.get(key) is None:
            changes.pop(key, None)
    await service.update_company(session, company, changes)
    return company_out(company, member.role)


@router.put(
    "/companies/me/logo",
    response_model=CompanyOut,
    responses=problem_responses(401, 403, 404, 413, 415, 422, 429),
)
async def put_company_logo(
    request: Request,
    file: Annotated[UploadFile, File()],
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
    storage=Depends(get_storage),
    limiter=Depends(get_limiter),
):
    """Логотип компании (E41-12): PNG, JPEG или WebP по сигнатуре, до 2 МБ; только владелец."""
    company, member = await service.require_company(session, user.id, admin=True)
    await limiter.check(f"logo:{company.id}", 20, 3600)
    data = await file.read(profile.AVATAR_MAX_BYTES + 1)
    if not getattr(request.app.state, "bucket_ready", False):
        await storage.ensure_bucket()
        request.app.state.bucket_ready = True
    return company_out(await service.set_logo(session, storage, company, data), member.role)


@router.delete(
    "/companies/me/logo", response_model=CompanyOut, responses=problem_responses(401, 403, 404)
)
async def delete_company_logo(
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
    storage=Depends(get_storage),
):
    company, member = await service.require_company(session, user.id, admin=True)
    return company_out(await service.clear_logo(session, storage, company), member.role)


@router.get(
    "/companies/{company_id}/logo",
    response_class=Response,
    responses={200: {"content": {"image/*": {}}}, **problem_responses(404)},
)
async def get_company_logo(
    company_id: UUID,
    session: AsyncSession = Depends(get_session),
    storage=Depends(get_storage),
):
    """Без авторизации: `<img>` не несёт токен, логотип компании публичен."""
    company = await service.get_company(session, company_id)
    if company is None or not company.logo_key:
        raise ProblemError(404, "logo_not_found", "Логотип не найден")
    try:
        data = await storage.get(company.logo_key)
    except Exception as exc:  # файл пропал из хранилища
        raise ProblemError(404, "logo_not_found", "Логотип не найден") from exc
    return Response(
        content=data,
        media_type=profile.content_type(company.logo_key),
        headers={"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )


@router.post(
    "/companies/me/members",
    response_model=MemberOut,
    status_code=201,
    responses=problem_responses(401, 403, 422),
)
async def invite_member(
    body: MemberIn,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    company, _ = await service.require_company(session, user.id, admin=True)
    member = await service.add_member(session, company, body.email, body.role)
    return MemberOut(user_id=member.user_id, role=CompanyMemberRole(member.role))


# --- E39-24: команда компании — владелец (`admin`) и HR (`member`) ---


class CompanyMemberOut(BaseModel):
    user_id: UUID
    role: CompanyMemberRole
    email: str | None = None
    full_name: str | None = None
    position: str | None = None
    avatar_url: str | None = None
    is_me: bool = False
    # E41-16 (только владельцу): аккаунт создан владельцем — ему можно выдать новый пароль;
    # HR ещё не сменил временный пароль и до какого времени тот действует
    managed: bool = False
    must_change_password: bool = False
    temp_password_expires_at: datetime | None = None


class InviteOut(BaseModel):
    id: UUID
    email: str
    created_at: datetime
    expires_at: datetime


class InviteCreated(InviteOut):
    url: str  # ссылка-приглашение: токен показывается один раз


class CompanyTeamOut(BaseModel):
    members: list[CompanyMemberOut]
    invites: list[InviteOut]  # действующие приглашения — только владельцу, HR видит []
    can_manage: bool


class InviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvitePreview(BaseModel):
    company_name: str
    company_verified: bool
    inviter_name: str | None = None
    email_masked: str
    expires_at: datetime


def _mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def _invite_out(i) -> InviteOut:
    return InviteOut(id=i.id, email=i.email, created_at=i.created_at, expires_at=i.expires_at)


@router.get(
    "/companies/me/members",
    response_model=CompanyTeamOut,
    responses=problem_responses(401, 403, 404),
)
async def my_team(user: User = Depends(_employer), session: AsyncSession = Depends(get_session)):
    """Команда компании: видят все участники, приглашения и управление — только владелец."""
    company, member = await service.require_company(session, user.id)
    owner = member.role == CompanyMemberRole.admin.value
    members = await service.list_members(session, company.id)
    return CompanyTeamOut(
        members=[
            CompanyMemberOut(
                user_id=m.user_id, role=CompanyMemberRole(m.role), email=m.email,
                full_name=m.full_name, position=m.position, avatar_url=m.avatar_url,
                is_me=m.user_id == user.id,
                managed=m.managed if owner else False,
                must_change_password=m.must_change_password if owner else False,
                temp_password_expires_at=m.temp_password_expires_at if owner else None,
            )
            for m in members
        ],
        invites=[_invite_out(i) for i in await service.list_invites(session, company.id)]
        if owner
        else [],
        can_manage=owner,
    )  # fmt: skip


@router.post(
    "/companies/me/invites",
    response_model=InviteCreated,
    status_code=201,
    deprecated=True,  # E41-16: интерфейс выдаёт доступ HR через `/companies/me/hr`
    responses=problem_responses(401, 403, 404, 409, 422, 429),
)
async def create_invite(
    body: InviteIn,
    request: Request,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    """Владелец приглашает HR по email: письмо со ссылкой (SMTP) и та же ссылка в ответе."""
    company, _ = await service.require_company(session, user.id, admin=True)
    await request.app.state.limiter.check(f"company_invite:{company.id}", 30, 3600)
    invite, token = await service.create_invite(session, company, user, body.email)
    settings = request.app.state.settings
    url = f"{settings.web_base_url.rstrip('/')}/invite/company/{token}"
    mailer = getattr(request.app.state, "mailer", None) or SmtpMailer(settings)
    sender = await profile.signature(session, user.id)
    who = sender.full_name if sender else "Владелец компании"
    await mailer.send(
        invite.email,
        f"Приглашение в команду «{company.name}» на ФСП Карьере",
        f"{who} приглашает вас в команду компании «{company.name}» на ФСП Карьере.\n\n"
        f"Принять приглашение: {url}\n\nСсылка действует 7 дней. "
        "Войдите или зарегистрируйтесь как работодатель с этим email.",
    )
    return InviteCreated(**_invite_out(invite).model_dump(), url=url)


@router.delete(
    "/companies/me/invites/{invite_id}",
    status_code=204,
    response_class=Response,
    responses=problem_responses(401, 403, 404),
)
async def revoke_invite(
    invite_id: UUID,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    company, _ = await service.require_company(session, user.id, admin=True)
    await service.revoke_invite(session, company.id, invite_id)
    return Response(status_code=204)


@router.delete(
    "/companies/me/members/{user_id}",
    status_code=204,
    response_class=Response,
    responses=problem_responses(401, 403, 404, 409),
)
async def remove_member(
    user_id: UUID,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    """Отозвать доступ HR: убрать из команды, закрыть сессии; аккаунт от владельца выключается."""
    company, _ = await service.require_company(session, user.id, admin=True)
    await service.remove_member(session, company.id, user_id, user)
    return Response(status_code=204)


# --- E41-16: доступ HR без почты — карточка доступа с временным паролем ---

HR_ACCESS_LIMIT = 20  # создание и сброс пароля HR: в час на компанию


class HrIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    full_name: str = Field(min_length=2, max_length=120)


class HrAccessCard(BaseModel):
    """Показывается владельцу один раз: временный пароль в БД — только хешем."""

    user_id: UUID
    email: str
    full_name: str | None
    login_url: str  # `WEB_BASE_URL` + `/login`
    temp_password: str
    expires_at: datetime


class AccessLogEntry(BaseModel):
    id: UUID
    action: Literal["created", "password_reset", "revoked"]
    created_at: datetime
    actor_name: str | None
    target_email: str | None
    target_name: str | None


def _card(request: Request, access: service.HrAccess) -> HrAccessCard:
    base = request.app.state.settings.web_base_url.rstrip("/")
    return HrAccessCard(
        user_id=access.user.id,
        email=access.user.email or "",
        full_name=access.full_name,
        login_url=f"{base}/login",
        temp_password=access.temp_password,
        expires_at=access.expires_at,
    )


_NO_STORE = {"Cache-Control": "no-store"}


@router.post(
    "/companies/me/hr",
    response_model=HrAccessCard,
    status_code=201,
    responses=problem_responses(401, 403, 404, 409, 422, 429),
)
async def create_hr(
    body: HrIn,
    request: Request,
    response: Response,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    """Владелец создаёт аккаунт HR сразу; логин и временный пароль (72 ч) — в ответе один раз."""
    company, _ = await service.require_company(session, user.id, admin=True)
    await request.app.state.limiter.check(f"company_hr:{company.id}", HR_ACCESS_LIMIT, 3600)
    access = await service.create_hr(session, company, user, body.email, body.full_name)
    response.headers.update(_NO_STORE)
    return _card(request, access)


@router.post(
    "/companies/me/members/{user_id}/password",
    response_model=HrAccessCard,
    responses=problem_responses(401, 403, 404, 409, 429),
)
async def reset_hr_password(
    user_id: UUID,
    request: Request,
    response: Response,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    """Выдать HR новый временный пароль: прежний и все сессии HR сразу недействительны."""
    company, _ = await service.require_company(session, user.id, admin=True)
    await request.app.state.limiter.check(f"company_hr:{company.id}", HR_ACCESS_LIMIT, 3600)
    access = await service.reset_hr_password(session, company, user, user_id)
    response.headers.update(_NO_STORE)
    return _card(request, access)


@router.get(
    "/companies/me/access-log",
    response_model=list[AccessLogEntry],
    responses=problem_responses(401, 403, 404),
)
async def access_log(user: User = Depends(_employer), session: AsyncSession = Depends(get_session)):
    """Журнал доступа HR (кто, кого, когда) — только владельцу, последние 50 записей."""
    company, _ = await service.require_company(session, user.id, admin=True)
    return [AccessLogEntry(**vars(e)) for e in await service.access_log(session, company.id)]


@invites_router.get("/{token}", response_model=InvitePreview, responses=problem_responses(404))
async def invite_preview(token: str, session: AsyncSession = Depends(get_session)):
    """Без авторизации: кто зовёт и куда; адрес приглашения — замаскирован."""
    invite = await service.invite_by_token(session, token)
    company = await service.get_company(session, invite.company_id)
    if company is None:
        raise ProblemError(404, "invite_not_found", "Приглашение не найдено или истекло")
    sender = await profile.signature(session, invite.invited_by)
    return InvitePreview(
        company_name=company.name,
        company_verified=service.badge_visible(company),
        inviter_name=sender.full_name if sender else None,
        email_masked=_mask(invite.email),
        expires_at=invite.expires_at,
    )


@invites_router.post(
    "/{token}/accept", response_model=CompanyOut, responses=problem_responses(401, 403, 404, 409)
)
async def invite_accept(
    token: str,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    company = await service.accept_invite(session, user, token)
    member = await service.membership(session, user.id)
    return company_out(company, member.role if member else None)


@admin_router.get("", response_model=list[CompanyOut], responses=problem_responses(401, 403))
async def admin_list(
    status: CompanyStatus | None = None,
    _: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    items = await service.list_by_status(session, status.value if status else None)
    return [company_out(c) for c in items]


@admin_router.post(
    "/{company_id}/verify", response_model=CompanyOut, responses=problem_responses(401, 403, 404)
)
async def admin_verify(
    company_id: UUID,
    _: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    return company_out(await service.verify(session, company_id))


@admin_router.post(
    "/{company_id}/reject", response_model=CompanyOut, responses=problem_responses(401, 403, 404)
)
async def admin_reject(
    company_id: UUID,
    _: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    return company_out(await service.reject(session, company_id))
