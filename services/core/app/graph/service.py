"""Сервис доказательств: единственная точка записи evidence для остальных модулей.

Upsert идемпотентен по (candidate_id, skill_id, source, fact_type, fact_id): повтор с теми же
данными ничего не меняет и не порождает событие. Реальное изменение → `evidence.changed`
в outbox в той же транзакции (messaging.md); пересчёт запрашивается там же командой
`core.recompute` (`request_recompute`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import sqlalchemy as sa
from fsp_contracts import new_envelope
from fsp_contracts.commands import CoreRecompute
from fsp_contracts.enums import EvidenceSource
from fsp_contracts.events import EvidenceChanged
from fsp_platform.outbox import add_to_outbox
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.models import Candidate
from app.graph.fsp_models import FspCompetitionRow, FspRankRow, FspResultRow
from app.graph.models import CandidateSkill, Evidence


@dataclass(frozen=True, slots=True)
class EvidenceIn:
    skill_id: uuid.UUID
    source: EvidenceSource | str
    strength: float
    observed_at: date
    fact_type: str
    fact_id: uuid.UUID
    details: dict | None = None
    verified: bool = True


@dataclass(frozen=True, slots=True)
class UpsertResult:
    created: int
    updated: int
    unchanged: int

    @property
    def changed(self) -> bool:
        return bool(self.created or self.updated)


_FIELDS = ("strength", "observed_at", "details", "verified")


def _key(candidate_id: uuid.UUID, i: EvidenceIn) -> tuple:
    return (candidate_id, i.skill_id, str(i.source), i.fact_type, i.fact_id)


async def request_recompute(
    session: AsyncSession, candidate_id: uuid.UUID, requested_at: datetime | None = None
) -> None:
    """Слияние пересчётов (graph.md §4.4): поставить `recompute_requested_at` и отправить команду.

    Обработчик `core.recompute` пропустит её, если `recomputed_at >= requested_at`.
    """
    at = requested_at or datetime.now(UTC)
    await session.execute(
        update(Candidate).where(Candidate.user_id == candidate_id).values(recompute_requested_at=at)
    )
    cmd = CoreRecompute(candidate_id=candidate_id, requested_at=at)
    await add_to_outbox(session, new_envelope("core.recompute", "core", cmd), candidate_id)


async def _publish(session: AsyncSession, candidate_id: uuid.UUID, sources: set[str]) -> None:
    event = EvidenceChanged(candidate_id=candidate_id, sources=sorted(sources))
    await add_to_outbox(session, new_envelope("evidence.changed", "core", event), candidate_id)
    await request_recompute(session, candidate_id)


async def upsert_evidence(
    session: AsyncSession, candidate_id: uuid.UUID, items: list[EvidenceIn]
) -> UpsertResult:
    """Создать/обновить доказательства кандидата. Деактивированное оживает при повторе."""
    for i in items:
        if not 0 <= i.strength <= 1:
            raise ValueError(f"strength вне [0, 1]: {i.strength}")
    # дубли внутри пачки: побеждает последний
    wanted = {_key(candidate_id, i): i for i in items}
    if not wanted:
        return UpsertResult(0, 0, 0)

    skills = {k[1] for k in wanted}
    rows = await session.scalars(
        select(Evidence).where(Evidence.candidate_id == candidate_id, Evidence.skill_id.in_(skills))
    )
    existing = {(r.candidate_id, r.skill_id, r.source, r.fact_type, r.fact_id): r for r in rows}

    created = updated = unchanged = 0
    sources: set[str] = set()
    for key, i in wanted.items():
        row = existing.get(key)
        if row is None:
            session.add(
                Evidence(
                    candidate_id=candidate_id,
                    skill_id=i.skill_id,
                    source=str(i.source),
                    strength=i.strength,
                    observed_at=i.observed_at,
                    fact_type=i.fact_type,
                    fact_id=i.fact_id,
                    details=i.details,
                    verified=i.verified,
                )
            )
            created += 1
            sources.add(str(i.source))
            continue
        dirty = not row.is_active or any(getattr(row, f) != getattr(i, f) for f in _FIELDS)
        if not dirty:
            unchanged += 1
            continue
        for f in _FIELDS:
            setattr(row, f, getattr(i, f))
        row.is_active = True
        updated += 1
        sources.add(str(i.source))

    await session.flush()
    if sources:
        await _publish(session, candidate_id, sources)
    return UpsertResult(created, updated, unchanged)


async def deactivate(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    *,
    source: EvidenceSource | str | None = None,
    fact_type: str | None = None,
    fact_id: uuid.UUID | None = None,
) -> int:
    """Мягко выключить доказательства по фильтру (минимум один фильтр). Возвращает число."""
    if source is None and fact_type is None and fact_id is None:
        raise ValueError("нужен хотя бы один фильтр")
    stmt = select(Evidence).where(Evidence.candidate_id == candidate_id, Evidence.is_active)
    if source is not None:
        stmt = stmt.where(Evidence.source == str(source))
    if fact_type is not None:
        stmt = stmt.where(Evidence.fact_type == fact_type)
    if fact_id is not None:
        stmt = stmt.where(Evidence.fact_id == fact_id)
    rows = list(await session.scalars(stmt))
    for r in rows:
        r.is_active = False
    await session.flush()
    if rows:
        await _publish(session, candidate_id, {r.source for r in rows})
    return len(rows)


async def list_active(
    session: AsyncSession, candidate_id: uuid.UUID, skill_id: uuid.UUID | None = None
) -> list[Evidence]:
    """Активные доказательства кандидата (подграф для пересчёта), свежие первыми."""
    stmt = select(Evidence).where(Evidence.candidate_id == candidate_id, Evidence.is_active)
    if skill_id is not None:
        stmt = stmt.where(Evidence.skill_id == skill_id)
    stmt = stmt.order_by(Evidence.observed_at.desc(), Evidence.id)
    return list(await session.scalars(stmt))


async def candidates_by_skills(
    session: AsyncSession, skill_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    """Кандидаты с активными доказательствами по навыкам (затронутые `taxonomy.updated`)."""
    if not skill_ids:
        return []
    rows = await session.scalars(
        select(Evidence.candidate_id)
        .where(Evidence.skill_id.in_(skill_ids), Evidence.is_active)
        .distinct()
    )
    return list(rows)


# --- чтение для подбора (matching) -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CoverReq:
    """Строка требования для отбора: навык `skill_id` закрывается навыком `via` с коэф. `adj`."""

    skill_id: uuid.UUID
    via: uuid.UUID
    adj: float
    floor: float  # нижняя граница требуемого уровня


async def covering_candidates(
    session: AsyncSession,
    reqs: list[CoverReq],
    *,
    required_count: int,
    max_failed: int,
    limit: int,
) -> list[uuid.UUID]:
    """Отбор по графу (matching.md §3, A): закрыто ≥ `required_count − (max_failed − 1)` требований.

    `cover = max(conf(via) · adj)` по каждому требованию; порядок — число закрытых, затем сумма.
    """
    if not reqs:
        return []
    req = sa.union_all(
        *(
            sa.select(
                sa.literal(r.skill_id, sa.Uuid).label("skill_id"),
                sa.literal(r.via, sa.Uuid).label("via"),
                sa.literal(r.adj, sa.Float).label("adj"),
                sa.literal(r.floor, sa.Float).label("floor"),
            )
            for r in reqs
        )
    ).subquery("req")
    cover = (
        sa.select(
            CandidateSkill.candidate_id.label("cid"),
            req.c.skill_id,
            sa.func.max(CandidateSkill.confidence * req.c.adj).label("eff"),
            sa.func.max(req.c.floor).label("floor"),
        )
        .join(req, CandidateSkill.skill_id == req.c.via)
        .group_by(CandidateSkill.candidate_id, req.c.skill_id)
        .subquery("cover")
    )
    met = sa.func.count().filter(cover.c.eff >= cover.c.floor - 1e-9)
    stmt = (
        sa.select(cover.c.cid)
        .group_by(cover.c.cid)
        .having(met >= required_count - (max_failed - 1))
        .order_by(met.desc(), sa.func.sum(cover.c.eff).desc(), cover.c.cid)
        .limit(limit)
    )
    return list(await session.scalars(stmt))


async def skills_of_candidates(
    session: AsyncSession, candidate_ids: list[uuid.UUID], skill_ids: list[uuid.UUID]
) -> list[CandidateSkill]:
    """Рёбра «владеет» кандидатов по нужным навыкам."""
    if not candidate_ids or not skill_ids:
        return []
    stmt = select(CandidateSkill).where(
        CandidateSkill.candidate_id.in_(candidate_ids), CandidateSkill.skill_id.in_(skill_ids)
    )
    return list(await session.scalars(stmt))


async def evidence_of(
    session: AsyncSession,
    candidate_ids: list[uuid.UUID],
    *,
    skill_ids: list[uuid.UUID] | None = None,
    fact_ids: list[uuid.UUID] | None = None,
    source: str | None = None,
) -> list[Evidence]:
    """Активные доказательства кандидатов с фильтрами по навыкам, фактам, источнику."""
    if not candidate_ids:
        return []
    stmt = select(Evidence).where(Evidence.candidate_id.in_(candidate_ids), Evidence.is_active)
    if skill_ids is not None:
        stmt = stmt.where(Evidence.skill_id.in_(skill_ids))
    if fact_ids is not None:
        stmt = stmt.where(Evidence.fact_id.in_(fact_ids))
    if source is not None:
        stmt = stmt.where(Evidence.source == source)
    return list(await session.scalars(stmt.order_by(Evidence.id)))


async def all_skills_of(
    session: AsyncSession, candidate_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[CandidateSkill]]:
    """Все рёбра «владеет» кандидатов (витрина поиска)."""
    out: dict[uuid.UUID, list[CandidateSkill]] = {i: [] for i in candidate_ids}
    if not candidate_ids:
        return out
    stmt = select(CandidateSkill).where(CandidateSkill.candidate_id.in_(candidate_ids))
    for cs in await session.scalars(stmt.order_by(CandidateSkill.skill_id)):
        out[cs.candidate_id].append(cs)
    return out


async def fsp_disciplines_of(
    session: AsyncSession, candidate_ids: list[uuid.UUID]
) -> dict[uuid.UUID, set[str]]:
    """Дисциплины ФСП, где у кандидата есть результат или разряд."""
    out: dict[uuid.UUID, set[str]] = {}
    if not candidate_ids:
        return out
    for model in (FspResultRow, FspRankRow):
        stmt = select(model.candidate_id, model.discipline).where(
            model.candidate_id.in_(candidate_ids)
        )
        for cid, disc in (await session.execute(stmt)).all():
            if disc:
                out.setdefault(cid, set()).add(disc)
    return out


async def evidence_by_ids(session: AsyncSession, ids: list[uuid.UUID]) -> list[Evidence]:
    """Активные доказательства по id (для краткой выписки «откуда навык»)."""
    if not ids:
        return []
    stmt = select(Evidence).where(Evidence.id.in_(ids), Evidence.is_active)
    return list(await session.scalars(stmt.order_by(Evidence.id)))


async def has_source(session: AsyncSession, candidate_id: uuid.UUID, source: str) -> bool:
    """Есть ли у кандидата действующие доказательства из источника (например, `github`)."""
    stmt = (
        select(Evidence.id)
        .where(Evidence.candidate_id == candidate_id, Evidence.source == source)
        .where(Evidence.is_active.is_(True))
        .limit(1)
    )
    return (await session.scalar(stmt)) is not None


async def upcoming_competitions(
    session: AsyncSession, today: date, days: int
) -> list[FspCompetitionRow]:
    """Будущие соревнования ФСП (объявлены или идёт регистрация) в ближайшие `days` дней."""
    stmt = (
        select(FspCompetitionRow)
        .where(
            FspCompetitionRow.status.in_(("announced", "registration")),
            FspCompetitionRow.start_date >= today,
            FspCompetitionRow.start_date <= today + timedelta(days=days),
        )
        .order_by(FspCompetitionRow.start_date, FspCompetitionRow.id)
    )
    return list(await session.scalars(stmt))
