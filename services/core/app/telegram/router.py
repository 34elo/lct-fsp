"""`/me/telegram/link` и internal API для бота (api.md §2.1, §2.9)."""

from __future__ import annotations

import hmac
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fsp_platform.app import ProblemError
from fsp_platform.ratelimit import RateLimiter
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_limiter, get_redis, get_session
from app.identity.deps import get_current_user
from app.identity.models import User
from app.telegram import service

router = APIRouter(tags=["telegram"])
internal = APIRouter(prefix="/internal", tags=["internal"])


async def require_bot(request: Request, authorization: str | None = Header(default=None)) -> None:
    """`Authorization: Service <token>` (security.md §1); пустой токен в настройках = закрыто."""
    expected = request.app.state.settings.service_token_bot
    scheme, _, token = (authorization or "").partition(" ")
    if not (expected and scheme == "Service" and hmac.compare_digest(token, expected)):
        raise ProblemError(401, "unauthorized", "Нужен сервисный токен")


class DeepLinkOut(BaseModel):
    deep_link: str


@router.post("/me/telegram/link", response_model=DeepLinkOut)
async def my_link(
    request: Request,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
    limiter: RateLimiter = Depends(get_limiter),
):
    await limiter.check(f"tglink:user:{user.id}", 10, 60)
    link = await service.create_link_deep_link(
        redis, request.app.state.settings.tg_bot_username, user.id
    )
    return DeepLinkOut(deep_link=link)


class StartIn(BaseModel):
    tg_user_id: int
    chat_id: int
    username: str | None = Field(default=None, max_length=64)
    start_param: str | None = Field(default=None, max_length=256)


class StartOut(BaseModel):
    user_id: UUID
    role: str
    missing_consents: list[str]
    # True, если Telegram связан с аккаунтом сайта (email/пароль), а не только заготовкой бота
    linked: bool


@internal.post("/tg/start", response_model=StartOut, dependencies=[Depends(require_bot)])
async def tg_start(body: StartIn, session: AsyncSession = Depends(get_session)):
    # start_param (`link_<token>`, `ref_<source>`) обрабатывает бот: link — отдельным вызовом
    user, _ = await service.ensure_user(session, body.tg_user_id, body.chat_id, body.username)
    return StartOut(
        user_id=user.id,
        role=user.role,
        missing_consents=await service.missing_consents(session, user.id),
        linked=user.email is not None,
    )


class ConsentsIn(BaseModel):
    tg_user_id: int
    types: list[str] = Field(max_length=10)


async def _user_by_tg(session: AsyncSession, tg_user_id: int) -> User:
    acc = await service.account_by_tg(session, tg_user_id)
    user = await session.get(User, acc.user_id) if acc else None
    if user is None or not user.is_active or user.deleted_at is not None:
        raise ProblemError(404, "telegram_unknown", "Аккаунт Telegram не найден")
    return user


@internal.post("/tg/consents", status_code=204, dependencies=[Depends(require_bot)])
async def tg_consents(body: ConsentsIn, session: AsyncSession = Depends(get_session)):
    user = await _user_by_tg(session, body.tg_user_id)
    await service.grant_consents(session, user.id, body.types)


class LinkIn(BaseModel):
    tg_user_id: int
    token: str = Field(min_length=1, max_length=256)


class LinkOut(BaseModel):
    user_id: UUID
    linked: bool = True


@internal.post("/tg/link", response_model=LinkOut, dependencies=[Depends(require_bot)])
async def tg_link(
    body: LinkIn,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    limiter: RateLimiter = Depends(get_limiter),
):
    await limiter.check(f"tglink:tg:{body.tg_user_id}", 10, 60)
    acc = await service.link_by_token(session, redis, body.tg_user_id, body.token)
    return LinkOut(user_id=acc.user_id)


class MagicLinkIn(BaseModel):
    tg_user_id: int
    redirect: str = Field(default="/", max_length=512)


class MagicLinkOut(BaseModel):
    url: str


@internal.post("/auth/magic-link", response_model=MagicLinkOut, dependencies=[Depends(require_bot)])
async def magic_link(
    body: MagicLinkIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    limiter: RateLimiter = Depends(get_limiter),
):
    await limiter.check(f"magiclink:tg:{body.tg_user_id}", 5, 60)
    url = await service.create_magic_link(
        session, redis, request.app.state.settings.web_base_url, body.tg_user_id, body.redirect
    )
    return MagicLinkOut(url=url)
