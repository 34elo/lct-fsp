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

PEERS_MAX = 200  # точек на графике; свою всегда оставляем


def place(values: list[float], mine: float) -> tuple[int, int]:
    """(место, топ-%) среди `values` (включая свою силу). Равные делят место."""
    size = max(1, len(values))
    rank = 1 + sum(1 for v in values if v > mine + 1e-9)
    return rank, max(1, min(100, math.ceil(rank / size * 100)))


async def compute(
    session: AsyncSession,
    cand: Candidate,
    cfg: StrengthConfig,
    fsp_cfg: FspStrengthConfig,
    today: datetime | None = None,
) -> CandidateStanding:
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
    others = sorted(
        (r for r in scored if r is not mine and r.strength is not None),
        key=lambda r: str(r.cand.user_id),
    )[: PEERS_MAX - 1]
    peers = [StandingPeer(strength=r.strength.value, salary_min=r.cand.salary_min)
             for r in [mine, *others] if r.strength is not None]  # fmt: skip
    return CandidateStanding(
        profession=cur.profession, grade=cur.grade, mode=cur.mode,
        confirmed_at=cur.confirmed_at,
        strength=StandingStrength(
            value=mine.strength.value, rank=rank, top_percent=top,
            parts=[StandingPart(**p.model_dump()) for p in explain(mine.strength, cfg)],
        ),
        category_size=len(scored), peers=peers,
    )  # fmt: skip
