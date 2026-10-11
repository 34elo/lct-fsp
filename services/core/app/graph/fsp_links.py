"""Связи людей по командам ФСП. Без анализа GitHub.

- `refresh_links` перестраивает связи `fsp_team` из `fsp_team_members` (идемпотентно);
  вызывается заданием `candidate_links.refresh` (core.jobs, раз в 10 минут).
- `prize_partner_counts` - анонимный агрегат «выступал в команде с N призёрами ФСП».
  Имён, псевдонимов и id напарников наружу не отдаём, только число.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

import structlog
from fsp_contracts import Envelope
from fsp_platform.messaging import Consumer, idempotent
from sqlalchemy import delete, insert, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.graph.fsp_models import CandidateLink, FspResultRow, FspTeamMember

log = structlog.get_logger()

KIND_TEAM = "fsp_team"
PRIZE_PLACES = 3


async def refresh_links(session: AsyncSession) -> int:
    """Пересобрать связи `fsp_team`; возвращает число пар. Повтор даёт тот же результат."""
    a, b = FspTeamMember, FspTeamMember.__table__.alias("b")
    pairs = (
        select(a.candidate_id, b.c.candidate_id, literal(KIND_TEAM), a.team_id)
        .join(b, (a.team_id == b.c.team_id) & (a.candidate_id < b.c.candidate_id))
        .where(a.candidate_id.is_not(None), b.c.candidate_id.is_not(None))
        .distinct()
    )
    await session.execute(delete(CandidateLink).where(CandidateLink.kind == KIND_TEAM))
    res = await session.execute(
        insert(CandidateLink).from_select(
            ["candidate_a", "candidate_b", "kind", "context_id"], pairs
        )
    )
    return res.rowcount or 0


async def prize_partner_counts(
    session: AsyncSession, candidate_ids: list[uuid.UUID], *, prize_places: int = PRIZE_PLACES
) -> dict[uuid.UUID, int]:
    """Сколько разных напарников по командам ФСП стали призёрами в общей команде."""
    if not candidate_ids:
        return {}
    ids = set(candidate_ids)
    rows = (
        await session.execute(
            select(
                CandidateLink.candidate_a, CandidateLink.candidate_b, CandidateLink.context_id
            ).where(
                CandidateLink.kind == KIND_TEAM,
                or_(CandidateLink.candidate_a.in_(ids), CandidateLink.candidate_b.in_(ids)),
            )
        )
    ).all()
    if not rows:
        return {}
    prizers = {
        (r.candidate_id, r.team_id)
        for r in await session.execute(
            select(FspResultRow.candidate_id, FspResultRow.team_id).where(
                FspResultRow.is_active.is_(True),
                FspResultRow.place.is_not(None),
                FspResultRow.place <= prize_places,
                FspResultRow.team_id.in_({r.context_id for r in rows}),
            )
        )
    }
    partners: dict[uuid.UUID, set[uuid.UUID]] = {}
    for a, b, team in rows:
        for me, other in ((a, b), (b, a)):
            if me in ids and (other, team) in prizers:
                partners.setdefault(me, set()).add(other)
    return {cid: len(p) for cid, p in partners.items()}


def register(
    consumers: Mapping[str, Consumer], session_factory: async_sessionmaker[AsyncSession]
) -> None:
    @consumers["core.jobs"].on("candidate_links.refresh")
    @idempotent(session_factory, "graph.candidate_links_refresh")
    async def on_refresh(envelope: Envelope, session: AsyncSession) -> None:
        log.info("candidate_links_refreshed", pairs=await refresh_links(session))
