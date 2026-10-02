from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fsp_contracts.enums import EmploymentType, Grade, RoleSlug, TeamSignalKind, WorkFormat
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.identity.deps import require_roles
from app.identity.models import User
from app.vacancies import service
from app.vacancies.models import Vacancy
from app.vacancies.service import SkillReq, VacancyStatus

router = APIRouter(prefix="/vacancies", tags=["vacancies"])

_employer = require_roles("employer")


class SkillReqIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=100)
    required: bool = True
    min_level: int = Field(default=2, ge=1, le=4)
    weight: float = Field(default=1.0, gt=0, le=3)


class SkillReqOut(BaseModel):
    slug: str
    required: bool
    min_level: int
    weight: float


class VacancyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=200)
    role: RoleSlug
    grade_min: Grade
    grade_max: Grade
    formats: list[WorkFormat] = Field(min_length=1, max_length=3)
    employment_type: EmploymentType
    city: str | None = Field(default=None, max_length=100)
    salary_from: int = Field(gt=0, le=100_000_000)
    salary_to: int = Field(gt=0, le=100_000_000)
    description: str | None = Field(default=None, max_length=10000)
    important_qualities: list[TeamSignalKind] = Field(default_factory=list, max_length=4)
    skills: list[SkillReqIn] = Field(default_factory=list, max_length=40)


class VacancyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=2, max_length=200)
    role: RoleSlug | None = None
    grade_min: Grade | None = None
    grade_max: Grade | None = None
    formats: list[WorkFormat] | None = Field(default=None, min_length=1, max_length=3)
    employment_type: EmploymentType | None = None
    city: str | None = Field(default=None, max_length=100)
    salary_from: int | None = Field(default=None, gt=0, le=100_000_000)
    salary_to: int | None = Field(default=None, gt=0, le=100_000_000)
    description: str | None = Field(default=None, max_length=10000)
    important_qualities: list[TeamSignalKind] | None = Field(default=None, max_length=4)
    skills: list[SkillReqIn] | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def _no_null_required(self) -> VacancyPatch:
        for name in self.model_fields_set - {"city", "description"}:
            if getattr(self, name) is None:
                raise ValueError(f"{name} не может быть null")
        return self


class VacancyOut(BaseModel):
    id: UUID
    company_id: UUID
    title: str
    role: RoleSlug
    grade_min: Grade
    grade_max: Grade
    formats: list[WorkFormat]
    employment_type: EmploymentType
    city: str | None
    salary_from: int
    salary_to: int
    range_too_wide: bool
    description: str | None
    status: VacancyStatus
    important_qualities: list[TeamSignalKind]
    skills: list[SkillReqOut]
    version: int
    created_at: datetime
    published_at: datetime | None


def vacancy_out(v: Vacancy, skills: list) -> VacancyOut:
    return VacancyOut(
        id=v.id,
        company_id=v.company_id,
        title=v.title,
        role=RoleSlug(v.role),
        grade_min=Grade(v.grade_min),
        grade_max=Grade(v.grade_max),
        formats=[WorkFormat(f) for f in v.formats],
        employment_type=EmploymentType(v.employment_type),
        city=v.city,
        salary_from=v.salary_from,
        salary_to=v.salary_to,
        range_too_wide=service.range_too_wide(v.salary_from, v.salary_to),
        description=v.description,
        status=VacancyStatus(v.status),
        important_qualities=[TeamSignalKind(q) for q in v.important_qualities],
        skills=[
            SkillReqOut(slug=slug, required=s.required, min_level=s.min_level, weight=s.weight)
            for s, slug in skills
        ],
        version=v.version,
        created_at=v.created_at,
        published_at=v.published_at,
    )


async def _out(session: AsyncSession, v: Vacancy) -> VacancyOut:
    return vacancy_out(v, (await service.skills_of(session, [v.id]))[v.id])


def _reqs(items: list[SkillReqIn]) -> list[SkillReq]:
    return [SkillReq(**i.model_dump()) for i in items]


@router.post("", response_model=VacancyOut, status_code=201)
async def create_vacancy(
    body: VacancyIn,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    fields = body.model_dump(mode="json", exclude={"skills"})
    v = await service.create(session, user, fields, _reqs(body.skills))
    return await _out(session, v)


@router.get("", response_model=list[VacancyOut])
async def list_vacancies(
    status: VacancyStatus | None = None,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    items = await service.list_owned(session, user, status.value if status else None)
    skills = await service.skills_of(session, [v.id for v in items])
    return [vacancy_out(v, skills[v.id]) for v in items]


@router.get("/{vacancy_id}", response_model=VacancyOut)
async def get_vacancy(
    vacancy_id: UUID,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    return await _out(session, await service.get_owned(session, user, vacancy_id))


@router.patch("/{vacancy_id}", response_model=VacancyOut)
async def patch_vacancy(
    vacancy_id: UUID,
    body: VacancyPatch,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    changes = body.model_dump(mode="json", exclude_unset=True, exclude={"skills"})
    skills = _reqs(body.skills) if body.skills is not None else None
    v = await service.update(session, user, vacancy_id, changes, skills)
    return await _out(session, v)


@router.delete("/{vacancy_id}", status_code=204)
async def delete_vacancy(
    vacancy_id: UUID,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    await service.delete_draft(session, user, vacancy_id)
    return Response(status_code=204)


@router.post("/{vacancy_id}/publish", response_model=VacancyOut)
async def publish_vacancy(
    vacancy_id: UUID,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    return await _out(session, await service.publish(session, user, vacancy_id))


@router.post("/{vacancy_id}/close", response_model=VacancyOut)
async def close_vacancy(
    vacancy_id: UUID,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    return await _out(session, await service.close(session, user, vacancy_id))
