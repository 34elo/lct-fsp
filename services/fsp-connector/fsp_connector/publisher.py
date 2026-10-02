"""Публикация `fsp.*` через outbox: вызывать в одной транзакции с изменением данных."""

from __future__ import annotations

from fsp_contracts import new_event
from fsp_contracts.events import FspCompetitionsUpdated, FspLinked, FspResultsImported
from fsp_platform.outbox import add_to_outbox
from sqlalchemy.ext.asyncio import AsyncSession

PRODUCER = "fsp-connector"


async def publish_linked(session: AsyncSession, payload: FspLinked) -> None:
    await add_to_outbox(
        session, new_event("fsp.linked", PRODUCER, payload), aggregate_id=payload.candidate_id
    )


async def publish_results_imported(session: AsyncSession, payload: FspResultsImported) -> None:
    await add_to_outbox(
        session,
        new_event("fsp.results.imported", PRODUCER, payload),
        aggregate_id=payload.candidate_id,
    )


async def publish_competitions_updated(
    session: AsyncSession, payload: FspCompetitionsUpdated
) -> None:
    await add_to_outbox(session, new_event("fsp.competitions.updated", PRODUCER, payload))
