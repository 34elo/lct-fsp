"""Базовые фабрики (blocks.md §5.8): user, candidate, company, vacancy, grade.

Меняются только по заявке. Функции принимают `AsyncSession`, делают `flush`; коммитит вызывающий.
"""

import uuid
from datetime import UTC, datetime

from app.assessment import service as assessment
from app.candidates.models import Candidate
from app.companies.models import Company, CompanyMember
from app.identity.models import User
from app.vacancies.models import Vacancy
from fsp_contracts.assessment import TestGrade
from sqlalchemy.ext.asyncio import AsyncSession

GRADE_THETA = {  # θ в середине полосы грейда (blocks.md §4.2)
    TestGrade.junior: -1.0,
    TestGrade.middle: 0.0,
    TestGrade.senior: 1.0,
}


async def make_user(
    session: AsyncSession, role: str = "candidate", *, verified: bool = True, **kw
) -> User:
    uid = kw.pop("id", None) or uuid.uuid4()
    user = User(
        id=uid,
        email=kw.pop("email", f"{uid.hex}@example.test"),
        password_hash="x",  # войти по паролю нельзя; для API — `helpers.register`
        role=role,
        email_verified_at=datetime.now(UTC) if verified else None,
        **kw,
    )
    session.add(user)
    await session.flush()
    return user


async def make_candidate(session: AsyncSession, **kw) -> Candidate:
    user = await make_user(session, "candidate", id=kw.pop("user_id", None))
    cand = Candidate(
        user_id=user.id,
        pseudonym=kw.pop("pseudonym", f"P{user.id.hex}"),
        pseudo_id=kw.pop("pseudo_id", user.id.hex[:12]),
        **kw,
    )
    session.add(cand)
    await session.flush()
    return cand


async def make_company(
    session: AsyncSession, *, status: str = "verified", **kw
) -> tuple[Company, User]:
    """Компания с владельцем-работодателем. Возвращает `(company, owner)`."""
    owner = await make_user(session, "employer")
    company = Company(name=kw.pop("name", "Acme Labs"), status=status, **kw)
    session.add(company)
    await session.flush()
    session.add(CompanyMember(company_id=company.id, user_id=owner.id, role="admin"))
    await session.flush()
    return company, owner


async def make_vacancy(session: AsyncSession, company: Company, **kw) -> Vacancy:
    data = {
        "title": "Backend-разработчик",
        "role": "backend",
        "grade_min": "junior",
        "grade_max": "senior",
        "formats": ["remote"],
        "employment_type": "full",
        "salary_from": 150_000,
        "salary_to": 250_000,
        "status": "published",
        "created_by": None,
    }
    data.update(kw)
    vac = Vacancy(company_id=company.id, **data)
    session.add(vac)
    await session.flush()
    return vac


async def make_grade(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    profession: str = "backend",
    grade: TestGrade | str = TestGrade.middle,
    theta: float | None = None,
    **kw,
):
    """Грейд кандидата через `assessment.service.seed_grade` (source="seed", событие в outbox)."""
    if theta is None:
        theta = GRADE_THETA[TestGrade(grade)]
    return await assessment.seed_grade(session, candidate_id, profession, grade, theta, **kw)
