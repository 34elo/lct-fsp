"""Живые прогоны (metrics.md §3): задания, автозасчёт по событиям, SUS.

Задание засчитывается без кнопки «готово»: `record()` вызывает `attach` до записи
(метит события прогоном) и `apply` после (двигает счётчики заданий).
"""

from __future__ import annotations

import secrets
import statistics
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from fsp_platform.app import ProblemError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.models import AnalyticsEventRow, LiveRun

SCENARIOS = ("candidate", "employer")
SUS_ITEMS = 10
DWELL_SECONDS = 20  # «карточка изучена»: card_dwell не меньше 20 с


def _any(_props: dict) -> bool:
    return True


def _dwelled(props: dict) -> bool:
    seconds = props.get("seconds")
    return seconds is None or float(seconds) >= DWELL_SECONDS


@dataclass(frozen=True)
class TaskDef:
    id: str
    title: str
    events: frozenset[str]
    target: int = 1
    accept: Callable[[dict], bool] = _any


CATALOG: dict[str, list[TaskDef]] = {
    "candidate": [
        TaskDef("resume", "Создать профиль из резюме", frozenset({"resume_confirmed"})),
        TaskDef("fsp", "Подтвердить достижения ФСП", frozenset({"fsp_link_completed"})),
        TaskDef(
            "uplift",
            "Узнать, какой навык подтвердить",
            frozenset({"uplift_clicked", "competition_clicked"}),
        ),
        TaskDef(
            "offer_reply",
            "Ответить на оффер",
            frozenset({"offer_accepted", "offer_declined"}),
        ),
    ],
    "employer": [
        TaskDef("shortlist", "Найти 5 подходящих кандидатов", frozenset({"shortlisted"}), 5),
        TaskDef(
            "why",
            "Понять, почему кандидат подходит",
            frozenset({"graph_path_highlighted", "card_dwell"}),
            accept=_dwelled,
        ),
        TaskDef("offer_sent", "Отправить оффер", frozenset({"offer_sent"})),
    ],
}


def _defs(scenario: str) -> dict[str, TaskDef]:
    return {t.id: t for t in CATALOG[scenario]}


def _aware(dt: datetime | None) -> datetime | None:
    # SQLite отдаёт naive-время, PostgreSQL — aware
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


def sus_score(answers: list[int]) -> float:
    """`(Σ_нечётные(x − 1) + Σ_чётные(5 − x)) × 2.5`; пункты нумеруются с 1."""
    odd = sum(x - 1 for x in answers[0::2])
    even = sum(5 - x for x in answers[1::2])
    return (odd + even) * 2.5


async def create(
    session: AsyncSession, scenario: str, task_ids: list[str] | None, notes: str | None
) -> LiveRun:
    defs = _defs(scenario)
    ids = task_ids or list(defs)
    unknown = [i for i in ids if i not in defs]
    if unknown or len(set(ids)) != len(ids):
        raise ProblemError(422, "invalid_tasks", "Неизвестные или повторяющиеся задания")
    run = LiveRun(
        id=uuid.uuid4(),
        scenario=scenario,
        token=secrets.token_urlsafe(24),
        tasks=[
            {"id": i, "title": defs[i].title, "target": defs[i].target, "count": 0, "done_at": None}
            for i in ids
        ],
        invited_at=datetime.now(UTC),
        notes=notes,
    )
    session.add(run)
    await session.flush()
    return run


