"""Телеметрия попытки поверх БД: таймер p95 и индекс честности (assessment.md §8).

- Таймер задания (`time_limit_for`) — p95 времени ответа семейства по последним ответам других
  попыток; данных мало — таймер семейства по умолчанию.
- Честность (`assess_attempt`) — вызывается при завершении попытки **до** калибровки `b`: θ — тот
  же EAP, что даст `finalize_attempt`, `b` — на момент ответа. Пишет `attempts.integrity` и разбор
  сигналов в `attempts.plan["integrity"]`; `grading` переносит `I` и пометку в `grades`.
- «Невозможный» неверный ответ: ответ кандидата на задание вида `copy_kinds` даёт 0 для его
  варианта, но совпадает с верным ответом другого кандидата на его вариант того же семейства
  (варианты различаются сидом, так что совпадение возможно почти только при списывании).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.config import AssessmentConfig
from app.assessment.integrity import (
    IntegrityConfig,
    IntegrityResult,
    ItemSignal,
    assess,
    load_integrity_config,
    parse_telemetry,
    quantile,
    time_limit_s,
)
from app.assessment.models import Attempt, FamilyRow, Response


async def family_rts(
    session: AsyncSession,
    family_id: uuid.UUID,
    icfg: IntegrityConfig,
    exclude_attempt: uuid.UUID | None = None,
) -> list[int]:
    """Время ответов семейства (мс), последние `rt_window` ответов других попыток."""
    q = select(Response.rt_ms).where(
        Response.family_id == family_id,
        Response.answered_at.is_not(None),
        Response.rt_ms.is_not(None),
    )
    if exclude_attempt is not None:
        q = q.where(Response.attempt_id != exclude_attempt)
    q = q.order_by(Response.answered_at.desc()).limit(icfg.rt_window)
    return [int(x) for x in await session.scalars(q)]


async def time_limit_for(
    session: AsyncSession, family_id: uuid.UUID, default_s: int, icfg: IntegrityConfig | None = None
) -> int:
    icfg = icfg or load_integrity_config()
    return time_limit_s(await family_rts(session, family_id, icfg), default_s, icfg)


def _norm(v: Any) -> Any:
    """Нормализация ответа для сравнения: строки без регистра и пробелов, числа как float."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int | float):
        return round(float(v), 6)
    if isinstance(v, str):
        s = v.strip().lower()
        try:
            return round(float(s.replace(",", ".")), 6)
        except ValueError:
            return s
    if isinstance(v, list | tuple):
        return tuple(_norm(x) for x in v)
    if isinstance(v, dict):
        return tuple(sorted((str(k), _norm(x)) for k, x in v.items()))
    return str(v)


async def copy_matches(
    session: AsyncSession,
    att: Attempt,
    wrong: Iterable[tuple[Response, FamilyRow]],
    icfg: IntegrityConfig,
) -> int:
    """Сколько неверных ответов попытки совпали с верным ответом другого кандидата."""
    ours = {
        r.family_id: _norm(r.answer)
        for r, f in wrong
        if f.kind in icfg.copy_kinds and r.answer is not None and _norm(r.answer) != ""
    }
    if not ours:
        return 0
    rows = await session.execute(
        select(Response.family_id, Response.answer)
        .join(Attempt, Attempt.id == Response.attempt_id)
        .where(
            Response.family_id.in_(ours),
            Attempt.candidate_id != att.candidate_id,
            Response.answered_at.is_not(None),
            Response.score >= icfg.correct_min - 1e-9,
        )
    )
    hit: set[uuid.UUID] = set()
    for fam_id, answer in rows.all():
        if fam_id not in hit and _norm(answer) == ours[fam_id]:
            hit.add(fam_id)
    return len(hit)


async def assess_attempt(
    session: AsyncSession, att: Attempt, cfg: AssessmentConfig, icfg: IntegrityConfig | None = None
) -> IntegrityResult:
    """Индекс честности завершённой попытки → `att.integrity`, `att.plan["integrity"]`."""
    icfg = icfg or load_integrity_config()
    rows = (
        await session.execute(
            select(Response, FamilyRow)
            .join(FamilyRow, FamilyRow.id == Response.family_id)
            .where(
                Response.attempt_id == att.id,
                Response.answered_at.is_not(None),
                Response.is_pilot.is_(False),
            )
            .order_by(Response.seq)
        )
    ).all()
    items: list[ItemSignal] = []
    for r, f in rows:
        rts = await family_rts(session, f.id, icfg, exclude_attempt=att.id)
        median = quantile(rts, 0.5) if len(rts) >= icfg.rt_min_n else None
        away, pastes = parse_telemetry(r.telemetry)
        items.append(
            ItemSignal(
                b=f.b,
                score=r.score or 0.0,
                rt_ms=r.rt_ms,
                median_ms=median,
                away_ms=away,
                pastes=pastes,
            )
        )
    wrong = [(r, f) for r, f in rows if (r.score or 0.0) <= 0.0]
    matches = await copy_matches(session, att, wrong, icfg)
    res = assess(items, matches, cfg, icfg)
    att.integrity = res.index
    att.plan = {**(att.plan or {}), "integrity": res.as_json()}
    await session.flush()
    return res
