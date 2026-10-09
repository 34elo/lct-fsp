"""Сила профиля и место в категории для самого кандидата (E35-12a, assessment.md §9).

Категория — профессия × грейд кандидата (основная профессия, иначе старший грейд). Сила
каждого участника считается той же формулой, что у работодателя (`strength.py`, без запроса:
S — доверие по навыкам). Место — по убыванию силы, у равных одно место. Чужих идентификаторов
в ответе нет: только числа для графика.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from fsp_contracts.assessment import (
    CandidateStanding,
    CategoryRef,
    StandingCategoryStats,
    StandingGap,
    StandingLeader,
    StandingPart,
    StandingPeer,
    StandingStrength,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import service as assessment
from app.candidates import service as candidates
from app.candidates.models import Candidate
from app.graph import service as graph
from app.graph.fsp_strength import FspStrengthConfig
from app.matching import navigator
from app.matching.search import Row, _attach_strength, trust_of
from app.matching.strength import StrengthConfig, explain
from app.offers import service as offers
from app.vacancies import service as vacancies

PEERS_MAX = 200  # точек на графике; свою всегда оставляем


def median(values: list[int]) -> int | None:
    """Медиана целых (для чётного числа — округлённое среднее двух средних); пусто → None."""
    if not values:
        return None
    v = sorted(values)
    n = len(v)
    return v[n // 2] if n % 2 else round((v[n // 2 - 1] + v[n // 2]) / 2)


def place(values: list[float], mine: float) -> tuple[int, int]:
    """(место, топ-%) среди `values` (включая свою силу). Равные делят место."""
    size = max(1, len(values))
    rank = 1 + sum(1 for v in values if v > mine + 1e-9)
    return rank, max(1, min(100, math.ceil(rank / size * 100)))


def relative_strength(mine: float, leader: float) -> float:
    """Сила относительно лидера категории, % (лидер = 100). Нулевой лидер → 100 (все равны)."""
    if leader <= 1e-9:
        return 100.0
    return round(max(0.0, min(100.0, mine / leader * 100)), 1)


def gap_to_next_ten(values: list[float], mine: float, top: int) -> StandingGap | None:
    """Сколько п.п. «от лидера» не хватает до ближайшей границы «десятки» выше своей.

    Граница — наибольшее кратное 10 строго меньше `top` (топ-34 → топ-30); у топ-10 % и выше и у
    самого лидера её нет. Нужная сила — у кандидата на месте floor(граница · N / 100), не выше 1-го.
    """
    target = (top - 1) // 10 * 10
    ordered = sorted(values, reverse=True)
    if target < 10 or mine >= ordered[0] - 1e-9:  # выше некуда
        return None
    need_rank = max(1, math.floor(target / 100 * len(ordered)))
    need = ordered[need_rank - 1]
    return StandingGap(
        top_percent=target,
        gap_relative=round(
            max(0.0, relative_strength(need, ordered[0]) - relative_strength(mine, ordered[0])), 1
        ),
    )


async def compute(
    session: AsyncSession,
    cand: Candidate,
    cfg: StrengthConfig,
    fsp_cfg: FspStrengthConfig,
    today: datetime | None = None,
) -> CandidateStanding:
    """Сила и место кандидата в его категории той же формулой, что у работодателя (assessment.md §9,
    E35-12a).
    """
    now = today or datetime.now(UTC)
    grades = await assessment.get_grades(session, cand.user_id)
    cur = navigator.pick_current(grades, cand.primary_role)
    if cur is None:
        return CandidateStanding()
    member_ids = await assessment.category_members(session, cur.profession, cur.grade)
    if cand.user_id not in member_ids:
        member_ids.append(cand.user_id)
    members = {c.user_id: c for c in await candidates.get_many(session, member_ids)}
    members[cand.user_id] = cand
    owned = await graph.all_skills_of(session, list(members))
    rows = [Row(c, trust_of(owned[i]), 0.0, owned[i]) for i, c in members.items()]
    await _attach_strength(
        session, rows, CategoryRef(profession=cur.profession, grade=cur.grade), [], {},
        now.date(), cfg, fsp_cfg,
    )  # fmt: skip
    scored = [r for r in rows if r.strength is not None]
    mine = next((r for r in scored if r.cand.user_id == cand.user_id), None)
    if mine is None or mine.strength is None:
        return CandidateStanding(
            profession=cur.profession, grade=cur.grade, mode=cur.mode,
            confirmed_at=cur.confirmed_at,
        )  # fmt: skip
    values = [r.strength.value for r in scored if r.strength is not None]
    rank, top = place(values, mine.strength.value)
    leader = max(values)
    others = sorted(
        (r for r in scored if r is not mine and r.strength is not None),
        key=lambda r: str(r.cand.user_id),
    )[: PEERS_MAX - 1]
    grades_of = await assessment.get_grades_many(session, member_ids)

    def theta_of(uid) -> float | None:
        g = next((x for x in grades_of.get(uid, []) if x.profession == cur.profession), None)
        return g.theta if g else None

    peers = [StandingPeer(strength=r.strength.value, salary_min=r.cand.salary_min,
                          theta=theta_of(r.cand.user_id))
             for r in [mine, *others] if r.strength is not None]  # fmt: skip
    salaries = await offers.category_interest_salaries(session, member_ids)
    stats = StandingCategoryStats(
        candidates=len(scored),
        interests=len(salaries),
        interest_salary_from_median=median([a for a, _ in salaries]),
        interest_salary_to_median=median([b for _, b in salaries]),
        companies_searching=await vacancies.companies_searching(
            session, cur.profession, str(cur.grade)
        ),
    )
    return CandidateStanding(
        profession=cur.profession, grade=cur.grade, mode=cur.mode,
        confirmed_at=cur.confirmed_at,
        strength=StandingStrength(
            value=mine.strength.value, rank=rank, top_percent=top,
            relative=relative_strength(mine.strength.value, leader),
            gap_to_next_ten=gap_to_next_ten(values, mine.strength.value, top),
            parts=[StandingPart(**p.model_dump()) for p in explain(mine.strength, cfg)],
        ),
        leader=StandingLeader(grade=cur.grade),
        category_size=len(scored), peers=peers, category_stats=stats,
    )  # fmt: skip
