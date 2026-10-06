"""Грейды, кулдауны и итог попытки (assessment.md §5, blocks.md §4.2, §4.4); `grades` пишет Б1.

- Кулдауны (`check_cooldown`): смена грейда — не чаще раза в `change_cooldown_days` (90), повтор
  того же грейда после неудачи — через `retry_days` (30); попытка на грейд ниже после неудачи
  доступна сразу (один раз). Нарушение → `409 cooldown` с датой `next_attempt_at`.
- Итог (`on_finished`): при завершении попытки (один раз) — запись грейда (без понижения),
  доказательства `test` в `graph`, события `assessment.attempt.finished` и, если набор категорий или
  поля, влияющие на силу профиля, изменились, — `candidate.category.changed` (всегда полный набор).
- Бонусный этап грейд не повышает (ADR-025 п.2): прошёл — в событии `invited_grade`, а тест по
  приглашению (`attempts.start_invited`) идёт без кулдаунов; его провал повтор не закрывает.

Функции не делают `commit`: события пишутся в outbox в транзакции вызывающего.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fsp_contracts.assessment import (
    TEST_GRADE_ORDER,
    AttemptFinished,
    CategoryChanged,
    CategoryRef,
    TestGrade,
)
from fsp_contracts.registry import new_event
from fsp_platform.app import ProblemError
from fsp_platform.outbox import add_to_outbox
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.config import AssessmentConfig
from app.assessment.models import Attempt, FamilyRow, Grade, Response
from app.candidates.models import Candidate
from app.graph import service as graph

PRODUCER = "core"


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _rank(grade: str) -> int:
    return TEST_GRADE_ORDER.index(TestGrade(grade))


def band_position(grade: TestGrade, theta: float, cfg: AssessmentConfig) -> float:
    """T = clamp((θ − cut_g) / (cut_{g+1} − cut_g), 0, 1); у senior ширина полосы 1.0 (§9)."""
    idx = TEST_GRADE_ORDER.index(grade)
    lo = cfg.cuts[grade.value]
    hi = cfg.cuts[TEST_GRADE_ORDER[idx + 1].value] if idx + 1 < len(TEST_GRADE_ORDER) else lo + 1.0
    return min(1.0, max(0.0, (theta - lo) / (hi - lo)))


# --- кулдауны ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Cooldown:
    kind: str  # change | retry
    grade: TestGrade | None  # для retry — грейд, на который нельзя; для change — None
    until: datetime


async def _failed_attempts(
    session: AsyncSession, candidate_id: uuid.UUID, profession: str
) -> list[Attempt]:
    """Неудачи, которые закрывают повтор. Провал теста по приглашению не считается (ADR-025 п.2)."""
    rows = list(
        await session.scalars(
            select(Attempt)
            .where(
                Attempt.candidate_id == candidate_id,
                Attempt.profession == profession,
                Attempt.status == "failed",
                Attempt.finished_at.is_not(None),
            )
            .order_by(Attempt.finished_at.desc())
        )
    )
    return [a for a in rows if not (a.plan or {}).get("invited_by")]


async def cooldowns(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    profession: str,
    cfg: AssessmentConfig,
    now: datetime | None = None,
) -> list[Cooldown]:
    """Действующие ограничения по профессии: повторы после неудач и смена грейда."""
    now = now or datetime.now(UTC)
    out: list[Cooldown] = []
    seen: set[str] = set()
    for att in await _failed_attempts(session, candidate_id, profession):
        until = _aware(att.finished_at) + timedelta(days=cfg.retry_days)
        if until > now and att.declared_grade not in seen:  # свежая неудача по грейду — одна запись
            seen.add(att.declared_grade)
            out.append(Cooldown("retry", TestGrade(att.declared_grade), until))
    row = await session.get(Grade, (candidate_id, profession))
    if row is not None and _aware(row.valid_until) > now and _aware(row.next_change_at) > now:
        out.append(Cooldown("change", None, _aware(row.next_change_at)))
    return sorted(out, key=lambda c: c.until)


def _cooldown_error(until: datetime, detail: str) -> ProblemError:
    return ProblemError(
        409, "cooldown", "Пересдача пока недоступна", f"{until.isoformat()} {detail}"
    )


async def check_cooldown(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    profession: str,
    declared: TestGrade,
    cfg: AssessmentConfig,
    now: datetime | None = None,
) -> None:
    """`409 cooldown` с датой следующей попытки, если попытка на `declared` сейчас запрещена."""
    now = now or datetime.now(UTC)
    failed = await _failed_attempts(session, candidate_id, profession)
    for att in failed:  # повтор того же грейда после неудачи — через retry_days
        until = _aware(att.finished_at) + timedelta(days=cfg.retry_days)
        if att.declared_grade == declared.value and until > now:
            raise _cooldown_error(until, "повтор грейда после неудачи")
    row = await session.get(Grade, (candidate_id, profession))
    if row is None or _aware(row.valid_until) <= now or row.grade == declared.value:
        return
    until = _aware(row.next_change_at)
    if until <= now:
        return
    # исключение: после неудачи одна попытка на грейд ниже доступна сразу
    for att in failed:
        if _aware(att.finished_at) + timedelta(days=cfg.retry_days) <= now:
            break
        if _rank(declared.value) < _rank(att.declared_grade):
            used = await session.scalar(
                select(Attempt.id)
                .where(
                    Attempt.candidate_id == candidate_id,
                    Attempt.profession == profession,
                    Attempt.started_at >= att.finished_at,
                    Attempt.declared_grade == declared.value,
                )
                .limit(1)
            )
            if used is None:
                return
    raise _cooldown_error(until, "смена грейда не чаще раза в 90 дней")


# --- итог попытки -----------------------------------------------------------------------------


async def _profile_version(session: AsyncSession, candidate_id: uuid.UUID) -> int:
    cand = await session.get(Candidate, candidate_id)
    return cand.profile_version if cand else 0


async def _emit_category_changed(
    session: AsyncSession, candidate_id: uuid.UUID, now: datetime
) -> None:
    rows = await session.scalars(
        select(Grade)
        .where(Grade.candidate_id == candidate_id, Grade.valid_until > now)
        .order_by(Grade.profession)
    )
    event = CategoryChanged(
        candidate_id=candidate_id,
        categories=[CategoryRef(profession=g.profession, grade=TestGrade(g.grade)) for g in rows],
        profile_version=await _profile_version(session, candidate_id),
    )
    await add_to_outbox(
        session, new_event("candidate.category.changed", PRODUCER, event), candidate_id
    )


def _snapshot(row: Grade | None) -> tuple | None:
    if row is None:
        return None
    return (
        row.grade,
        round(row.band_position, 6),
        round(row.integrity, 6),
        row.needs_confirmation,
        _aware(row.valid_until),
    )


async def _write_grade(
    session: AsyncSession,
    att: Attempt,
    grade: TestGrade,
    cfg: AssessmentConfig,
    now: datetime,
    *,
    low_confidence: bool,
) -> bool:
    """Записать грейд попытки (upsert по `(candidate, profession)`). Истина — было ли изменение."""
    theta = att.theta if att.theta is not None else cfg.cuts[grade.value]
    row = await session.get(Grade, (att.candidate_id, att.profession))
    before = _snapshot(row)
    changed_grade = row is None or _aware(row.valid_until) <= now or row.grade != grade.value
    if row is None:
        row = Grade(candidate_id=att.candidate_id, profession=att.profession)
        session.add(row)
    row.grade = grade.value
    row.theta = theta
    row.se = att.se
    row.band_position = band_position(grade, theta, cfg)
    row.theta_by_type = (att.plan or {}).get("theta_by_type") or {}
    row.integrity = att.integrity if att.integrity is not None else 1.0
    row.needs_confirmation = row.integrity < cfg.integrity_threshold
    row.low_confidence = low_confidence
    row.source = "test"
    row.attempt_id = att.id
    row.confirmed_at = now
    row.valid_until = now + timedelta(days=cfg.validity_days)
    if changed_grade or row.next_change_at is None:
        row.next_change_at = now + timedelta(days=cfg.change_cooldown_days)
    row.updated_at = now
    await session.flush()
    return before != _snapshot(row)


async def _write_evidence(
    session: AsyncSession,
    att: Attempt,
    cfg: AssessmentConfig,
    now: datetime,
    *,
    exclude: Collection[uuid.UUID] = frozenset(),
) -> None:
    """Доказательства `test` по навыкам попытки: сила = max · доля набранного (идемпотентно).

    `exclude` — выведенные из оценки семейства (пересчёт при карантине, E22-9).
    """
    rows = (
        await session.execute(
            select(Response, FamilyRow)
            .join(FamilyRow, FamilyRow.id == Response.family_id)
            .where(
                Response.attempt_id == att.id,
                Response.answered_at.is_not(None),
                Response.is_pilot.is_(False),
            )
        )
    ).all()
    per_skill: dict[uuid.UUID, list[float]] = defaultdict(list)
    types: dict[uuid.UUID, str] = {}
    for r, f in rows:
        if f.id in exclude:
            continue
        per_skill[f.skill_id].append(r.score or 0.0)
        types[f.skill_id] = f.skill_type
    cap = cfg.evidence_max_strength
    if (att.integrity if att.integrity is not None else 1.0) < cfg.integrity_threshold:
        cap = min(cap, cfg.unconfirmed_cap)  # «требует подтверждения»: доверие ограничено ●●○○
    items = []
    for sid in sorted(per_skill, key=str):
        scores = per_skill[sid]
        share = sum(scores) / len(scores)
        strength = round(min(cap, cfg.evidence_max_strength * share), 4)
        if strength <= 0:
            continue
        items.append(
            graph.EvidenceIn(
                skill_id=sid,
                source="test",
                strength=strength,
                observed_at=now.date(),
                fact_type="test_attempt",
                fact_id=att.id,
                details={
                    "theta": round(att.theta or 0.0, 4),
                    "share": round(share, 4),
                    "items": len(scores),
                    "skill_type": types[sid],
                    "profession": att.profession,
                    "grade": att.declared_grade,
                },
            )
        )
    if items:
        await graph.upsert_evidence(session, att.candidate_id, items)


async def on_finished(
    session: AsyncSession, att: Attempt, cfg: AssessmentConfig, now: datetime | None = None
) -> None:
    """Вызывается один раз при завершении попытки, после `finalize_attempt`."""
    now = now or datetime.now(UTC)
    plan = att.plan or {}
    passed = att.status == "passed"
    low = bool((plan.get("main") or {}).get("low_confidence"))
    category_changed = False
    if passed:
        declared = TestGrade(att.declared_grade)
        row = await session.get(Grade, (att.candidate_id, att.profession))
        active = row is not None and _aware(row.valid_until) > now
        if not active or _rank(declared.value) >= _rank(row.grade):  # грейд не понижается
            category_changed = await _write_grade(
                session, att, declared, cfg, now, low_confidence=low
            )
    await _write_evidence(session, att, cfg, now)
    if category_changed:
        await _emit_category_changed(session, att.candidate_id, now)
    cur = await session.get(Grade, (att.candidate_id, att.profession))
    current = TestGrade(cur.grade) if cur is not None and _aware(cur.valid_until) > now else None
    event = AttemptFinished(
        candidate_id=att.candidate_id,
        attempt_id=att.id,
        profession=att.profession,
        declared_grade=TestGrade(att.declared_grade),
        stage=att.stage,  # type: ignore[arg-type]
        result="passed" if passed else "failed",
        grade=current,
        theta=att.theta or 0.0,
        se=att.se or 0.0,
        integrity=att.integrity if att.integrity is not None else 1.0,
        needs_confirmation=(att.integrity if att.integrity is not None else 1.0)
        < cfg.integrity_threshold,
        low_confidence=low or bool((plan.get("bonus") or {}).get("low_confidence")),
        finished_at=_aware(att.finished_at or now),
        profile_version=await _profile_version(session, att.candidate_id),
        invited_grade=TestGrade(plan["invited_grade"]) if plan.get("invited_grade") else None,
    )
    await add_to_outbox(
        session, new_event("assessment.attempt.finished", PRODUCER, event), att.candidate_id
    )
    from app.assessment import track  # E31-2a

    await track.emit(
        session,
        "assessment_finished",
        att.candidate_id,
        {
            "attempt_id": str(att.id),
            "profession": att.profession,
            "declared_grade": att.declared_grade,
            "stage": att.stage,
            "result": "passed" if passed else "failed",
            "grade": current.value if current else None,
            "items": int((plan.get("main") or {}).get("items") or 0),
            "duration_s": int(
                (_aware(att.finished_at or now) - _aware(att.started_at)).total_seconds()
            )
            if att.started_at
            else None,
        },
        now=now,
    )
    from app.assessment import lifecycle  # тревоги семейств после попытки (E22-9)

    await lifecycle.watch_attempt(session, att, cfg)
