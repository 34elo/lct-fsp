"""Жизненный цикл семейства заданий (assessment.md §7, E22-9).

```
draft ─ автопроверка ─► pilot ─ пороги + админ ─► active ─ тревога ─► quarantine ─► retired
```

- Статистика семейства (`families.stats`) считается по ответам завершённых попыток: `n`, доля
  верных, `r_pb` (балл × финальный θ попытки), разброс доли верных по группам сидов
  (`seed mod G`), DIF «с ФСП / без ФСП» (разница средних остатков `y − P(θ, b)`), рост среднего
  остатка `y − P(θ, b)` за последние `leak_window` ответов относительно предыдущих (утечка; остаток
  учитывает θ отвечавших, поэтому сдвиг состава кандидатов тревогу не даёт), число апелляций.
- Допуск `pilot → active` — только кнопкой админа и только при выполнении всех порогов. Без админа
  семейство в `active` не попадает (кроме стартового банка кодовых семейств, см. `attempts.py`).
- Тревоги (`r_pb` < 0.05 при n ≥ 50, утечка, 3 апелляции) переводят `active → quarantine`
  автоматически после каждой завершённой попытки; дальше решает админ.
- Семейство выходит из оценки (`quarantine`, `retired`) или возвращается в неё — θ затронутых
  попыток пересчитываются по сохранённым ответам и текущим `b`. Грейд меняется, только если
  изменилось решение SPRT; тогда кандидат получает уведомление.

Каждая смена статуса — событие `assessment.family.status_changed` в outbox. Функции не делают
`commit`: транзакцией управляет вызывающий.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from fsp_contracts.assessment import TEST_GRADE_ORDER, FamilyStatusChanged, TestGrade
from fsp_contracts.registry import new_event
from fsp_platform.app import ProblemError
from fsp_platform.outbox import add_to_outbox
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import grading, sprt, track
from app.assessment.config import AssessmentConfig
from app.assessment.models import Attempt, FamilyRow, Grade, Response
from app.assessment.psychometrics import Observation, eap, p_correct, theta_by_type

PRODUCER = "core"
STATUSES = ("draft", "pilot", "active", "quarantine", "retired")
WITHDRAWN = frozenset({"quarantine", "retired"})
# Разрешённые переходы. В `active` — только из `pilot` (пороги) и `quarantine` (решение админа).
TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"pilot", "retired"}),
    "pilot": frozenset({"active", "quarantine", "retired"}),
    "active": frozenset({"quarantine", "retired"}),
    "quarantine": frozenset({"active", "retired"}),
    "retired": frozenset(),
}


# --- статистика и пороги (чистые функции) -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class Answer:
    """Ответ на задание семейства в завершённой попытке (в порядке ответа)."""

    score: float
    theta: float
    seed: int
    fsp: bool | None = None  # есть ли у кандидата доказательства ФСП (None — не считали)


@dataclass(frozen=True, slots=True)
class FamilyStats:
    n: int
    p: float | None  # доля верных (средний балл)
    r_pb: float | None  # точечно-бисериальная: балл × финальный θ
    seed_spread: float | None  # max − min доли верных по группам сидов
    dif: float | None  # |остаток с ФСП − остаток без ФСП|
    leak: float | None  # средний остаток y − P(θ, b) за последние leak_window − за предыдущие
    appeals: int = 0

    def as_json(self) -> dict[str, Any]:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Корреляция Пирсона; `None`, если у одной из величин нет разброса."""
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _mean(xs: Iterable[float]) -> float | None:
    vals = list(xs)
    return sum(vals) / len(vals) if vals else None


def compute_stats(
    answers: Sequence[Answer], b: float, cfg: AssessmentConfig, *, appeals: int = 0
) -> FamilyStats:
    scores = [min(max(a.score, 0.0), 1.0) for a in answers]
    n = len(scores)
    groups: dict[int, list[float]] = {}
    for a, y in zip(answers, scores, strict=True):
        groups.setdefault(a.seed % max(cfg.seed_groups, 1), []).append(y)
    means = [sum(g) / len(g) for g in groups.values()]
    spread = max(means) - min(means) if len(means) >= 2 else None

    res = [y - p_correct(a.theta, b) for a, y in zip(answers, scores, strict=True)]
    resid: dict[bool, list[float]] = {True: [], False: []}
    for a, r in zip(answers, res, strict=True):
        if a.fsp is not None:
            resid[a.fsp].append(r)
    dif = None
    if min(len(resid[True]), len(resid[False])) >= cfg.dif_min_group:
        dif = abs(sum(resid[True]) / len(resid[True]) - sum(resid[False]) / len(resid[False]))

    leak = None
    w = cfg.leak_window
    if n >= 2 * w:
        leak = sum(res[-w:]) / w - sum(res[:-w]) / (n - w)
    return FamilyStats(
        n=n,
        p=_mean(scores),
        r_pb=pearson(scores, [a.theta for a in answers]),
        seed_spread=spread,
        dif=dif,
        leak=leak,
        appeals=appeals,
    )


