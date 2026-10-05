from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fsp_contracts.enums import CompanyMemberRole, CompanyStatus
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies import service
from app.companies.models import Company
from app.deps import get_session
from app.identity.deps import require_roles
from app.identity.models import User
from app.openapi_errors import problem_responses

router = APIRouter(tags=["companies"])
admin_router = APIRouter(prefix="/admin/companies", tags=["admin"])

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
    logo_key: str | None
    contacts: dict[str, Any] | None
    direction: str | None
    status: CompanyStatus
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


class CompanyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=200)
    inn: str | None = Field(default=None, pattern=r"^(\d{10}|\d{12})$")
    site: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    contacts: Contacts | None = Field(default=None)
    direction: str | None = Field(default=None, max_length=1000)


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
        logo_key=c.logo_key,
        contacts=c.contacts,
        direction=c.direction,
        status=CompanyStatus(c.status),
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
    if changes.get("name") is None:
        changes.pop("name", None)
    await service.update_company(session, company, changes)
    return company_out(company, member.role)


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
