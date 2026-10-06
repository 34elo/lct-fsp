"""Выбор задания и остановка поверх БД (assessment.md §5–6, E22-3).

Чистые формулы — в `selection.py` (план, дефицит, счёт, топ-3, пилоты) и `sprt.py` (LLR, решение,
бонус). Здесь — фильтры банка, которым нужна БД:
- статус (`active` для оценки, `pilot` для пилотных слотов) и навык из плана;
- уровень в пределах грейда этапа ±1;
- не показывались этому кандидату `repeat_days` дней (в том числе в текущей попытке);
- экспозиция за `exposure_days` дней < `exposure_max` тестов — проверяется, когда тестов в окне
  не меньше `exposure_min_tests` (на холодном старте любая выдача дала бы 100 %).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from random import Random

from fsp_contracts.assessment import TestGrade
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import selection as sel
from app.assessment.config import AssessmentConfig
from app.assessment.models import Attempt, FamilyRow, Response
from app.assessment.psychometrics import Estimate, Observation, eap
from app.taxonomy import service as taxonomy


def sections_json(plan: Iterable[sel.Section]) -> list[dict]:
    return [{"skill": s.skill, "skill_type": s.skill_type, "share": s.share} for s in plan]


def sections_of(raw: list[dict]) -> list[sel.Section]:
    return [sel.Section(r["skill"], r["skill_type"], float(r["share"])) for r in raw]


async def _shown_to_candidate(
    session: AsyncSession, candidate_id: uuid.UUID, since: datetime
) -> set[uuid.UUID]:
    rows = await session.scalars(
        select(Response.family_id)
        .join(Attempt, Attempt.id == Response.attempt_id)
        .where(Attempt.candidate_id == candidate_id, Response.created_at >= since)
        .distinct()
    )
    return set(rows)


async def _overexposed(
    session: AsyncSession, now: datetime, cfg: AssessmentConfig
) -> set[uuid.UUID]:
    since = now - timedelta(days=cfg.exposure_days)
    tests = await session.scalar(
        select(func.count()).select_from(Attempt).where(Attempt.started_at >= since)
    )
    if not tests or tests < cfg.exposure_min_tests:
        return set()
    rows = await session.execute(
        select(Response.family_id, func.count(func.distinct(Response.attempt_id)))
        .join(Attempt, Attempt.id == Response.attempt_id)
        .where(Attempt.started_at >= since)
        .group_by(Response.family_id)
    )
    return {fid for fid, cnt in rows.all() if cnt / tests >= cfg.exposure_max}


async def _seen_competitions(
    session: AsyncSession, candidate_id: uuid.UUID, rows: Iterable[FamilyRow]
) -> set[str]:
    """Соревнования ФСП кандидата — только если среди кандидатов есть задачи соревнований."""
    if not any(r.competition_id for r in rows):
        return set()
    from app.graph import service as graph  # граф читает ФСП-модели Б2 через свой service

    return await graph.fsp_competitions_of(session, candidate_id)


async def eligible(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    skills: Iterable[str],
    grade: TestGrade | None,
    cfg: AssessmentConfig,
    *,
    status: str = "active",
    now: datetime | None = None,
) -> dict[str, list[FamilyRow]]:
    """Семейства-кандидаты по навыкам (slug → строки). `grade=None` — без фильтра уровня."""
    now = now or datetime.now(UTC)
    by_id = {taxonomy.skill_id(s): s for s in skills}
    if not by_id:
        return {}
    rows = await session.scalars(
        select(FamilyRow).where(FamilyRow.status == status, FamilyRow.skill_id.in_(by_id))
    )
    shown = await _shown_to_candidate(session, candidate_id, now - timedelta(days=cfg.repeat_days))
    hot = await _overexposed(session, now, cfg) if status == "active" else set()
    rows = list(rows)
    seen_comps = await _seen_competitions(session, candidate_id, rows)
    out: dict[str, list[FamilyRow]] = {}
    for r in rows:
        if r.id in shown or r.id in hot:
            continue
        if r.competition_id and r.competition_id in seen_comps:
            continue  # участнику соревнования его задачи не даём (E32-6)
        if grade is not None and not sel.level_ok(r.level, grade, cfg):
            continue
        out.setdefault(by_id[r.skill_id], []).append(r)
    return out


async def stage_plan(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    skill_weights: dict[str, float],
    skill_types: dict[str, str],
    grade: TestGrade,
    cfg: AssessmentConfig,
) -> list[sel.Section]:
    """План этапа по навыкам, для которых сейчас есть допустимые задания."""
    avail = await eligible(session, candidate_id, skill_weights, grade, cfg)
    return sel.build_plan(skill_weights, skill_types, grade, cfg, available=set(avail))


def candidate(row: FamilyRow) -> sel.Candidate:
    return sel.Candidate(id=row.id, b=row.b, ai_solvable=row.ai_solvable or 0.0, n=row.n)


async def pick_regular(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    sections: list[sel.Section],
    grade: TestGrade,
    issued_by_skill: dict[str, int],
    k: int,
    rng: Random,
    cfg: AssessmentConfig,
) -> uuid.UUID | None:
    """Секция с наибольшим дефицитом, где есть кандидаты → топ-3 по счёту у порога грейда."""
    pool = await eligible(session, candidate_id, [s.skill for s in sections], grade, cfg)
    target = cfg.cuts[grade.value]
    for section in sel.sections_by_deficit(sections, issued_by_skill, k):
        rows = pool.get(section.skill)
        if rows:
            chosen = sel.choose([candidate(r) for r in rows], target, rng, cfg)
            return chosen.id if chosen else None
    return None


async def pick_pilot(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    skills: Iterable[str],
    rng: Random,
    cfg: AssessmentConfig,
) -> uuid.UUID | None:
    """Пилот: статус `pilot`, секции профессии, наименьшее `n`, при равенстве случайно."""
    pool = await eligible(session, candidate_id, skills, None, cfg, status="pilot")
    chosen = sel.pick_pilot([candidate(r) for rows in pool.values() for r in rows], rng)
    return chosen.id if chosen else None


async def current_estimate(
    session: AsyncSession, attempt_id: uuid.UUID, cfg: AssessmentConfig
) -> Estimate:
    """EAP θ по оцениваемым ответам попытки (пилоты не влияют)."""
    rows = await session.execute(
        select(Response.score, FamilyRow.b, FamilyRow.skill_type)
        .join(FamilyRow, FamilyRow.id == Response.family_id)
        .where(
            Response.attempt_id == attempt_id,
            Response.answered_at.is_not(None),
            Response.is_pilot.is_(False),
        )
    )
    return eap([Observation(b=b, score=sc or 0.0, skill_type=t) for sc, b, t in rows.all()], cfg)
