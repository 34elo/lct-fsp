"""Сервис доказательств: единственная точка записи evidence для остальных модулей.

Upsert идемпотентен по (candidate_id, skill_id, source, fact_type, fact_id): повтор с теми же
данными ничего не меняет и не порождает событие. Реальное изменение → `evidence.changed`
в outbox в той же транзакции (messaging.md); пересчёт запрашивается там же командой
`core.recompute` (`request_recompute`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from fsp_contracts import new_envelope
from fsp_contracts.commands import CoreRecompute
from fsp_contracts.enums import EvidenceSource
from fsp_contracts.events import EvidenceChanged
from fsp_platform.outbox import add_to_outbox
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.models import Candidate
from app.graph.models import Evidence


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
