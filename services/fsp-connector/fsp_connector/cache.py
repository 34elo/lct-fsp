"""CachedFspAdapter: кеш ответов ФСП в Redis (ключи `c:fsp:*`, TTL 10 мин)."""

from __future__ import annotations

import json
from datetime import date

from fsp_contracts.fsp import (
    FspCompetition,
    FspOAuthIdentity,
    FspParticipant,
    FspParticipantBrief,
    FspRank,
    FspResult,
    FspStandingRow,
    FspTeam,
    MaskedContact,
)
from pydantic import TypeAdapter
from redis.asyncio import Redis

from fsp_connector.port import FspPort

_RESULTS = TypeAdapter(list[FspResult])


def part_key(participant_id: str) -> str:
    return f"c:fsp:part:{participant_id}"


def results_key(participant_id: str) -> str:
    return f"c:fsp:res:{participant_id}"


class CachedFspAdapter:
    """Кеширует карточку участника и полный список результатов. Остальное — напрямую.

    Результаты с `since` не кешируем: инкрементальная синхронизация всегда идёт к источнику.
    Вебхук и синхронизация вызывают `invalidate(participant_id)`.
    """

    def __init__(self, inner: FspPort, redis: Redis, ttl_seconds: int = 600):
        self.inner = inner
        self.redis = redis
        self.ttl = ttl_seconds

    async def invalidate(self, participant_id: str) -> None:
        await self.redis.delete(part_key(participant_id), results_key(participant_id))

    async def get_participant(self, participant_id: str) -> FspParticipant:
        key = part_key(participant_id)
        if (hit := await self.redis.get(key)) is not None:
            return FspParticipant.model_validate_json(hit)
        value = await self.inner.get_participant(participant_id)
        await self.redis.set(key, value.model_dump_json(), ex=self.ttl)
        return value

    async def get_results(self, participant_id: str, since: date | None = None) -> list[FspResult]:
        if since is not None:
            return await self.inner.get_results(participant_id, since)
        key = results_key(participant_id)
        if (hit := await self.redis.get(key)) is not None:
            return _RESULTS.validate_json(hit)
        value = await self.inner.get_results(participant_id)
        await self.redis.set(key, json.dumps(_RESULTS.dump_python(value, mode="json")), ex=self.ttl)
        return value

    async def get_ranks(self, participant_id: str) -> list[FspRank]:
        return (await self.get_participant(participant_id)).ranks

    # --- без кеша
    async def find_participant(
        self,
        *,
        email: str | None = None,
        last_name: str | None = None,
        birth_date: date | None = None,
    ) -> list[FspParticipantBrief]:
        return await self.inner.find_participant(
            email=email, last_name=last_name, birth_date=birth_date
        )

    async def get_competitions(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        discipline: str | None = None,
    ) -> list[FspCompetition]:
        return await self.inner.get_competitions(
            date_from=date_from, date_to=date_to, discipline=discipline
        )

    async def get_standings(self, competition_id: str) -> list[FspStandingRow]:
        return await self.inner.get_standings(competition_id)

    async def get_team(self, team_id: str) -> FspTeam:
        return await self.inner.get_team(team_id)

    async def send_verification_code(self, participant_id: str) -> MaskedContact:
        return await self.inner.send_verification_code(participant_id)

    async def check_verification_code(self, participant_id: str, code: str) -> bool:
        return await self.inner.check_verification_code(participant_id, code)

    def authorize_url(self, state: str, code_challenge: str) -> str:
        return self.inner.authorize_url(state, code_challenge)

    async def exchange_code(self, code: str, code_verifier: str) -> FspOAuthIdentity:
        return await self.inner.exchange_code(code, code_verifier)
