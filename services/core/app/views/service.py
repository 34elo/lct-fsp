"""Журнал просмотров карточек: запись и агрегаты для кандидата (без названий компаний)."""

from __future__ import annotations

import html
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
    session: AsyncSession,
    candidate_id: uuid.UUID,
    now: datetime | None = None,
    *,
    visible: bool = False,
) -> dict:
    """`{total_30d, companies_30d, window_days, visible, by_day[]}` — только числа, компании не
    называются. `by_day` — полная шкала `WINDOW_DAYS` дней (нули для дней без просмотров, E43-5)."""
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
    today = now.astimezone(UTC).date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(WINDOW_DAYS - 1, -1, -1)]
    return {
        "total_30d": len(rows),
        "companies_30d": len({c for _, c in rows if c is not None}),
        "window_days": WINDOW_DAYS,
        "visible": visible,
        "by_day": [{"date": d, "count": per_day.get(d, 0)} for d in days],
    }


def generate_badge_svg(profession: str, grade: str, integrity: float = 1.0) -> str:
    """Генерирует SVG бейдж «Подтверждено ФСП · Профессия · Грейд · ●●●●».

    Args:
        profession: Slug профессии (e.g., 'backend')
        grade: Грейд (junior|middle|senior)
        integrity: Коэффициент честности 0..1, определяет заполненность кружков

    Returns:
        SVG-контент
    """
    # Формируем текст профессии с большой буквы и заменяем _ на пробелы
    profession_title = html.escape(profession.replace("_", " ").title())
    grade_title = html.escape(grade.title())

    # Определяем количество заполненных кружков (от 0 до 4)
    filled_dots = int(round(integrity * 4))
    filled_dots = max(0, min(4, filled_dots))  # Зажимаем между 0 и 4

    # Создаём кружки
    dots = ""
    for i in range(4):
        if i < filled_dots:
            # Заполненный кружок
            dots += f'<circle cx="{300 + i * 25}" cy="40" r="6" fill="#000" />'
        else:
            # Пустой кружок
            dots += (
                f'<circle cx="{300 + i * 25}" cy="40" r="6" fill="none" '
                'stroke="#ddd" stroke-width="2" />'
            )

    # SVG шаблон
    svg = f"""<svg width="400" height="80" xmlns="http://www.w3.org/2000/svg">
  <style>
    text {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    .title {{ font-size: 16px; font-weight: bold; }}
    .subtitle {{ font-size: 12px; fill: #666; }}
  </style>

  <rect width="400" height="80" fill="#fff" stroke="#e0e0e0" stroke-width="1" rx="8" />

  <!-- Заголовок -->
  <text x="12" y="25" class="title">Подтверждено ФСП</text>

  <!-- Профессия и грейд -->
  <text x="12" y="45" class="subtitle">{profession_title} · {grade_title}</text>

  <!-- Кружки честности -->
  {dots}
</svg>"""

    return svg


__all__ = ["SOURCES", "record", "stats", "generate_badge_svg"]
