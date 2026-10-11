"""Фабрики кандидата и теста."""

import uuid

from fsp_contracts.assessment import TestGrade
from sqlalchemy.ext.asyncio import AsyncSession

from .base import make_candidate, make_grade


async def make_graded_candidate(
    session: AsyncSession,
    grades: dict[str, TestGrade | str] | None = None,
    **kw,
) -> tuple[uuid.UUID, list]:
    """Кандидат с грейдами `{profession: grade}` (по умолчанию backend/middle)."""
    cand = await make_candidate(session, **kw)
    rows = [
        await make_grade(session, cand.user_id, prof, grade)
        for prof, grade in (grades or {"backend": TestGrade.middle}).items()
    ]
    return cand.user_id, rows
