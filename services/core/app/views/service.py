"""Журнал просмотров карточек: запись и агрегаты для кандидата (без названий компаний)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.views.models import ProfileView

SOURCES = ("search", "match", "similar", "direct")
WINDOW_DAYS = 30


async def record(
    session: AsyncSession,
    *,
    candidate_id: uuid.UUID,
    company_id: uuid.UUID,
    viewer_user_id: uuid.UUID,
    source: str,
    vacancy_id: uuid.UUID | None,
) -> None:
    session.add(
        ProfileView(
            candidate_id=candidate_id, company_id=company_id, viewer_user_id=viewer_user_id,
            source=source, vacancy_id=vacancy_id,
        )
    )  # fmt: skip
    await session.flush()


async def stats(
    session: AsyncSession, candidate_id: uuid.UUID, now: datetime | None = None
) -> dict:
    """`{total_30d, companies_30d, by_day[]}` — только числа, компании не называются."""
    now = now or datetime.now(UTC)
    since = now - timedelta(days=WINDOW_DAYS)
    rows = (
        await session.execute(
            select(ProfileView.viewed_at, ProfileView.company_id).where(
                ProfileView.candidate_id == candidate_id, ProfileView.viewed_at >= since
            )
        )
    ).all()
    per_day: dict[str, int] = {}
    for at, _ in rows:
        day = (at if at.tzinfo else at.replace(tzinfo=UTC)).astimezone(UTC).date().isoformat()
        per_day[day] = per_day.get(day, 0) + 1
    return {
        "total_30d": len(rows),
        "companies_30d": len({c for _, c in rows if c is not None}),
        "by_day": [{"date": d, "count": n} for d, n in sorted(per_day.items())],
    }


__all__ = ["SOURCES", "record", "stats"]
