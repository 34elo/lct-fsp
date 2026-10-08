"""`POST /track` (web) и `POST /internal/track` (бот): приём событий интерфейса (E18-2).

Псевдоним `actor` и роль определяет сервер (по токену), клиентские значения не принимаются.
Имя события и `props` проверяет `analytics.service.record` по схемам трекинга (metrics.md §2.2):
неизвестное событие, чужой источник или лишнее поле отклоняются, ПДн в `props` не попадают.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fsp_contracts.analytics import MAX_TRACK_BATCH, AnalyticsEvent, Channel, Role, Source
from fsp_platform.app import ProblemError
from fsp_platform.jwt import TokenError, decode_token
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import service
from app.deps import get_redis, get_session
from app.identity.models import User
from app.openapi_errors import problem_responses

router = APIRouter(tags=["analytics"])
internal = APIRouter(prefix="/internal", tags=["internal"])

_ROLES = ("candidate", "employer", "fsp_admin")
RATE_LIMIT = 120  # запросов в минуту на пользователя или IP
BATCH_TTL = 600  # секунд хранения id батча для дедупликации повторной отправки


class TrackEventIn(BaseModel):
    """Событие от клиента: без `actor`, `role`, `channel` — их ставит сервер."""

    model_config = ConfigDict(extra="forbid")

    event: Annotated[str, Field(max_length=64)]
    ts: datetime
    session_id: Annotated[str, Field(max_length=64)] | None = None
    run_id: UUID | None = None
    app_version: Annotated[str, Field(max_length=32)] | None = None
    props: dict = Field(default_factory=dict)


class TrackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: Annotated[list[TrackEventIn], Field(min_length=1, max_length=MAX_TRACK_BATCH)]
    # id батча: повторная отправка того же батча (ретрай, sendBeacon) не дублирует события
    batch_id: Annotated[str, Field(min_length=8, max_length=64)] | None = None
    # `sendBeacon` не умеет заголовки: токен для псевдонима можно передать в теле
    access_token: Annotated[str, Field(max_length=2048)] | None = None


class BotTrackEventIn(TrackEventIn):
    user_id: UUID | None = None  # пользователь бота: core сам считает псевдоним
    role: Role = "anon"


class BotTrackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: Annotated[list[BotTrackEventIn], Field(min_length=1, max_length=MAX_TRACK_BATCH)]
    batch_id: Annotated[str, Field(min_length=8, max_length=64)] | None = None


class TrackOut(BaseModel):
    accepted: int
    rejected: int
    duplicate: bool = False


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "-")


def _token(request: Request, body_token: str | None) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return body_token


async def _who(
    request: Request, token: str | None, session: AsyncSession
) -> tuple[str | None, Role]:
    """Псевдоним и роль по токену; невалидный токен или неактивный пользователь = аноним."""
    if not token:
        return None, "anon"
    settings = request.app.state.settings
    try:
        user_id = UUID(decode_token(settings.jwt_secret, token)["sub"])
    except (TokenError, ValueError, KeyError):
        return None, "anon"
    user = await session.get(User, user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        return None, "anon"
    role: Role = user.role if user.role in _ROLES else "anon"  # type: ignore[assignment]
    return service.pseudonym(settings.analytics_salt, user.id), role


async def _first_batch(redis: Redis, scope: str, batch_id: str | None) -> bool:
    if not batch_id:
        return True
    key = "track:batch:" + hashlib.sha256(f"{scope}:{batch_id}".encode()).hexdigest()[:32]
    return bool(await redis.set(key, 1, nx=True, ex=BATCH_TTL))


def _envelope(
    ev: TrackEventIn, actor: str | None, role: Role, channel: Channel
) -> AnalyticsEvent | None:
    try:
        return AnalyticsEvent(
            event=ev.event,
            ts=ev.ts,
            actor=actor,
            role=role,
            session_id=ev.session_id,
            channel=channel,
            run_id=ev.run_id,
            app_version=ev.app_version,
            props=ev.props,
        )
    except ValueError:
        return None


async def _store(
    session: AsyncSession, envelopes: list[AnalyticsEvent | None], source: Source
) -> TrackOut:
    good = [e for e in envelopes if e is not None]
    saved = await service.record(session, good, source=source)
    return TrackOut(accepted=saved, rejected=len(envelopes) - saved)


@router.post(
    "/track", response_model=TrackOut, status_code=202, responses=problem_responses(422, 429)
)
async def track(
    body: TrackIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> TrackOut:
    """Батч событий интерфейса (до 50). Авторизация необязательна: без неё события анонимные."""
    actor, role = await _who(request, _token(request, body.access_token), session)
    scope = actor or _client_ip(request)
    await request.app.state.limiter.check(f"track:{scope}", RATE_LIMIT, 60)
    if not await _first_batch(redis, scope, body.batch_id):
        return TrackOut(accepted=0, rejected=0, duplicate=True)
    return await _store(session, [_envelope(e, actor, role, "web") for e in body.events], "web")


async def require_bot(request: Request, authorization: str | None = Header(default=None)) -> None:
    expected = request.app.state.settings.service_token_bot
    scheme, _, token = (authorization or "").partition(" ")
    if not (expected and scheme == "Service" and hmac.compare_digest(token, expected)):
        raise ProblemError(401, "unauthorized", "Нужен сервисный токен")


@internal.post(
    "/track",
    response_model=TrackOut,
    status_code=202,
    dependencies=[Depends(require_bot)],
    responses=problem_responses(401, 422),
)
async def internal_track(
    body: BotTrackIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> TrackOut:
    """События бота (канал `tg`): принимаются только события, разрешённые источнику `bot`."""
    if not await _first_batch(redis, "bot", body.batch_id):
        return TrackOut(accepted=0, rejected=0, duplicate=True)
    salt = request.app.state.settings.analytics_salt
    envelopes = [
        _envelope(
            e,
            service.pseudonym(salt, e.user_id) if e.user_id else None,
            e.role if e.user_id else "anon",
            "tg",
        )
        for e in body.events
    ]
    return await _store(session, envelopes, "bot")
