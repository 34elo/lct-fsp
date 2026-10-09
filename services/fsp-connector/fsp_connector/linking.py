"""Привязка кандидата к участнику ФСП: реестр (E39-28), OAuth, код, ручной ID (fsp.md §4)."""

from __future__ import annotations

import hmac
from typing import Literal
from uuid import UUID

from fsp_contracts.events import FspLinked
from fsp_contracts.fsp import MaskedContact
from fsp_platform.app import ProblemError
from fsp_platform.db import session_scope
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fsp_connector.errors import FspNotFound
from fsp_connector.models import FspLink, FspLinkConflict
from fsp_connector.port import FspPort
from fsp_connector.publisher import publish_linked

Method = Literal["oauth", "code", "manual", "registry"]


def pending_key(candidate_id: UUID) -> str:
    return f"s:fspcode:{candidate_id}"


class LinkService:
    def __init__(
        self,
        port: FspPort,
        sessions: async_sessionmaker[AsyncSession],
        redis: Redis,
        *,
        code_ttl: int = 600,
        max_attempts: int = 5,
    ):
        self.port, self.sessions, self.redis = port, sessions, redis
        self.code_ttl, self.max_attempts = code_ttl, max_attempts

    # ------------------------------------------------------------ OAuth
    def authorize_url(self, state: str, code_challenge: str) -> str:
        return self.port.authorize_url(state, code_challenge)

    async def exchange(self, candidate_id: UUID, code: str, code_verifier: str) -> tuple[str, bool]:
        identity = await self.port.exchange_code(code, code_verifier)
        await self._bind(candidate_id, identity.participant_id, "oauth", True)
        return identity.participant_id, True

    # ------------------------------------------------------------ код / ручной ID
    async def start(
        self, candidate_id: UUID, participant_id: str | None, email: str | None
    ) -> tuple[Method, MaskedContact | None]:
        pid = await self._resolve(participant_id, email)
        await self._ensure_free(candidate_id, pid, "code")
        participant = await self.port.get_participant(pid)
        if participant.email_masked is None and participant.phone_masked is None:
            await self._bind(candidate_id, pid, "manual", False)  # контакта нет: код слать некуда
            return "manual", None
        masked = await self.port.send_verification_code(pid)
        key = pending_key(candidate_id)
        await self.redis.delete(key)
        await self.redis.hset(key, mapping={"participant_id": pid, "attempts": 0})
        await self.redis.expire(key, self.code_ttl)
        return "code", masked

    async def link_manual(self, candidate_id: UUID, participant_id: str) -> None:
        """Явный ручной ID без проверки (ссылка «нет доступа к почте»)."""
        await self.port.get_participant(participant_id)  # 404, если такого нет
        await self._bind(candidate_id, participant_id, "manual", False)

    async def bind_registry(self, candidate_id: UUID, participant_id: str) -> None:
        """Реестр (ADR-052): совпали контакты аккаунта или админ принял заявку — подтверждено."""
        await self._bind(candidate_id, participant_id, "registry", True)

    async def verify(self, candidate_id: UUID, code: str) -> bool:
        key = pending_key(candidate_id)
        pid_raw = await self.redis.hget(key, "participant_id")
        if pid_raw is None:
            raise ProblemError(410, "code_expired", "Код истёк, запросите новый")
        attempts = await self.redis.hincrby(key, "attempts", 1)
        if attempts > self.max_attempts:
            raise ProblemError(
                429, "too_many_attempts", "Слишком много попыток, запросите новый код"
            )
        pid = pid_raw.decode() if isinstance(pid_raw, bytes) else pid_raw
        if not await self.port.check_verification_code(pid, code):
            return False
        await self._bind(candidate_id, pid, "code", True)
        await self.redis.delete(key)
        return True

    # ------------------------------------------------------------ внутреннее
    async def _resolve(self, participant_id: str | None, email: str | None) -> str:
        if participant_id:
            return participant_id
        if not email:
            raise ProblemError(422, "validation_error", "Нужен participant_id или email")
        found = await self.port.find_participant(email=email)
        if not found:
            raise FspNotFound(email)
        if len(found) > 1:
            raise ProblemError(409, "fsp_ambiguous", "Найдено несколько участников, укажите ID")
        return found[0].id

    async def _ensure_free(self, candidate_id: UUID, pid: str, method: str) -> None:
        async with self.sessions() as s:
            await self._check(s, candidate_id, pid, method)

    async def _check(
        self, s: AsyncSession, candidate_id: UUID, pid: str, method: str
    ) -> FspLink | None:
        """Проверки уникальности; возвращает свою же существующую привязку."""
        by_pid = (
            await s.execute(select(FspLink).where(FspLink.participant_id == pid))
        ).scalar_one_or_none()
        if by_pid is not None and by_pid.candidate_id != candidate_id:
            await self._record_conflict(candidate_id, pid, method)
            raise ProblemError(
                409, "fsp_already_linked", "Этот участник ФСП уже привязан к другому аккаунту"
            )
        mine = await s.get(FspLink, candidate_id)
        if mine is not None and mine.participant_id != pid:
            raise ProblemError(
                409, "candidate_already_linked", "К аккаунту уже привязан другой участник ФСП"
            )
        return mine

    async def _record_conflict(self, candidate_id: UUID, pid: str, method: str) -> None:
        async with session_scope(self.sessions) as s:
            s.add(FspLinkConflict(candidate_id=candidate_id, participant_id=pid, method=method))

    async def _bind(self, candidate_id: UUID, pid: str, method: Method, verified: bool) -> None:
        try:
            async with session_scope(self.sessions) as s:
                mine = await self._check(s, candidate_id, pid, method)
                if mine is not None:
                    if mine.verified or not verified:
                        return  # повтор или понижение: ничего не меняем, события нет
                    mine.verified, mine.method = True, method
                else:
                    s.add(
                        FspLink(
                            candidate_id=candidate_id,
                            participant_id=pid,
                            verified=verified,
                            method=method,
                        )
                    )
                await publish_linked(
                    s,
                    FspLinked(
                        candidate_id=candidate_id,
                        participant_id=pid,
                        verified=verified,
                        method=method,
                    ),
                )
        except IntegrityError:  # гонка двух привязок одного participant_id
            await self._record_conflict(candidate_id, pid, method)
            raise ProblemError(
                409, "fsp_already_linked", "Этот участник ФСП уже привязан к другому аккаунту"
            ) from None


def token_ok(expected: str, authorization: str | None) -> bool:
    scheme, _, token = (authorization or "").partition(" ")
    return bool(expected) and scheme == "Service" and hmac.compare_digest(token, expected)
