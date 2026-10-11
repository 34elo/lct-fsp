"""Синхронизация результатов ФСП: fsp-connector → события `fsp.*` для core.

Команда `fsp.sync {candidate_id, reason, since?}`: берём привязку, тянем результаты, разряды,
составы команд и календарь, пишем `fsp.competitions.updated` и `fsp.results.imported` в outbox.
Upsert по `(participant_id, competition_id, stage)` и правила «дисциплина → навыки» — в core
(`app/fsp`): здесь только нормализованные факты. Команда `fsp.sync_all` — то же для всех привязок
плюс обновление календаря.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from uuid import UUID

import structlog
from fsp_contracts.events import FspCompetitionsUpdated, FspResultsImported
from fsp_contracts.fsp import FspCompetition, FspRank, FspResult, FspTeam
from fsp_platform.db import session_scope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fsp_connector.errors import FspError, FspNotFound
from fsp_connector.models import FspLink
from fsp_connector.port import FspPort
from fsp_connector.publisher import publish_competitions_updated, publish_results_imported

log = structlog.get_logger()


def ranks_digest(ranks: list[FspRank]) -> str:
    body = sorted((r.discipline, r.rank, str(r.assigned_at)) for r in ranks)
    return hashlib.sha1(json.dumps(body).encode()).hexdigest()  # noqa: S324 - не криптография


class SyncService:
    def __init__(self, port: FspPort, sessions: async_sessionmaker[AsyncSession]):
        self.port, self.sessions = port, sessions

    async def _invalidate(self, participant_id: str) -> None:
        invalidate = getattr(self.port, "invalidate", None)
        if invalidate is not None:
            await invalidate(participant_id)

    async def _competitions(self, wanted: set[str] | None) -> list[FspCompetition]:
        """Календарь целиком (`wanted=None`) или только соревнования, упомянутые в результатах."""
        items = await self.port.get_competitions()
        return items if wanted is None else [c for c in items if c.id in wanted]

    async def _teams(self, results: list[FspResult]) -> list[FspTeam]:
        teams: dict[str, FspTeam] = {}
        for tid in sorted({r.team_id for r in results if r.team_id}):
            try:
                teams[tid] = await self.port.get_team(tid)
            except FspNotFound:
                log.warning("fsp_team_not_found", team_id=tid)  # состав неизвестен — не критично
        return list(teams.values())

    async def sync_candidate(
        self,
        session: AsyncSession,
        candidate_id: UUID,
        *,
        reason: str,
        since: date | None = None,
        now: datetime | None = None,
    ) -> bool:
        """Синхронизировать одного кандидата. True — событие `fsp.results.imported` опубликовано.

        Полная выгрузка (`new=true`) — `since` не задан и привязка ещё не синхронизировалась
        либо причина `linked`/`manual` без `since`; core по ней деактивирует исчезнувшие результаты.
        """
        link = await session.get(FspLink, candidate_id)
        if link is None:
            log.info("fsp_sync_skipped_no_link", candidate_id=str(candidate_id), reason=reason)
            return False
        now = now or datetime.now(UTC)
        full = since is None and (link.last_synced_at is None or reason in {"linked", "manual"})
        if since is None and not full and link.last_synced_at is not None:
            since = link.last_synced_at.date()
        await self._invalidate(link.participant_id)

        results = await self.port.get_results(link.participant_id, None if full else since)
        ranks = await self.port.get_ranks(link.participant_id)
        digest = ranks_digest(ranks)
        changed = full or bool(results) or digest != link.sync_cursor

        if changed:
            wanted = {r.competition_id for r in results}
            comps = await self._competitions(wanted) if wanted else []
            if comps:
                await publish_competitions_updated(
                    session, FspCompetitionsUpdated(competitions=comps)
                )
            await publish_results_imported(
                session,
                FspResultsImported(
                    candidate_id=candidate_id,
                    participant_id=link.participant_id,
                    results=results,
                    ranks=ranks,
                    teams=await self._teams(results),
                    new=full,
                ),
            )
        link.last_synced_at = now
        link.sync_cursor = digest
        log.info(
            "fsp_synced",
            candidate_id=str(candidate_id),
            reason=reason,
            full=full,
            results=len(results),
            published=changed,
        )
        return changed

    async def sync_all(self, *, now: datetime | None = None) -> int:
        """Часовой фолбэк: календарь + инкрементальная синхронизация всех привязок."""
        comps = await self._competitions(None)
        if comps:
            async with session_scope(self.sessions) as s:
                await publish_competitions_updated(s, FspCompetitionsUpdated(competitions=comps))
        async with self.sessions() as s:
            ids = list(await s.scalars(select(FspLink.candidate_id).order_by(FspLink.linked_at)))
        done = 0
        for cid in ids:
            try:
                async with session_scope(self.sessions) as s:
                    await self.sync_candidate(s, cid, reason="schedule", now=now)
                done += 1
            except FspError as exc:  # один сбойный участник не рвёт остальных
                log.warning("fsp_sync_failed", candidate_id=str(cid), code=exc.code)
        return done
