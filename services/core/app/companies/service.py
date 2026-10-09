"""Компании: регистрация, участники, модерация (статусы — `CompanyStatus`)."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fsp_contracts.enums import CompanyMemberRole, CompanyStatus
from fsp_platform.app import ProblemError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies.models import Company, CompanyInvite, CompanyMember
from app.identity import profile
from app.identity.models import User, UserProfile
from app.identity.service import hash_token, normalize_email

# из какого статуса можно перейти в новый (blocked выставляется вне этих эндпоинтов)
_VERIFY_FROM = {CompanyStatus.pending, CompanyStatus.rejected}
_REJECT_FROM = {CompanyStatus.pending, CompanyStatus.verified}


async def membership(session: AsyncSession, user_id: uuid.UUID) -> CompanyMember | None:
    return await session.scalar(select(CompanyMember).where(CompanyMember.user_id == user_id))


async def create_company(session: AsyncSession, user: User, fields: dict) -> Company:
    if await membership(session, user.id) is not None:
        raise ProblemError(409, "company_exists", "Вы уже состоите в компании")
    company = Company(**fields, status=CompanyStatus.pending.value)
    session.add(company)
    await session.flush()
    session.add(
        CompanyMember(company_id=company.id, user_id=user.id, role=CompanyMemberRole.admin.value)
    )
    try:
        await session.flush()
    except IntegrityError as exc:  # параллельная регистрация
        raise ProblemError(409, "company_exists", "Вы уже состоите в компании") from exc
    return company


async def my_company(
    session: AsyncSession, user_id: uuid.UUID
) -> tuple[Company, CompanyMember] | None:
    m = await membership(session, user_id)
    if m is None:
        return None
    company = await session.get(Company, m.company_id)
    return (company, m) if company is not None else None


async def require_company(
    session: AsyncSession, user_id: uuid.UUID, *, admin: bool = False
) -> tuple[Company, CompanyMember]:
    found = await my_company(session, user_id)
    if found is None:
        raise ProblemError(404, "company_not_found", "Компания не найдена")
    if admin and found[1].role != CompanyMemberRole.admin.value:
        raise ProblemError(403, "forbidden", "Недостаточно прав")
    return found


def badge_visible(company: Company) -> bool:
    """Метка «компания проверена» для кандидатов: verified и компания не скрыла её (E32-5a)."""
    return company.status == "verified" and bool(company.show_verified_badge)


async def update_company(session: AsyncSession, company: Company, changes: dict) -> Company:
    for key, value in changes.items():
        setattr(company, key, value)
    await session.flush()
    return company


async def add_member(
    session: AsyncSession, company: Company, email: str, role: CompanyMemberRole
) -> CompanyMember:
    """Приглашение: пользователь с ролью employer должен быть уже зарегистрирован."""
    user = await session.scalar(
        select(User).where(
            User.email == normalize_email(email),
            User.role == "employer",
            User.deleted_at.is_(None),
        )
    )
    if user is None:
        raise ProblemError(404, "user_not_found", "Работодатель с таким email не найден")
    existing = await membership(session, user.id)
    if existing is not None:
        if existing.company_id == company.id:
            return existing
        raise ProblemError(409, "already_member", "Пользователь состоит в другой компании")
    member = CompanyMember(company_id=company.id, user_id=user.id, role=role.value)
    session.add(member)
    await session.flush()
    return member


async def list_by_status(session: AsyncSession, status: str | None) -> list[Company]:
    q = select(Company).order_by(Company.created_at, Company.id)
    if status is not None:
        q = q.where(Company.status == status)
    return list((await session.scalars(q)).all())


async def _moderate(
    session: AsyncSession, company_id: uuid.UUID, target: CompanyStatus, allowed: set
) -> Company:
    company = await session.get(Company, company_id)
    if company is None:
        raise ProblemError(404, "company_not_found", "Компания не найдена")
    if company.status == target.value:  # повтор решения не меняет результат
        return company
    if CompanyStatus(company.status) not in allowed:
        raise ProblemError(409, "invalid_status", "Переход статуса недопустим")
    company.status = target.value
    await session.flush()
    return company


async def verify(session: AsyncSession, company_id: uuid.UUID) -> Company:
    return await _moderate(session, company_id, CompanyStatus.verified, _VERIFY_FROM)


async def reject(session: AsyncSession, company_id: uuid.UUID) -> Company:
    return await _moderate(session, company_id, CompanyStatus.rejected, _REJECT_FROM)


async def get_company(session: AsyncSession, company_id: uuid.UUID) -> Company | None:
    """Компания без проверки доступа — для публичных блоков (оффер кандидату)."""
    return await session.get(Company, company_id)


async def member_user_ids(session: AsyncSession, company_id: uuid.UUID) -> list[uuid.UUID]:
    """Все участники компании — адресаты уведомлений по офферам."""
    rows = await session.scalars(
        select(CompanyMember.user_id).where(CompanyMember.company_id == company_id)
    )
    return list(rows)


# --- E39-24: команда компании (владелец = `admin`, HR = `member`) и приглашения по ссылке ---

INVITE_TTL = timedelta(days=7)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _pending(invite: CompanyInvite, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return (
        invite.accepted_at is None and invite.revoked_at is None and _aware(invite.expires_at) > now
    )


@dataclass(frozen=True)
class MemberView:
    user_id: uuid.UUID
    role: str
    email: str | None
    full_name: str | None
    position: str | None
    avatar_url: str | None


async def list_members(session: AsyncSession, company_id: uuid.UUID) -> list[MemberView]:
    """Участники компании: владелец первым, дальше HR по ФИО/email."""
    rows = (
        await session.execute(
            select(CompanyMember, User, UserProfile)
            .join(User, User.id == CompanyMember.user_id)
            .outerjoin(UserProfile, UserProfile.user_id == CompanyMember.user_id)
            .where(CompanyMember.company_id == company_id, User.deleted_at.is_(None))
        )
    ).all()
    out = [
        MemberView(
            user_id=m.user_id,
            role=m.role,
            email=u.email,
            full_name=p.full_name if p else None,
            position=p.position if p else None,
            avatar_url=profile.avatar_url(m.user_id, p.avatar_key if p else None),
        )
        for m, u, p in rows
    ]
    out.sort(key=lambda v: (v.role != CompanyMemberRole.admin.value, v.full_name or v.email or ""))
    return out


async def list_invites(session: AsyncSession, company_id: uuid.UUID) -> list[CompanyInvite]:
    rows = await session.scalars(
        select(CompanyInvite)
        .where(CompanyInvite.company_id == company_id)
        .order_by(CompanyInvite.created_at.desc(), CompanyInvite.id)
    )
    now = datetime.now(UTC)
    return [i for i in rows if _pending(i, now)]


async def create_invite(
    session: AsyncSession, company: Company, inviter: User, email: str
) -> tuple[CompanyInvite, str]:
    """Новое приглашение HR. Повтор на тот же email отзывает прежнюю ссылку и выдаёт новую."""
    email = normalize_email(email)
    member = await session.scalar(
        select(CompanyMember)
        .join(User, User.id == CompanyMember.user_id)
        .where(CompanyMember.company_id == company.id, User.email == email)
    )
    if member is not None:
        raise ProblemError(409, "already_member", "Этот человек уже в команде")
    now = datetime.now(UTC)
    for old in await session.scalars(
        select(CompanyInvite).where(
            CompanyInvite.company_id == company.id,
            CompanyInvite.email == email,
            CompanyInvite.accepted_at.is_(None),
            CompanyInvite.revoked_at.is_(None),
        )
    ):
        old.revoked_at = now
    token = secrets.token_urlsafe(32)
    invite = CompanyInvite(
        company_id=company.id,
        email=email,
        role=CompanyMemberRole.member.value,
        token_hash=hash_token(token),
        invited_by=inviter.id,
        created_at=now,
        expires_at=now + INVITE_TTL,
    )
    session.add(invite)
    await session.flush()
    return invite, token


async def revoke_invite(session: AsyncSession, company_id: uuid.UUID, invite_id: uuid.UUID) -> None:
    """Отзыв ссылки; чужое или несуществующее приглашение — 404, повтор — no-op."""
    invite = await session.get(CompanyInvite, invite_id)
    if invite is None or invite.company_id != company_id or invite.accepted_at is not None:
        raise ProblemError(404, "invite_not_found", "Приглашение не найдено")
    if invite.revoked_at is None:
        invite.revoked_at = datetime.now(UTC)
        await session.flush()


async def invite_by_token(session: AsyncSession, token: str) -> CompanyInvite:
    """Действующее приглашение по токену ссылки; иначе 404 (неверный, отозван, истёк, принят)."""
    invite = await session.scalar(
        select(CompanyInvite).where(CompanyInvite.token_hash == hash_token(token))
    )
    if invite is None or not _pending(invite):
        raise ProblemError(404, "invite_not_found", "Приглашение не найдено или истекло")
    return invite


async def accept_invite(session: AsyncSession, user: User, token: str) -> Company:
    """Принять приглашение: email аккаунта должен совпасть с адресом приглашения."""
    invite = await invite_by_token(session, token)
    if normalize_email(user.email or "") != invite.email:
        raise ProblemError(403, "invite_email_mismatch", "Приглашение отправлено на другой email")
    existing = await membership(session, user.id)
    if existing is not None and existing.company_id != invite.company_id:
        raise ProblemError(409, "already_member", "Вы уже состоите в другой компании")
    if existing is None:
        session.add(CompanyMember(company_id=invite.company_id, user_id=user.id, role=invite.role))
    invite.accepted_at = datetime.now(UTC)
    invite.accepted_by = user.id
    try:
        await session.flush()
    except IntegrityError as exc:  # параллельное принятие другого приглашения
        raise ProblemError(409, "already_member", "Вы уже состоите в другой компании") from exc
    company = await session.get(Company, invite.company_id)
    if company is None:
        raise ProblemError(404, "invite_not_found", "Приглашение не найдено или истекло")
    return company


async def remove_member(session: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Убрать HR из команды. Чужой участник — 404; владельца убрать нельзя — 409."""
    member = await session.get(CompanyMember, (company_id, user_id))
    if member is None:
        raise ProblemError(404, "member_not_found", "Участник не найден")
    if member.role == CompanyMemberRole.admin.value:
        raise ProblemError(409, "owner_cannot_be_removed", "Владельца нельзя убрать из компании")
    await session.delete(member)
    await session.flush()
