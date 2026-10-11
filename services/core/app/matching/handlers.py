"""Обработчики подбора: события → команды `core.match.*` → таблица `matches`."""

from __future__ import annotations

from collections.abc import Mapping

import structlog
from fsp_contracts import Envelope
from fsp_contracts.commands import CoreMatchCandidate, CoreMatchVacancy
from fsp_contracts.events import SkillsProfileUpdated, VacancyEvent
from fsp_platform.messaging import Consumer, idempotent
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.graph.trust import TrustConfig
from app.matching import service
from app.matching.scoring import MatchConfig

log = structlog.get_logger()


def register(
    consumers: Mapping[str, Consumer],
    session_factory: async_sessionmaker[AsyncSession],
    cfg: MatchConfig,
    trust: TrustConfig,
) -> None:
    @consumers["core.handlers"].on("vacancy.published")
    @idempotent(session_factory, "matching.vacancy_published")
    async def on_published(envelope: Envelope, session: AsyncSession) -> None:
        evt = VacancyEvent.model_validate(envelope.payload)
        await service.request_match_vacancy(session, evt.vacancy_id, evt.version)

    @consumers["core.handlers"].on("vacancy.updated")
    @idempotent(session_factory, "matching.vacancy_updated")
    async def on_updated(envelope: Envelope, session: AsyncSession) -> None:
        evt = VacancyEvent.model_validate(envelope.payload)
        await service.request_match_vacancy(session, evt.vacancy_id, evt.version)

    @consumers["core.handlers"].on("vacancy.closed")
    @idempotent(session_factory, "matching.vacancy_closed")
    async def on_closed(envelope: Envelope, session: AsyncSession) -> None:
        evt = VacancyEvent.model_validate(envelope.payload)
        await service.drop_vacancy_matches(session, evt.vacancy_id)

    @consumers["core.handlers"].on("skills.profile.updated")
    @idempotent(session_factory, "matching.profile_updated")
    async def on_profile(envelope: Envelope, session: AsyncSession) -> None:
        evt = SkillsProfileUpdated.model_validate(envelope.payload)
        await service.request_match_candidate(session, evt.candidate_id, evt.profile_version)

    @consumers["core.match"].on("core.match.vacancy")
    @idempotent(session_factory, "matching.match_vacancy")
    async def on_match_vacancy(envelope: Envelope, session: AsyncSession) -> None:
        cmd = CoreMatchVacancy.model_validate(envelope.payload)
        n = await service.match_vacancy(session, cmd.vacancy_id, cfg, trust, version=cmd.version)
        log.info("match_vacancy_done", vacancy_id=str(cmd.vacancy_id), count=n, skipped=n is None)

    @consumers["core.match"].on("core.match.candidate")
    @idempotent(session_factory, "matching.match_candidate")
    async def on_match_candidate(envelope: Envelope, session: AsyncSession) -> None:
        cmd = CoreMatchCandidate.model_validate(envelope.payload)
        n = await service.match_candidate(
            session, cmd.candidate_id, cfg, trust, version=cmd.profile_version
        )
        log.info("match_candidate_done", candidate_id=str(cmd.candidate_id), skipped=n is None)
