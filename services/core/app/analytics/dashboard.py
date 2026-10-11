"""Дашборд ФСП: воронка и конверсия навигатор → соревнование.

Считаем по `analytics_events` на лету (десятки тысяч строк; без материализованных представлений,
так одинаково работает и в SQLite тестов). Только агрегаты по псевдонимам: ячейки меньше
`MIN_CELL` человек скрываются (`hidden=True`, число и доля `None`).
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from datetime import UTC, datetime, timedelta
from datetime import date as Date

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.models import AnalyticsEventRow as E

MIN_CELL = 5
DEFAULT_DAYS = 30
MAX_DAYS = 180

Pred = Callable[[str, dict], bool]

# Этап воронки: id, подпись, предикат по (event, props).
STAGES: list[tuple[str, str, Pred]] = [
    ("registered", "Регистрация", lambda e, p: e == "signup_completed"),
    ("test", "Прошли тест", lambda e, p: e == "test_completed"),
    (
        "category",
        "Получили категорию",
        lambda e, p: (
            e == "category_changed" or (e == "profile_updated" and bool(p.get("grade_to")))
        ),
    ),
    ("invited", "Получили приглашение", lambda e, p: e == "offer_received"),
    ("answered", "Ответили на приглашение", lambda e, p: e in ("offer_accepted", "offer_declined")),
]
_NAVIGATOR_SOURCES = ("navigator", "uplift")
_EVENTS = {
    "signup_completed", "test_completed", "category_changed", "profile_updated",
    "offer_received", "offer_accepted", "offer_declined", "fsp_link_completed",
    "uplift_shown", "competition_clicked", "interest_shown",
}  # fmt: skip

# Счётчики «Аналитики»: id, подпись, предикат. Считаем события, а не людей.
COUNTERS: list[tuple[str, str, Pred]] = [
    ("registrations", "Регистрации", lambda e, p: e == "signup_completed"),
    ("tests", "Пройденные тесты", lambda e, p: e == "test_completed"),
    (
        "grades",
        "Присвоенные грейды",
        lambda e, p: (
            e == "category_changed" or (e == "profile_updated" and bool(p.get("grade_to")))
        ),
    ),
    ("interests", "Интересы работодателей", lambda e, p: e == "interest_shown"),
    ("invites", "Приглашения", lambda e, p: e == "offer_received"),
    ("accepted", "Принятые приглашения", lambda e, p: e == "offer_accepted"),
]


class Cell(BaseModel):
    count: int | None  # None, если ячейка меньше MIN_CELL
    hidden: bool


class Stage(Cell):
    id: str
    title: str
    pct_of_registered: float | None
    pct_of_previous: float | None


class Ratio(Cell):
    """Доля: числитель `count` (уникальные люди) и `pct` от знаменателя `of`."""

    pct: float | None
    of: int | None


class Counter(Cell):
    id: str
    title: str


class DayPoint(BaseModel):
    """Один день: значения счётчиков по id; меньше `MIN_CELL` событий — `null`."""

    date: Date
    values: dict[str, int | None]


class DashboardOut(BaseModel):
    since: datetime
    days: int
    min_cell: int
    funnel: list[Stage]
    fsp_share: Ratio  # доля зарегистрированных с привязанным ФСП
    navigator_to_competition: Ratio  # кликнувшие на соревнование / увидевшие подсказку
    counters: list[Counter] = []  # итоги окна по событиям
    daily: list[DayPoint] = []  # те же счётчики по дням, от старого к новому


def _cell(n: int) -> Cell:
    return Cell(count=None, hidden=True) if n < MIN_CELL else Cell(count=n, hidden=False)


def _pct(n: int, d: int) -> float | None:
    if n < MIN_CELL or d < MIN_CELL:
        return None
    return round(100 * n / d, 1)


def _ratio(n: int, d: int) -> Ratio:
    return Ratio(**_cell(n).model_dump(), pct=_pct(n, d), of=None if d < MIN_CELL else d)


async def build(
    session: AsyncSession, days: int = DEFAULT_DAYS, *, exclude_actors: Collection[str] = ()
) -> DashboardOut:
    """Воронка за `days` дней; `exclude_actors` — псевдонимы демо-аккаунтов."""
    days = max(1, min(days, MAX_DAYS))
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        await session.execute(
            select(E.event, E.actor, E.props, E.ts).where(
                E.ts >= since, E.event.in_(_EVENTS), E.actor.is_not(None)
            )
        )
    ).all()
    if exclude_actors:
        skip = set(exclude_actors)
        rows = [r for r in rows if r[1] not in skip]
    stamped = rows
    rows = [(e, a, p) for e, a, p, _ in stamped]

    def actors(pred: Pred) -> set[str]:
        return {a for e, a, p in rows if pred(e, p or {})}

    cohort = actors(STAGES[0][2])  # воронка когортная: только зарегистрированные в окне
    funnel: list[Stage] = []
    prev = len(cohort)
    for i, (sid, title, pred) in enumerate(STAGES):
        n = len(cohort) if i == 0 else len(actors(pred) & cohort)
        funnel.append(
            Stage(
                id=sid,
                title=title,
                pct_of_registered=None if i == 0 else _pct(n, len(cohort)),
                pct_of_previous=None if i == 0 else _pct(n, prev),
                **_cell(n).model_dump(),
            )
        )
        prev = n

    fsp_n = len(actors(lambda e, p: e == "fsp_link_completed") & cohort)
    shown = actors(lambda e, p: e == "uplift_shown")
    clicked = actors(
        lambda e, p: e == "competition_clicked" and p.get("source") in _NAVIGATOR_SOURCES
    )
    counters = [
        Counter(
            id=cid,
            title=title,
            **_cell(sum(1 for e, _, p in rows if pred(e, p or {}))).model_dump(),
        )
        for cid, title, pred in COUNTERS
    ]
    by_day: dict[Date, dict[str, int]] = {}
    today = datetime.now(UTC).date()
    for i in range(days, -1, -1):
        by_day[today - timedelta(days=i)] = {cid: 0 for cid, _, _ in COUNTERS}
    for e, _, p, ts in stamped:
        bucket = by_day.get(ts.date())
        if bucket is None:
            continue
        for cid, _, pred in COUNTERS:
            if pred(e, p or {}):
                bucket[cid] += 1
    daily = [
        DayPoint(date=d, values={k: (v if v >= MIN_CELL else None) for k, v in vals.items()})
        for d, vals in by_day.items()
    ]
    return DashboardOut(
        since=since,
        days=days,
        min_cell=MIN_CELL,
        funnel=funnel,
        fsp_share=_ratio(fsp_n, len(cohort)),
        navigator_to_competition=_ratio(len(clicked & shown), len(shown)),
        counters=counters,
        daily=daily,
    )
