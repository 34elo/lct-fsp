"""Обработчики core-worker для графа: `core.recompute` и `taxonomy.updated` (messaging.md §4)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

import structlog
from fsp_contracts import Envelope
from fsp_contracts.commands import CoreRecompute
from fsp_contracts.events import TaxonomyUpdated
from fsp_platform.messaging import Consumer, idempotent
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.graph import service
from app.graph.recompute import recompute_profile
from app.graph.trust import TrustConfig
from app.taxonomy.service import SkillGraphCache

log = structlog.get_logger()


def register(
    consumers: Mapping[str, Consumer],
    session_factory: async_sessionmaker[AsyncSession],
    cfg: TrustConfig,
    graph_cache: SkillGraphCache | None = None,
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