def admission_failures(
    stats: FamilyStats, b: float, cfg: AssessmentConfig, *, need_dif: bool = False
) -> list[str]:
    """Невыполненные пороги допуска `pilot → active` (пусто — можно допускать).

    `need_dif` — задачи ФСП (E32-6): без измеренного DIF «с ФСП / без ФСП» допуска нет.
    """
    out: list[str] = []
    if stats.n < cfg.admit_min_n:
        out.append("n")
    if stats.r_pb is None or stats.r_pb < cfg.admit_min_rpb:
        out.append("r_pb")
    if abs(b) > cfg.admit_max_abs_b:
        out.append("b")
    if stats.seed_spread is not None and stats.seed_spread > cfg.admit_max_seed_spread:
        out.append("seed_spread")
    if stats.dif is not None and stats.dif > cfg.admit_max_dif:
        out.append("dif")
    elif stats.dif is None and need_dif:
        out.append("dif_unmeasured")
    return out


def alarm_reasons(stats: FamilyStats, cfg: AssessmentConfig) -> list[str]:
    """Тревоги для `active → quarantine`."""
    out: list[str] = []
    if stats.n >= cfg.alarm_min_n and (stats.r_pb is None or stats.r_pb < cfg.alarm_min_rpb):
        out.append("low_r_pb")
    if stats.leak is not None and stats.leak >= cfg.leak_delta:
        out.append("leak")
    if stats.appeals >= cfg.alarm_appeals:
        out.append("appeals")
    return out


# --- статистика из БД -------------------------------------------------------------------------


async def _answers(session: AsyncSession, family_id: uuid.UUID) -> list[tuple[Answer, uuid.UUID]]:
    rows = await session.execute(
        select(Response.score, Attempt.theta, Response.seed, Attempt.candidate_id)
        .join(Attempt, Attempt.id == Response.attempt_id)
        .where(
            Response.family_id == family_id,
            Response.answered_at.is_not(None),
            Attempt.status != "active",
            Attempt.theta.is_not(None),
        )
        .order_by(Response.answered_at, Response.id)
    )
    return [(Answer(sc or 0.0, th, seed), cid) for sc, th, seed, cid in rows.all()]


async def refresh_stats(
    session: AsyncSession, row: FamilyRow, cfg: AssessmentConfig, *, with_dif: bool = False
) -> FamilyStats:
    """Пересчитать и сохранить `families.stats`. DIF — только по запросу (нужен граф)."""
    pairs = await _answers(session, row.id)
    if with_dif:
        from app.graph import service as graph

        fsp: dict[uuid.UUID, bool] = {}
        for _, cid in pairs:
            if cid not in fsp:
                fsp[cid] = await graph.has_source(session, cid, "fsp")
        answers = [Answer(a.score, a.theta, a.seed, fsp[cid]) for a, cid in pairs]
    else:
        answers = [a for a, _ in pairs]
    prev = dict(row.stats or {})
    stats = compute_stats(answers, row.b, cfg, appeals=int(prev.get("appeals", 0)))
    data = stats.as_json()
    if not with_dif and "dif" in prev:
        data["dif"] = prev["dif"]  # не затираем DIF, посчитанный при просмотре очереди
    row.stats = {**prev, **data, "updated_at": datetime.now(UTC).isoformat()}
    return stats


def _stats_of(row: FamilyRow) -> FamilyStats:
    s = row.stats or {}
    return FamilyStats(
        n=int(s.get("n", 0)),
        p=s.get("p"),
        r_pb=s.get("r_pb"),
        seed_spread=s.get("seed_spread"),
        dif=s.get("dif"),
        leak=s.get("leak"),
        appeals=int(s.get("appeals", 0)),
    )


# --- смена статуса ----------------------------------------------------------------------------