async def by_token(session: AsyncSession, token: str) -> LiveRun:
    stmt = select(LiveRun).where(LiveRun.token == token)
    run = (await session.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise ProblemError(404, "not_found", "Прогон не найден")
    return run


async def start(session: AsyncSession, run: LiveRun, actor: str | None) -> LiveRun:
    """Идемпотентный старт: таймер идёт с первого вызова, псевдоним привязывается один раз."""
    if run.finished_at is not None:
        raise ProblemError(409, "run_finished", "Прогон уже завершён")
    if run.started_at is None:
        run.started_at = datetime.now(UTC)
    if actor and run.actor is None:
        run.actor = actor
    await session.flush()
    return run


async def attach(session: AsyncSession, rows: list[dict]) -> dict[uuid.UUID, LiveRun]:
    """До записи: события испытателя без `run_id` получают метку его прогона.

    Событие с `run_id` и псевдонимом привязывает псевдоним к прогону (если ещё не привязан).
    Возвращает открытые прогоны, затронутые пачкой.
    """
    run_ids = {r["run_id"] for r in rows if r.get("run_id")}
    actors = {r["actor"] for r in rows if r.get("actor") and not r.get("run_id")}
    if not run_ids and not actors:
        return {}
    cond = []
    if run_ids:
        cond.append(LiveRun.id.in_(run_ids))
    if actors:
        cond.append(LiveRun.actor.in_(actors))
    stmt = select(LiveRun).where(LiveRun.finished_at.is_(None), or_(*cond))
    found = (await session.execute(stmt)).scalars().all()
    runs = {r.id: r for r in found}
    by_actor = {r.actor: r for r in found if r.actor}
    for row in rows:
        if row.get("run_id"):
            run = runs.get(row["run_id"])
            if run is not None and row.get("actor") and run.actor is None:
                run.actor = row["actor"]
                by_actor[run.actor] = run
        elif row.get("actor") in by_actor:
            run = by_actor[row["actor"]]
            started = _aware(run.started_at)
            if started is not None and _aware(row["ts"]) < started:
                continue  # событие раньше старта прогона
            row["run_id"] = run.id
    return runs


def apply(runs: dict[uuid.UUID, LiveRun], rows: list[dict]) -> None:
    """После записи: двигает счётчики заданий, ставит `started_at` по первому событию."""
    for row in sorted((r for r in rows if r.get("run_id") in runs), key=lambda r: r["ts"]):
        run = runs[row["run_id"]]
        ts = _aware(row["ts"])
        if run.started_at is None:
            run.started_at = ts
        defs = _defs(run.scenario)
        tasks = [dict(t) for t in run.tasks]
        for t in tasks:
            d = defs.get(t["id"])
            if d is None or t["done_at"] or row["event"] not in d.events:
                continue
            if not d.accept(row.get("props") or {}):
                continue
            t["count"] += 1
            if t["count"] >= t["target"]:
                t["done_at"] = ts.isoformat()
            run.tasks = tasks  # новый список: иначе JSON-колонка не увидит изменение
            break  # одно событие закрывает одно задание


async def submit_sus(
    session: AsyncSession,
    run: LiveRun,
    answers: list[int],
    category_agree: bool | None,
    notes: str | None,
) -> LiveRun:
    if run.finished_at is not None:
        raise ProblemError(409, "run_finished", "Анкета уже отправлена")
    run.sus_answers = answers
    run.sus_score = sus_score(answers)
    run.category_agree = category_agree
    if notes:
        run.notes = notes
    run.finished_at = datetime.now(UTC)
    if run.started_at is None:
        run.started_at = run.finished_at
    await session.flush()
    return run


def task_stats(run: LiveRun, last_event: datetime | None) -> list[dict]:
    """По каждому заданию: выполнено ли и сколько заняло (от предыдущего выполненного)."""
    out, prev = [], _aware(run.started_at)
    for t in run.tasks:
        done_at = datetime.fromisoformat(t["done_at"]) if t["done_at"] else None
        end = done_at or _aware(last_event)
        duration = (end - prev).total_seconds() if prev and end else None
        out.append(
            {
                "id": t["id"],
                "title": t["title"],
                "target": t["target"],
                "count": t["count"],
                "done": done_at is not None,
                "done_at": done_at,
                "duration_s": max(0, round(duration)) if duration is not None else None,
            }
        )
        if done_at:
            prev = done_at
    return out


async def steps_and_last(
    session: AsyncSession, run_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, datetime | None]]:
    if not run_ids:
        return {}
    res = await session.execute(
        select(AnalyticsEventRow.run_id, func.count(), func.max(AnalyticsEventRow.ts))
        .where(AnalyticsEventRow.run_id.in_(run_ids))
        .group_by(AnalyticsEventRow.run_id)
    )
    return {rid: (n, last) for rid, n, last in res.all()}


def stuck_task(stats: list[dict]) -> str | None:
    """Затык: задание, на котором стояли дольше всего (невыполненное — до последнего события)."""
    timed = [s for s in stats if s["duration_s"] is not None]
    return max(timed, key=lambda s: s["duration_s"])["id"] if timed else None


def summarize(runs: list[dict]) -> dict:
    """Сводка для страницы качества: успешность заданий, медианное время, SUS, согласие."""
    finished = [r for r in runs if r["status"] == "finished"]
    total = sum(r["tasks_total"] for r in finished)
    done = sum(r["tasks_done"] for r in finished)
    times = [r["total_time_s"] for r in finished if r["total_time_s"] is not None]
    sus = [r["sus_score"] for r in finished if r["sus_score"] is not None]
    agree = [r["category_agree"] for r in finished if r["category_agree"] is not None]
    return {
        "runs": len(runs),
        "finished": len(finished),
        "task_success_pct": round(100 * done / total, 1) if total else None,
        "median_time_s": round(statistics.median(times)) if times else None,
        "median_sus": round(statistics.median(sus), 1) if sus else None,
        "category_agree_pct": round(100 * sum(agree) / len(agree), 1) if agree else None,
    }
