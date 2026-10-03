"""Компании: регистрация, участники, модерация (статусы — `CompanyStatus`)."""

from __future__ import annotations

import uuid

from fsp_contracts.enums import CompanyMemberRole, CompanyStatus
from fsp_platform.app import ProblemError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies.models import Company, CompanyMember
from app.identity.models import User
from app.identity.service import normalize_email

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
