"""Вакансии: CRUD, публикация, закрытие. Доступ только участникам компании-владельца
(чужая вакансия → 404). Публиковать может лишь `verified` компания.

Версия `version` растёт при каждом изменении содержимого; события `vacancy.*` (messaging.md)
уходят в outbox в той же транзакции — для опубликованной вакансии.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from fsp_contracts import new_envelope
from fsp_contracts.enums import CompanyStatus, Grade
from fsp_contracts.events import VacancyEvent
from fsp_platform.app import ProblemError
from fsp_platform.outbox import add_to_outbox
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies import service as companies
from app.identity.models import User
from app.taxonomy.models import Skill
from app.vacancies.models import Vacancy, VacancySkill

RANGE_TOO_WIDE_RATIO = 1.6  # ml.md §7: salary_to / salary_from


class VacancyStatus(StrEnum):
    draft = "draft"
    published = "published"
    closed = "closed"


@dataclass(frozen=True, slots=True)
class SkillReq:
    slug: str
    required: bool = True
    min_level: int = 2
    weight: float = 1.0


def range_too_wide(salary_from: int, salary_to: int) -> bool:
    return salary_from > 0 and salary_to / salary_from > RANGE_TOO_WIDE_RATIO


def _not_found() -> ProblemError:
    return ProblemError(404, "vacancy_not_found", "Вакансия не найдена")


async def _resolve_skills(session: AsyncSession, reqs: list[SkillReq]) -> list[VacancySkill]:
    slugs = [r.slug for r in reqs]
    if len(set(slugs)) != len(slugs):
        raise ProblemError(422, "duplicate_skill", "Навык указан дважды")
    rows = {s.slug: s for s in (await session.scalars(select(Skill).where(Skill.slug.in_(slugs))))}
    out: dict[uuid.UUID, VacancySkill] = {}
    missing: list[dict[str, str]] = []
    for r in reqs:
        skill = rows.get(r.slug)
        if skill is not None and skill.status == "merged" and skill.merged_into:
            skill = await session.get(Skill, skill.merged_into)
        if skill is None or skill.status == "rejected":
            missing.append({"field": "skills", "message": f"неизвестный навык: {r.slug}"})
            continue
        if skill.id in out:  # два синонима слились в один навык
            raise ProblemError(422, "duplicate_skill", "Навык указан дважды")
        out[skill.id] = VacancySkill(
            skill_id=skill.id, required=r.required, min_level=r.min_level, weight=r.weight
        )
    if missing:
        raise ProblemError(422, "unknown_skill", "Неизвестный навык", errors=missing)
    return list(out.values())


async def _emit(session: AsyncSession, name: str, v: Vacancy) -> None:
    event = VacancyEvent(vacancy_id=v.id, version=v.version)
    await add_to_outbox(session, new_envelope(name, "core", event), v.company_id)


async def get_owned(session: AsyncSession, user: User, vacancy_id: uuid.UUID) -> Vacancy:
    company, _ = await companies.require_company(session, user.id)
    v = await session.get(Vacancy, vacancy_id)
    if v is None or v.company_id != company.id:
        raise _not_found()
    return v


async def get(session: AsyncSession, vacancy_id: uuid.UUID) -> Vacancy | None:
    """Вакансия без проверки владельца — для внутренних модулей (подбор)."""
    return await session.get(Vacancy, vacancy_id)


async def skills_of(session: AsyncSession, vacancy_ids: list[uuid.UUID]) -> dict:
    """{vacancy_id: [(VacancySkill, slug)]} — навыки по порядку весов."""
    out: dict[uuid.UUID, list[tuple[VacancySkill, str]]] = {i: [] for i in vacancy_ids}
    if not vacancy_ids:
        return out
    q = (
        select(VacancySkill, Skill.slug)
        .join(Skill, Skill.id == VacancySkill.skill_id)
        .where(VacancySkill.vacancy_id.in_(vacancy_ids))
        .order_by(VacancySkill.required.desc(), Skill.slug)
    )
    for vs, slug in (await session.execute(q)).all():
        out[vs.vacancy_id].append((vs, slug))
    return out


async def create(
    session: AsyncSession, user: User, fields: dict, skills: list[SkillReq]
) -> Vacancy:
    company, _ = await companies.require_company(session, user.id)
    check_consistency(fields)
    resolved = await _resolve_skills(session, skills)
    v = Vacancy(**fields, company_id=company.id, created_by=user.id, status="draft", version=1)
    session.add(v)
    await session.flush()
    for vs in resolved:
        vs.vacancy_id = v.id
        session.add(vs)
    await session.flush()
    return v


async def list_owned(session: AsyncSession, user: User, status: str | None = None) -> list[Vacancy]:
    company, _ = await companies.require_company(session, user.id)
    q = select(Vacancy).where(Vacancy.company_id == company.id)
    if status is not None:
        q = q.where(Vacancy.status == status)
    return list((await session.scalars(q.order_by(Vacancy.created_at.desc(), Vacancy.id))).all())


async def update(
    session: AsyncSession,
    user: User,
    vacancy_id: uuid.UUID,
    changes: dict,
    skills: list[SkillReq] | None,
) -> Vacancy:
    v = await get_owned(session, user, vacancy_id)
    if v.status == VacancyStatus.closed:
        raise ProblemError(409, "invalid_status", "Закрытую вакансию нельзя изменить")

    check_consistency({**_snapshot(v), **changes})
    new_skills = await _resolve_skills(session, skills) if skills is not None else None
    if not changes and new_skills is None:
        return v
    for key, value in changes.items():
        setattr(v, key, value)
    if new_skills is not None:
        await session.execute(delete(VacancySkill).where(VacancySkill.vacancy_id == v.id))
        for vs in new_skills:
            vs.vacancy_id = v.id
            session.add(vs)
    v.version += 1
    await session.flush()
    if v.status == VacancyStatus.published:
        await _emit(session, "vacancy.updated", v)
    return v


async def delete_draft(session: AsyncSession, user: User, vacancy_id: uuid.UUID) -> None:
    v = await get_owned(session, user, vacancy_id)
    if v.status != VacancyStatus.draft:
        raise ProblemError(409, "invalid_status", "Удалить можно только черновик")
    await session.execute(delete(VacancySkill).where(VacancySkill.vacancy_id == v.id))
    await session.delete(v)
    await session.flush()


async def publish(session: AsyncSession, user: User, vacancy_id: uuid.UUID) -> Vacancy:
    v = await get_owned(session, user, vacancy_id)
    if v.status == VacancyStatus.published:  # повтор не меняет результат
        return v
    if v.status != VacancyStatus.draft:
        raise ProblemError(409, "invalid_status", "Переход статуса недопустим")
    company, _ = await companies.require_company(session, user.id)
    if company.status != CompanyStatus.verified.value:
        raise ProblemError(403, "company_not_verified", "Компания не прошла проверку")
    n_required = len(
        (
            await session.scalars(
                select(VacancySkill.skill_id).where(
                    VacancySkill.vacancy_id == v.id, VacancySkill.required.is_(True)
                )
            )
        ).all()
    )
    if n_required == 0:
        raise ProblemError(422, "no_required_skills", "Укажите хотя бы один обязательный навык")
    v.status = VacancyStatus.published.value
    v.published_at = datetime.now(UTC)
    v.version += 1
    await session.flush()
    await _emit(session, "vacancy.published", v)
    return v


async def close(session: AsyncSession, user: User, vacancy_id: uuid.UUID) -> Vacancy:
    v = await get_owned(session, user, vacancy_id)
    if v.status == VacancyStatus.closed:
        return v
    if v.status != VacancyStatus.published:
        raise ProblemError(409, "invalid_status", "Закрыть можно только опубликованную вакансию")
    v.status = VacancyStatus.closed.value
    v.version += 1
    await session.flush()
    await _emit(session, "vacancy.closed", v)
    return v


_SNAP = ("grade_min", "grade_max", "salary_from", "salary_to", "formats", "city")


def _snapshot(v: Vacancy) -> dict:
    return {k: getattr(v, k) for k in _SNAP}


def check_consistency(f: dict) -> None:
    """Проверки, зависящие от нескольких полей (грейды и вилка)."""
    order = [g.value for g in Grade]
    if order.index(str(f["grade_min"])) > order.index(str(f["grade_max"])):
        raise ProblemError(422, "invalid_grade_range", "grade_min выше grade_max")
    if f["salary_to"] < f["salary_from"]:
        raise ProblemError(422, "invalid_salary_range", "Вилка: salary_to меньше salary_from")
