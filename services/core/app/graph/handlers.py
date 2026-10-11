"""Обработчики core-worker для графа: recompute, taxonomy.updated, fsp.*."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

import structlog
from fsp_contracts import Envelope
from fsp_contracts.commands import CoreRecompute
from fsp_contracts.events import (
    FspCompetitionsUpdated,
    FspLinked,
    FspResultsImported,
    TaxonomyUpdated,
)
from fsp_platform.messaging import Consumer, idempotent
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.graph import fsp_ingest, service
from app.graph.embedding import Embedder
from app.graph.recompute import recompute_profile
from app.graph.trust import TrustConfig
from app.taxonomy.service import SkillGraphCache

log = structlog.get_logger()


def register(
    consumers: Mapping[str, Consumer],
    session_factory: async_sessionmaker[AsyncSession],
    cfg: TrustConfig,
    graph_cache: SkillGraphCache | None = None,
    embedder: Embedder | None = None,
) -> None:
    graph_cache = graph_cache or SkillGraphCache()

    @consumers["core.recompute"].on("core.recompute")
    @idempotent(session_factory, "graph.recompute")
    async def on_recompute(envelope: Envelope, session: AsyncSession) -> None:
        cmd = CoreRecompute.model_validate(envelope.payload)
        res = await recompute_profile(
            session,
            cmd.candidate_id,
            cmd.requested_at,
            cfg,
            await graph_cache.get(session),
            embedder=embedder,
        )
        log.info(
            "recompute_done",
            candidate_id=str(cmd.candidate_id),
            skipped=res.skipped,
            changed=res.changed,
            profile_version=res.profile_version,
        )

    @consumers["core.handlers"].on("taxonomy.updated")
    @idempotent(session_factory, "graph.taxonomy_updated")
    async def on_taxonomy_updated(envelope: Envelope, session: AsyncSession) -> None:
        evt = TaxonomyUpdated.model_validate(envelope.payload)
        graph_cache.invalidate()
        now = datetime.now(UTC)
        ids: list[uuid.UUID] = await service.candidates_by_skills(session, evt.changed_skill_ids)
        for cid in ids:
            await service.request_recompute(session, cid, now)

    # ФСП: факты и доказательства из событий fsp-connector
    @consumers["core.ingest"].on("fsp.linked")
    @idempotent(session_factory, "graph.fsp_linked")
    async def on_fsp_linked(envelope: Envelope, session: AsyncSession) -> None:
        await fsp_ingest.on_linked(session, FspLinked.model_validate(envelope.payload), cfg.fsp)

    @consumers["core.ingest"].on("fsp.competitions.updated")
    @idempotent(session_factory, "graph.fsp_competitions")
    async def on_fsp_competitions(envelope: Envelope, session: AsyncSession) -> None:
        evt = FspCompetitionsUpdated.model_validate(envelope.payload)
        await fsp_ingest.on_competitions(session, evt, cfg.fsp)

    @consumers["core.ingest"].on("fsp.results.imported")
    @idempotent(session_factory, "graph.fsp_results")
    async def on_fsp_results(envelope: Envelope, session: AsyncSession) -> None:
        evt = FspResultsImported.model_validate(envelope.payload)
        await fsp_ingest.on_results(session, evt, cfg.fsp)
