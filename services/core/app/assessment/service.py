"""Публичное API блока 1 для блока 2 (blocks.md §4.3). Сигнатуры заморожены.

Функции не делают `commit`: транзакцией управляет вызывающий. Читают только таблицу `grades`
(и `candidates` для заявленного); `surveys`/`attempts` есть (E22-7).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from fsp_contracts.assessment import (
    TEST_GRADE_ORDER,
    CandidateGrade,
    CategoryChanged,
    CategoryRef,
    ClaimedVsConfirmed,
    TestGrade,
)
from fsp_contracts.registry import new_event
from fsp_platform.outbox import add_to_outbox
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import survey
from app.assessment.models import Grade
from app.candidates.models import Candidate

PRODUCER = "core"
GRADE_VALIDITY = timedelta(days=365)  # срок грейда: 12 месяцев (blocks.md §4.2)
GRADE_COOLDOWN = timedelta(
    days=30
)  # ближайшая смена; точное значение — assessment.md / scoring.yaml


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _dto(row: Grade) -> CandidateGrade:
    return CandidateGrade(
        candidate_id=row.candidate_id,
        profession=row.profession,
        grade=TestGrade(row.grade),
        theta=row.theta,
        se=row.se,
        band_position=row.band_position,
        theta_by_type=row.theta_by_type or {},
        integrity=row.integrity,
        needs_confirmation=row.needs_confirmation,
        low_confidence=row.low_confidence,
        source=row.source,  # type: ignore[arg-type]
        attempt_id=row.attempt_id,
        confirmed_at=_aware(row.confirmed_at),
        valid_until=_aware(row.valid_until),
        next_change_at=_aware(row.next_change_at),
    )


def _active(now: datetime | None = None):
    return Grade.valid_until > (now or datetime.now(UTC))


async def get_grades(session: AsyncSession, candidate_id: uuid.UUID) -> list[CandidateGrade]:
    """Только действующие грейды (`valid_until > now()`), по профессии."""
    rows = await session.scalars(
        select(Grade)
        .where(Grade.candidate_id == candidate_id, _active())
        .order_by(Grade.profession)
    )
    return [_dto(r) for r in rows]


async def get_grades_many(
    session: AsyncSession, candidate_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[CandidateGrade]]:
    """То же пачкой (без N+1). Кандидатов без действующих грейдов в словаре нет."""
    ids = list(set(candidate_ids))
    out: dict[uuid.UUID, list[CandidateGrade]] = {}
    if not ids:
        return out
    rows = await session.scalars(
        select(Grade)
        .where(Grade.candidate_id.in_(ids), _active())
        .order_by(Grade.candidate_id, Grade.profession)
    )
    for r in rows:
        out.setdefault(r.candidate_id, []).append(_dto(r))
    return out


async def get_grade(
    session: AsyncSession, candidate_id: uuid.UUID, profession: str
) -> CandidateGrade | None:
    row = await session.scalar(
        select(Grade).where(
            Grade.candidate_id == candidate_id, Grade.profession == profession, _active()
        )
    )
    return _dto(row) if row else None


async def category_members(
    session: AsyncSession, profession: str, grade: TestGrade | str
) -> list[uuid.UUID]:
    """Кандидаты с действующим грейдом ровно `grade`. Согласия и видимость фильтрует Б2."""
    rows = await session.scalars(
        select(Grade.candidate_id)
        .where(Grade.profession == profession, Grade.grade == str(grade), _active())
        .order_by(Grade.candidate_id)
    )
    return list(rows)


async def category_counts(session: AsyncSession) -> dict[tuple[str, str], int]:
    """`(profession, grade) → число` действующих грейдов, без учёта согласий."""
    rows = await session.execute(
        select(Grade.profession, Grade.grade, func.count())
        .where(_active())
        .group_by(Grade.profession, Grade.grade)
    )
    return {(p, g): n for p, g, n in rows}


def _rank(grade: str) -> int | None:
    try:
        return TEST_GRADE_ORDER.index(TestGrade(grade))
    except ValueError:
        return None


async def claimed_vs_confirmed(
    session: AsyncSession, candidate_id: uuid.UUID
) -> list[ClaimedVsConfirmed]:
    """По каждой профессии из грейдов и резюме: заявлено против подтверждённого.

    Заявленное — последний опрос (`declared_grade`) по профессии; из резюме — `candidates.grade`
    по `primary_role` (старая шкала).
    Сравнение идёт с `declared_grade`, а без него — с `resume_grade`, если он junior/middle/senior.
    """
    grades = {g.profession: g for g in await get_grades(session, candidate_id)}
    cand = await session.get(Candidate, candidate_id)
    resume: dict[str, str] = {}
    if cand and cand.primary_role and cand.grade:
        resume[cand.primary_role] = cand.grade
    declared = await survey.declared_grades(session, candidate_id)

    out: list[ClaimedVsConfirmed] = []
    for prof in sorted(set(grades) | set(resume) | set(declared)):
        confirmed = TestGrade(grades[prof].grade) if prof in grades else None
        decl = declared.get(prof)
        res = resume.get(prof)
        claim = decl.value if decl else res
        c_rank, k_rank = (
            (_rank(confirmed.value) if confirmed else None),
            (_rank(claim) if claim else None),
        )
        if confirmed is None:
            status = "unconfirmed"
        elif k_rank is None or c_rank is None or k_rank == c_rank:
            status = "confirmed"
        else:
            status = "overclaimed" if k_rank > c_rank else "underclaimed"
        out.append(
            ClaimedVsConfirmed(
                profession=prof,
                declared_grade=decl,
                resume_grade=res,
                confirmed_grade=confirmed,
                status=status,  # type: ignore[arg-type]
            )
        )
    return out


async def last_activity_at(session: AsyncSession, candidate_id: uuid.UUID) -> datetime | None:
    """Последний завершённый тест или регулярное задание (для свежести R).

    Пока `attempts`/`task_submissions` нет (блок 1), берём `confirmed_at` грейдов любого срока.
    """
    ts = await session.scalar(
        select(func.max(Grade.confirmed_at)).where(Grade.candidate_id == candidate_id)
    )
    return _aware(ts) if ts else None


async def seed_grade(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    profession: str,
    grade: TestGrade | str,
    theta: float,
    *,
    integrity: float = 1.0,
    needs_confirmation: bool = False,
    now: datetime | None = None,
) -> CandidateGrade:
    """ТОЛЬКО seed и тесты: upsert с `source="seed"` и событие `candidate.category.changed`."""
    now = now or datetime.now(UTC)
    grade = TestGrade(grade)
    band = _band_position(grade, theta)
    row = await session.get(Grade, (candidate_id, profession))
    if row is None:
        row = Grade(candidate_id=candidate_id, profession=profession)
        session.add(row)
    row.grade = grade.value
    row.theta = theta
    row.se = None
    row.band_position = band
    row.theta_by_type = {}
    row.integrity = integrity
    row.needs_confirmation = needs_confirmation
    row.low_confidence = False
    row.source = "seed"
    row.attempt_id = None
    row.confirmed_at = now
    row.valid_until = now + GRADE_VALIDITY
    row.next_change_at = now + GRADE_COOLDOWN
    row.updated_at = now
    await session.flush()

    categories = [
        CategoryRef(profession=g.profession, grade=g.grade)
        for g in await _active_after(session, candidate_id, now)
    ]
    cand = await session.get(Candidate, candidate_id)
    event = CategoryChanged(
        candidate_id=candidate_id,
        categories=categories,
        profile_version=cand.profile_version if cand else 0,
    )
    await add_to_outbox(
        session, new_event("candidate.category.changed", PRODUCER, event), candidate_id
    )
    return _dto(row)


async def _active_after(
    session: AsyncSession, candidate_id: uuid.UUID, now: datetime
) -> list[CandidateGrade]:
    rows = await session.scalars(
        select(Grade)
        .where(Grade.candidate_id == candidate_id, _active(now))
        .order_by(Grade.profession)
    )
    return [_dto(r) for r in rows]


# cut_g — нижняя граница полосы грейда на шкале θ (assessment.md §9); у senior ширина 1.0.
_CUT = {TestGrade.junior: -1.0, TestGrade.middle: 0.0, TestGrade.senior: 1.0}


def _band_position(grade: TestGrade, theta: float) -> float:
    """T = clamp((θ − cut_g) / (cut_{g+1} − cut_g), 0, 1); формула assessment.md §9."""
    idx = TEST_GRADE_ORDER.index(grade)
    lo = _CUT[grade]
    hi = _CUT[TEST_GRADE_ORDER[idx + 1]] if idx + 1 < len(TEST_GRADE_ORDER) else lo + 1.0
    return min(1.0, max(0.0, (theta - lo) / (hi - lo)))