async def set_status(
    session: AsyncSession,
    row: FamilyRow,
    to: str,
    cfg: AssessmentConfig,
    *,
    reason: str,
    actor_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> None:
    """Переход статуса с событием. Выход из оценки или возврат в неё — пересчёт попыток."""
    if to not in STATUSES:
        raise ValueError(f"неизвестный статус {to}")
    frm = row.status
    if frm == to:
        return
    if to not in TRANSITIONS.get(frm, frozenset()):
        raise ProblemError(409, "invalid_transition", "Недопустимая смена статуса", f"{frm} → {to}")
    now = now or datetime.now(UTC)
    row.status = to
    log = list((row.stats or {}).get("log", []))
    log.append(
        {
            "from": frm,
            "to": to,
            "reason": reason,
            "actor_id": str(actor_id) if actor_id else None,
            "at": now.isoformat(),
        }
    )
    row.stats = {**(row.stats or {}), "log": log[-20:]}
    await session.flush()
    event = FamilyStatusChanged(family_id=row.id, **{"from": frm}, to=to)
    await add_to_outbox(
        session, new_event("assessment.family.status_changed", PRODUCER, event), row.id
    )
    if actor_id is not None:
        reason_kind = "admin"
    else:
        reason_kind = (
            reason.split(":")[0] if reason.split(":")[0] in ("autocheck", "alarm") else "other"
        )
    await track.emit(
        session,
        "family_status_changed",
        None,
        {
            "family": track.slug(row.slug),
            "from_status": frm,
            "to_status": to,
            "reason": reason_kind,
        },
        role="fsp_admin" if actor_id else "anon",
        now=now,
    )
    if (frm == "active") != (to == "active") and "active" in (frm, to):
        await recompute_attempts(session, row.id, cfg, now=now)


async def to_pilot(session: AsyncSession, row: FamilyRow, cfg: AssessmentConfig) -> None:
    """`draft → pilot` после автопроверки (кодовые — `families-check`, spec — конструктор)."""
    await set_status(session, row, "pilot", cfg, reason="autocheck")


async def _get(session: AsyncSession, family_id: uuid.UUID) -> FamilyRow:
    row = await session.get(FamilyRow, family_id)
    if row is None:
        raise ProblemError(404, "not_found", "Семейство не найдено")
    return row


async def approve(
    session: AsyncSession, family_id: uuid.UUID, admin_id: uuid.UUID, cfg: AssessmentConfig
) -> FamilyRow:
    """Кнопка админа: `pilot → active` (все пороги) или `quarantine → active` (решение админа)."""
    row = await _get(session, family_id)
    if row.status == "active":
        return row
    if row.status not in ("pilot", "quarantine"):
        raise ProblemError(409, "invalid_transition", "Недопустимая смена статуса", row.status)
    if row.key_status != "approved":
        raise ProblemError(409, "key_not_approved", "Ключ семейства не утверждён")
    if row.status == "pilot":
        stats = await refresh_stats(session, row, cfg, with_dif=True)
        failed = admission_failures(stats, row.b, cfg, need_dif=row.source == "fsp")
        if failed:
            raise ProblemError(
                409,
                "thresholds_not_met",
                "Пороги допуска не выполнены",
                ", ".join(failed),
                errors=[{"field": f, "message": "порог не выполнен"} for f in failed],
            )
    await set_status(session, row, "active", cfg, reason="admin", actor_id=admin_id)
    return row


async def quarantine(
    session: AsyncSession, family_id: uuid.UUID, admin_id: uuid.UUID, cfg: AssessmentConfig
) -> FamilyRow:
    row = await _get(session, family_id)
    await set_status(session, row, "quarantine", cfg, reason="admin", actor_id=admin_id)
    return row


async def retire(
    session: AsyncSession, family_id: uuid.UUID, admin_id: uuid.UUID, cfg: AssessmentConfig
) -> FamilyRow:
    row = await _get(session, family_id)
    await set_status(session, row, "retired", cfg, reason="admin", actor_id=admin_id)
    return row


async def queue(
    session: AsyncSession, status: str, cfg: AssessmentConfig
) -> list[tuple[FamilyRow, FamilyStats, list[str]]]:
    """Очередь допуска: семейства статуса со свежей статистикой и невыполненными порогами."""
    rows = list(
        await session.scalars(
            select(FamilyRow).where(FamilyRow.status == status).order_by(FamilyRow.slug)
        )
    )
    out = []
    for row in rows:
        stats = await refresh_stats(session, row, cfg, with_dif=True)
        out.append(
            (row, stats, admission_failures(stats, row.b, cfg, need_dif=row.source == "fsp"))
        )
    await session.flush()
    return out


# --- тревоги ----------------------------------------------------------------------------------


async def check_alarms(
    session: AsyncSession, row: FamilyRow, cfg: AssessmentConfig, *, refresh: bool = True
) -> list[str]:
    """Тревоги активного семейства; сработала — карантин. Возвращает причины."""
    if row.status != "active":
        return []
    stats = await refresh_stats(session, row, cfg) if refresh else _stats_of(row)
    reasons = alarm_reasons(stats, cfg)
    if reasons:
        await set_status(session, row, "quarantine", cfg, reason="alarm:" + ",".join(reasons))
    return reasons


async def watch_attempt(session: AsyncSession, att: Attempt, cfg: AssessmentConfig) -> None:
    """После завершения попытки: статистика и тревоги активных семейств, на которые отвечали."""
    rows = await session.scalars(
        select(FamilyRow)
        .join(Response, Response.family_id == FamilyRow.id)
        .where(Response.attempt_id == att.id, Response.answered_at.is_not(None))
        .order_by(FamilyRow.id)
    )
    for row in list(rows):
        if row.status == "active":
            await check_alarms(session, row, cfg)
        elif row.status == "pilot":
            await refresh_stats(session, row, cfg)
    await session.flush()


async def register_appeal(
    session: AsyncSession, family_id: uuid.UUID, cfg: AssessmentConfig
) -> list[str]:
    """Апелляция на задание семейства: счётчик в `stats.appeals`; на третьей — карантин."""
    row = await _get(session, family_id)
    stats = dict(row.stats or {})
    stats["appeals"] = int(stats.get("appeals", 0)) + 1
    row.stats = stats
    await session.flush()
    return await check_alarms(session, row, cfg, refresh=False)


# --- пересчёт попыток -------------------------------------------------------------------------


def _rank(grade: str) -> int:
    return TEST_GRADE_ORDER.index(TestGrade(grade))


def _granted(status: str, plan: dict) -> str | None:
    """Грейд, который даёт попытка: заявленный при `passed`.

    Принятое повышение (`upgrade_accepted_at`) — только у попыток до ADR-025 п.2: теперь бонусный
    этап приглашает на отдельный тест, а не повышает.
    """
    if status != "passed":
        return None
    offer = plan.get("upgrade_offer")
    if offer and plan.get("upgrade_accepted_at"):
        return offer
    return plan.get("declared_grade")


def _stage_decision(
    rows: list[tuple[Response, FamilyRow]], cut: float, theta: float, cfg: AssessmentConfig
) -> tuple[sprt.Decision, float]:
    llr = sum(sprt.llr_increment(cut, f.b, r.score or 0.0, cfg) for r, f in rows)
    if not rows:
        return sprt.Decision("failed", True), 0.0
    d = sprt.decide(
        llr,
        len(rows),
        min_items=0,
        max_items=len(rows),
        exhausted=True,
        theta=theta,
        cut=cut,
        cfg=cfg,
    )
    assert d is not None
    return d, llr


async def _regrade(
    session: AsyncSession, att: Attempt, cfg: AssessmentConfig, withdrawn: set[uuid.UUID], now
) -> bool:
    """Пересчитать одну завершённую попытку без выведенных семейств. Истина — грейд изменился."""
    cfg = cfg.for_mode(att.mode)  # экспресс — свои α/β (E32-4a)
    rows = [
        (r, f)
        for r, f in (
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
        if f.id not in withdrawn
    ]
    obs = [Observation(b=f.b, score=r.score or 0.0, skill_type=f.skill_type) for r, f in rows]
    est = eap(obs, cfg)
    plan = dict(att.plan or {})
    old_granted = _granted(att.status, {**plan, "declared_grade": att.declared_grade})

    bonus = plan.get("bonus")
    from_seq = int(bonus["from_seq"]) if bonus else None
    main_rows = [(r, f) for r, f in rows if from_seq is None or r.seq <= from_seq]
    main_d, main_llr = _stage_decision(main_rows, cfg.cuts[att.declared_grade], est.theta, cfg)
    if "main" in plan:
        plan["main"] = {
            **plan["main"],
            "result": main_d.result,
            "low_confidence": main_d.low_confidence,
            "items": len(main_rows),
            "llr": main_llr,
        }
    status = main_d.result
    if bonus:
        bonus_rows = [(r, f) for r, f in rows if r.seq > from_seq]
        bonus_d, bonus_llr = _stage_decision(bonus_rows, cfg.cuts[bonus["grade"]], est.theta, cfg)
        plan["bonus"] = {
            **bonus,
            "result": bonus_d.result,
            "low_confidence": bonus_d.low_confidence,
            "items": len(bonus_rows),
            "llr": bonus_llr,
        }
        invite_ok = status == "passed" and bonus_d.result == "passed"
        if not invite_ok:
            plan.update(invited_grade=None, invite_expires_at=None)
        elif not plan.get("invited_grade"):  # приглашение (ADR-025 п.2) — от конца попытки
            from app.assessment import attempts

            finished = grading._aware(att.finished_at or now)
            plan.update(attempts.invitation(bonus, "passed", cfg, now=finished))
    plan["theta_by_type"] = theta_by_type(obs, cfg)
    plan["recomputed_at"] = now.isoformat()
    att.plan = plan
    att.theta, att.se = est.theta, est.se
    att.status = status
    new_granted = _granted(status, {**plan, "declared_grade": att.declared_grade})

    row = await session.get(Grade, (att.candidate_id, att.profession))
    owned = row is not None and row.attempt_id == att.id
    active = row is not None and grading._aware(row.valid_until) > now
    changed = False
    if new_granted != old_granted:
        if owned and new_granted is None:
            before = grading._snapshot(row)
            row.valid_until = now  # грейд попытки больше не подтверждён (данные не удаляем)
            row.updated_at = now
            changed = before != grading._snapshot(row)
        elif new_granted is not None and (
            owned or not active or _rank(new_granted) > _rank(row.grade)
        ):
            low = bool(main_d.low_confidence)
            changed = await grading._write_grade(
                session, att, TestGrade(new_granted), cfg, now, low_confidence=low
            )
    elif owned and new_granted is not None:  # решение то же: обновляем θ и позицию в полосе
        before = grading._snapshot(row)
        row.theta, row.se = est.theta, est.se
        row.band_position = grading.band_position(TestGrade(row.grade), est.theta, cfg)
        row.theta_by_type = plan["theta_by_type"]
        if before != grading._snapshot(row):
            await grading._emit_category_changed(session, att.candidate_id, now)
    await session.flush()

    from app.graph import service as graph

    await graph.deactivate(session, att.candidate_id, source="test", fact_id=att.id)
    await grading._write_evidence(session, att, cfg, now, exclude=withdrawn)
    if changed:
        await grading._emit_category_changed(session, att.candidate_id, now)
    if new_granted != old_granted:
        await _notify(session, att, new_granted)
    return new_granted != old_granted


async def _notify(session: AsyncSession, att: Attempt, grade: str | None) -> None:
    from app.notifications import service as notifications

    title = (
        f"Итог теста пересчитан: грейд {grade}"
        if grade
        else "Итог теста пересчитан: грейд не подтверждён"
    )
    await notifications.notify(
        session,
        att.candidate_id,
        type="assessment.regraded",
        title=title,
        payload={"attempt_id": str(att.id), "profession": att.profession, "grade": grade},
        out=[],
    )


async def recompute_attempts(
    session: AsyncSession,
    family_id: uuid.UUID,
    cfg: AssessmentConfig,
    *,
    now: datetime | None = None,
) -> list[uuid.UUID]:
    """Пересчёт завершённых попыток, где семейство было оцениваемым. Возвращает id тех, чей
    грейд изменился."""
    now = now or datetime.now(UTC)
    withdrawn = set(
        await session.scalars(select(FamilyRow.id).where(FamilyRow.status.in_(WITHDRAWN)))
    )
    atts = await session.scalars(
        select(Attempt)
        .join(Response, Response.attempt_id == Attempt.id)
        .where(
            Response.family_id == family_id,
            Response.is_pilot.is_(False),
            Response.answered_at.is_not(None),
            Attempt.status.in_(("passed", "failed")),
        )
        .order_by(Attempt.finished_at, Attempt.id)
    )
    changed: list[uuid.UUID] = []
    for att in list(atts):
        if await _regrade(session, att, cfg, withdrawn, now):
            changed.append(att.id)
    return changed
