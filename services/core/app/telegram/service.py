"""Telegram: Login Widget, magic-ссылки, привязка по deep link (security.md §1, telegram.md)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fsp_contracts.enums import ConsentType
from fsp_platform.app import ProblemError
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.consents import service as consents
from app.identity.models import User
from app.telegram.models import TelegramAccount

MAGIC_TTL = 300  # 5 мин (security.md §1)
LINK_TTL = 900  # deep link с сайта живёт 15 мин
WIDGET_MAX_AGE = 24 * 3600
# Согласия, которые бот просит при первом /start
BOT_CONSENTS = (ConsentType.pd_processing, ConsentType.telegram_notifications)


def _key(kind: str, token: str) -> str:
    return f"{kind}:{hashlib.sha256(token.encode()).hexdigest()}"


# --- Login Widget -----------------------------------------------------------------------------


def verify_widget(data: dict[str, Any], bot_token: str, *, now: float | None = None) -> int:
    """Проверка данных Telegram Login Widget: HMAC-SHA256 с ключом SHA256(bot_token),
    `auth_date` не старше 24 ч. Возвращает tg_user_id."""
    bad = ProblemError(401, "invalid_telegram_auth", "Не удалось подтвердить вход через Telegram")
    if not bot_token:
        raise ProblemError(503, "telegram_login_disabled", "Вход через Telegram не настроен")
    got = str(data.get("hash", ""))
    fields = {k: str(v) for k, v in data.items() if k != "hash" and v is not None}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hashlib.sha256(bot_token.encode()).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not got or not hmac.compare_digest(expected, got.lower()):
        raise bad
    try:
        auth_date = int(fields["auth_date"])
        tg_id = int(fields["id"])
    except (KeyError, ValueError) as exc:
        raise bad from exc
    if (now if now is not None else time.time()) - auth_date > WIDGET_MAX_AGE:
        raise ProblemError(401, "telegram_auth_expired", "Данные входа устарели, повторите")
    return tg_id


def sign_widget(data: dict[str, Any], bot_token: str) -> str:
    """Подпись по правилам Telegram (для тестов и мок-виджета)."""
    check = "\n".join(f"{k}={data[k]}" for k in sorted(data) if k != "hash" and data[k] is not None)
    secret = hashlib.sha256(bot_token.encode()).digest()
    return hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()


# --- Аккаунты ---------------------------------------------------------------------------------


async def account_by_tg(session: AsyncSession, tg_user_id: int) -> TelegramAccount | None:
    return await session.scalar(
        select(TelegramAccount).where(TelegramAccount.tg_user_id == tg_user_id)
    )


async def account_of_user(session: AsyncSession, user_id: uuid.UUID) -> TelegramAccount | None:
    return await session.get(TelegramAccount, user_id)


async def is_linked(session: AsyncSession, user_id: uuid.UUID) -> bool:
    return await account_of_user(session, user_id) is not None


async def _active_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise ProblemError(401, "unauthorized", "Учётная запись недоступна")
    return user


async def ensure_user(
    session: AsyncSession, tg_user_id: int, chat_id: int, username: str | None
) -> tuple[User, TelegramAccount]:
    """Пользователь по tg_user_id; нет — создаём кандидата без email (data-model.md §3.1)."""
    acc = await account_by_tg(session, tg_user_id)
    if acc is None:
        user = User(role="candidate")
        session.add(user)
        await session.flush()
        acc = TelegramAccount(
            user_id=user.id, tg_user_id=tg_user_id, chat_id=chat_id, username=username
        )
        try:
            async with session.begin_nested():
                session.add(acc)
        except IntegrityError:  # гонка двух /start: аккаунт уже создан параллельно
            await session.delete(user)
            await session.flush()
            acc = await account_by_tg(session, tg_user_id)
            if acc is None:
                raise
    else:
        acc.chat_id, acc.username = chat_id, username
        await session.flush()
    return await _active_user(session, acc.user_id), acc


async def login_widget(session: AsyncSession, data: dict[str, Any], bot_token: str) -> User:
    """Вход (или регистрация кандидата) по данным Login Widget. В личном чате chat_id = user id."""
    tg_id = verify_widget(data, bot_token)
    user, _ = await ensure_user(session, tg_id, tg_id, data.get("username") or None)
    return user


async def missing_consents(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    have = await consents.active(session, user_id)
    return [str(t) for t in BOT_CONSENTS if str(t) not in have]


async def grant_consents(session: AsyncSession, user_id: uuid.UUID, types: list[str]) -> None:
    parsed = []
    for t in types:
        try:
            parsed.append((ConsentType(t), True, None))
        except ValueError as exc:
            raise ProblemError(422, "invalid_consent", f"Неизвестное согласие: {t}") from exc
    await consents.set_consents(session, user_id, parsed)


# --- Одноразовые токены (Redis GETDEL) ---------------------------------------------------------


async def _issue(redis: Redis, kind: str, user_id: uuid.UUID, ttl: int) -> str:
    token = secrets.token_urlsafe(32)  # 256 бит
    await redis.set(_key(kind, token), str(user_id), ex=ttl)
    return token


async def _consume(redis: Redis, kind: str, token: str) -> uuid.UUID | None:
    raw = await redis.getdel(_key(kind, token))
    if raw is None:
        return None
    return uuid.UUID(raw.decode() if isinstance(raw, bytes) else raw)


def safe_redirect(redirect: str) -> str:
    """Только путь внутри SPA: без схемы, хоста и `//` (защита от open redirect)."""
    if (
        not redirect.startswith("/")
        or redirect.startswith("//")
        or "\\" in redirect
        or any(ord(c) < 32 for c in redirect)
    ):
        raise ProblemError(422, "invalid_redirect", "Недопустимый адрес перехода")
    return redirect


async def create_magic_link(
    session: AsyncSession, redis: Redis, web_base_url: str, tg_user_id: int, redirect: str
) -> str:
    from urllib.parse import urlencode

    redirect = safe_redirect(redirect)
    acc = await account_by_tg(session, tg_user_id)
    if acc is None:
        raise ProblemError(404, "telegram_unknown", "Аккаунт Telegram не найден")
    await _active_user(session, acc.user_id)
    token = await _issue(redis, "magic", acc.user_id, MAGIC_TTL)
    return (
        f"{web_base_url.rstrip('/')}/auth/magic?{urlencode({'token': token, 'redirect': redirect})}"
    )


async def consume_magic(session: AsyncSession, redis: Redis, token: str) -> User:
    user_id = await _consume(redis, "magic", token)
    if user_id is None:
        raise ProblemError(
            401, "invalid_magic_token", "Ссылка недействительна или уже использована"
        )
    return await _active_user(session, user_id)


async def create_link_deep_link(redis: Redis, bot_username: str, user_id: uuid.UUID) -> str:
    if not bot_username:
        raise ProblemError(503, "telegram_disabled", "Бот Telegram не настроен")
    token = await _issue(redis, "tglink", user_id, LINK_TTL)
    return f"https://t.me/{bot_username.lstrip('@')}?start=link_{token}"


async def link_by_token(
    session: AsyncSession, redis: Redis, tg_user_id: int, token: str
) -> TelegramAccount:
    """Привязка Telegram к аккаунту с сайта. Заготовка бота (создана /start без email и пароля)
    сливается в аккаунт сайта: согласия переносятся, заготовка деактивируется."""
    target_id = await _consume(redis, "tglink", token)
    if target_id is None:
        raise ProblemError(410, "link_token_invalid", "Ссылка привязки недействительна")
    target = await _active_user(session, target_id)
    acc = await account_by_tg(session, tg_user_id)
    if acc is None:
        raise ProblemError(404, "telegram_unknown", "Сначала нажмите /start")
    if acc.user_id == target.id:
        return acc  # повтор безвреден
    if await account_of_user(session, target.id) is not None:
        raise ProblemError(
            409, "telegram_already_linked", "К аккаунту уже привязан другой Telegram"
        )
    old = await session.get(User, acc.user_id)
    if old is not None and (old.email is not None or old.password_hash is not None):
        raise ProblemError(
            409, "telegram_already_linked", "Этот Telegram привязан к другому аккаунту"
        )
    chat_id, username = acc.chat_id, acc.username
    if old is not None:
        granted = await consents.active(session, old.id)
        await consents.set_consents(
            session, target.id, [(ConsentType(t), True, None) for t in granted]
        )
        old.is_active = False
        old.deleted_at = datetime.now(UTC)
    await session.delete(acc)
    await session.flush()
    new = TelegramAccount(
        user_id=target.id, tg_user_id=tg_user_id, chat_id=chat_id, username=username
    )
    session.add(new)
    await session.flush()
    return new
