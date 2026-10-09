"""Привязка ФСП со стороны core: PKCE/state в Redis, статус привязки, достижения (fsp.md §4)."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from fsp_contracts import new_envelope
from fsp_contracts.commands import FspSync
from fsp_platform.app import ProblemError
from fsp_platform.outbox import add_to_outbox
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.fsp.client import ConnectorClient
from app.graph.fsp_models import FspParticipant, FspTeamMember, FspTeamRow

STATE_TTL = 600  # s:oauth:* — 10 мин (messaging.md §6)
SYNC_COOLDOWN = 600  # ручное обновление не чаще раза в 10 минут


def _state_key(state: str) -> str:
    return f"s:oauth:{state}"


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


async def put_state(redis: Redis, user_id: uuid.UUID, verifier: str, next_path: str) -> str:
    state = secrets.token_urlsafe(32)
    payload = json.dumps({"user_id": str(user_id), "verifier": verifier, "next": next_path})
    await redis.set(_state_key(state), payload, ex=STATE_TTL)
    return state


async def take_state(redis: Redis, state: str) -> dict[str, Any] | None:
    raw = await redis.getdel(_state_key(state))  # одноразовый
    if raw is None:
        return None
    return json.loads(raw.decode() if isinstance(raw, bytes) else raw)


async def link_status(session: AsyncSession, candidate_id: uuid.UUID) -> dict[str, Any]:
    row = await session.get(FspParticipant, candidate_id)
    if row is None:
        return {"linked": False, "verified": False, "participant_id": None}
    return {"linked": True, "verified": row.verified, "participant_id": row.participant_id}


async def teams_of(session: AsyncSession, candidate_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(FspTeamRow.id, FspTeamRow.name, FspTeamMember.role)
        .join(FspTeamMember, FspTeamMember.team_id == FspTeamRow.id)
        .where(FspTeamMember.candidate_id == candidate_id)
        .order_by(FspTeamRow.id)
    )
    return [{"id": i, "name": n or "", "role": r} for i, n, r in rows]


async def request_sync(session: AsyncSession, redis: Redis, candidate_id: uuid.UUID) -> None:
    if await session.get(FspParticipant, candidate_id) is None:
        raise ProblemError(409, "fsp_not_linked", "Сначала привяжите ФСП")
    ok = await redis.set(
        f"rl:fspsync:{candidate_id}", datetime.now(UTC).isoformat(), nx=True, ex=SYNC_COOLDOWN
    )
    if not ok:
        raise ProblemError(429, "sync_too_often", "Обновлять можно раз в 10 минут")
    cmd = FspSync(candidate_id=candidate_id, reason="manual")
    await add_to_outbox(session, new_envelope("fsp.sync", "core", cmd), aggregate_id=candidate_id)


async def demo_create_result(session: AsyncSession, connector: ConnectorClient) -> None:
    """Демо-кнопка: создать результат ФСП для случайного кандидата."""
    await connector.demo_create_result()


async def demo_reset(session: AsyncSession, connector: ConnectorClient) -> None:
    """Демо-кнопка: очистить результаты ФСП."""
    await connector.demo_reset()


async def pending_requests_count(connector: ConnectorClient) -> int:
    """Число заявок на привязку ФСП, ждущих решения админа (E39-29)."""
    data = await connector.registry("GET", "/requests", params={"status": "pending"})
    return len(data or [])
