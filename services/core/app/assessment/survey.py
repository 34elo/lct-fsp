"""Опрос кандидата: отрасль → профессия → стек → формат → вилка → заявленный грейд (E22-7).

История — новые строки `surveys`; идентичный последнему опрос не дублируется. Пока опроса нет,
`GET` предзаполняет его из резюме/анкеты (профессия, стек, формат, вилка, грейд).
"""

from __future__ import annotations

import uuid
from typing import Any

from fsp_contracts.assessment import TEST_GRADE_ORDER, TestGrade
from fsp_contracts.enums import WorkFormat
from fsp_platform.app import ProblemError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import track
from app.assessment.models import Survey
from app.candidates.models import Candidate
from app.taxonomy import service as taxonomy

MAX_STACK = 30
_FIELDS = (
    "industry",
    "profession",
    "stack",
    "formats",
    "salary_from",
    "salary_to",
    "declared_grade",
)


def _clean_stack(stack: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for s in stack:
        s = s.strip().lower()
        if s:
            seen.setdefault(s[:64], None)
    return list(seen)[:MAX_STACK]


def snapshot(row: Survey) -> dict[str, Any]:
    return {f: getattr(row, f) for f in _FIELDS}


async def last_survey(
    session: AsyncSession, candidate_id: uuid.UUID, profession: str | None = None
) -> Survey | None:
    q = select(Survey).where(Survey.candidate_id == candidate_id)
    if profession:
        q = q.where(Survey.profession == profession)
    return await session.scalar(q.order_by(Survey.created_at.desc(), Survey.id.desc()).limit(1))


async def declared_grades(session: AsyncSession, candidate_id: uuid.UUID) -> dict[str, TestGrade]:
    """Профессия → заявленный грейд из последнего опроса по этой профессии."""
    rows = await session.scalars(
        select(Survey)
        .where(Survey.candidate_id == candidate_id, Survey.declared_grade.is_not(None))
        .order_by(Survey.created_at, Survey.id)
    )
    return {r.profession: TestGrade(r.declared_grade) for r in rows}  # type: ignore[arg-type]


async def save_survey(
    session: AsyncSession, candidate_id: uuid.UUID, data: dict[str, Any]
) -> tuple[Survey, bool]:
    """Сохраняет опрос; возвращает `(строка, создана_новая)`."""
    professions = {p.slug for p in await taxonomy.list_professions(session)}
    if data["profession"] not in professions:
        raise ProblemError(422, code="unknown_profession", title="Неизвестная профессия")
    sf, st = data.get("salary_from"), data.get("salary_to")
    if sf is not None and st is not None and sf > st:
        raise ProblemError(422, code="invalid_salary_range", title="Вилка: «от» больше «до»")
    data = {
        **data,
        "stack": _clean_stack(data.get("stack") or []),
        "formats": sorted(set(data.get("formats") or [])),
    }
    last = await last_survey(session, candidate_id)
    if last is not None and snapshot(last) == {f: data.get(f) for f in _FIELDS}:
        return last, False
    row = Survey(candidate_id=candidate_id, **{f: data.get(f) for f in _FIELDS})
    session.add(row)
    await session.flush()
    await track.emit(
        session,
        "survey_saved",
        candidate_id,
        {
            "profession": data["profession"],
            "declared_grade": data.get("declared_grade"),
            "stack_size": len(data["stack"]),
            "formats_count": len(data["formats"]),
            "has_salary": sf is not None or st is not None,
        },
    )
    return row, True


def prefill(cand: Candidate | None, professions: set[str]) -> dict[str, Any] | None:
    """Черновик опроса из анкеты/резюме; `None`, если брать нечего."""
    if cand is None:
        return None
    grade = cand.grade if cand.grade in {g.value for g in TEST_GRADE_ORDER} else None
    formats = [f for f in (cand.formats or []) if f in {w.value for w in WorkFormat}]
    profession = cand.primary_role if cand.primary_role in professions else None
    out = {
        "industry": None,
        "profession": profession,
        "stack": list(cand.primary_stack or [])[:MAX_STACK],
        "formats": formats,
        "salary_from": cand.salary_min,
        "salary_to": None,
        "declared_grade": grade,
    }
    if not (profession or out["stack"] or formats or cand.salary_min or grade):
        return None
    return out
