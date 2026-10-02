"""Регистрация, вход, ротация refresh-токенов с семьями (security.md §1)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fsp_platform.app import ProblemError
from fsp_platform.jwt import encode_token
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import RefreshToken, User

REFRESH_TTL = timedelta(days=30)
ACCESS_TTL = timedelta(minutes=15)
SELF_REGISTER_ROLES = {"candidate", "employer"}

_hasher = PasswordHasher()
# Хеш для выравнивания времени ответа, когда пользователя нет
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


@dataclass
class IssuedTokens:
    access_token: str
    refresh_token: str
    user: User


def make_access(secret: str, user: User) -> str:
    return encode_token(secret, str(user.id), user.role, ttl=ACCESS_TTL, jti=uuid.uuid4().hex)


async def register(session: AsyncSession, email: str, password: str, role: str) -> User:
    if role not in SELF_REGISTER_ROLES:
        raise ProblemError(422, "invalid_role", "Недопустимая роль")
    email = normalize_email(email)
    exists = await session.scalar(select(User.id).where(User.email == email))
    if exists:
        raise ProblemError(409, "email_taken", "Email уже зарегистрирован")
    user = User(email=email, password_hash=_hasher.hash(password), role=role)
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ProblemError(409, "email_taken", "Email уже зарегистрирован") from exc
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.email == normalize_email(email)))
    stored = user.password_hash if user and user.password_hash else _DUMMY_HASH
    try:
        _hasher.verify(stored, password)
        ok = user is not None and user.password_hash is not None
    except (VerifyMismatchError, InvalidHashError):
        ok = False
    if not ok or user is None or not user.is_active or user.deleted_at is not None:
        raise ProblemError(401, "invalid_credentials", "Неверный email или пароль")
    return user


async def _new_refresh(
    session: AsyncSession, user: User, family_id: uuid.UUID, user_agent: str | None
) -> str:
    raw = secrets.token_urlsafe(32)  # 256 бит
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            family_id=family_id,
            expires_at=datetime.now(UTC) + REFRESH_TTL,
            user_agent=(user_agent or None) and user_agent[:255],
        )
    )
    await session.flush()
    return raw


async def issue_tokens(
    session: AsyncSession, secret: str, user: User, user_agent: str | None = None
) -> IssuedTokens:
    """Новая сессия: новая семья refresh-токенов."""
    refresh = await _new_refresh(session, user, uuid.uuid4(), user_agent)
    return IssuedTokens(make_access(secret, user), refresh, user)


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def rotate(
    session: AsyncSession, secret: str, raw: str | None, user_agent: str | None = None
) -> IssuedTokens | None:
    """Ротация refresh. None — повторное использование: семья отозвана, вызывающий
    обязан зафиксировать транзакцию (не бросать исключение) и ответить 401."""
    unauthorized = ProblemError(401, "unauthorized", "Сессия недействительна")
    if not raw:
        raise unauthorized
    # FOR UPDATE: два одновременных refresh одним токеном не пройдут оба
    row = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)).with_for_update()
    )
    if row is None:
        raise unauthorized
    if row.revoked_at is not None:
        await _revoke_family(session, row.family_id)
        return None
    if _aware(row.expires_at) <= datetime.now(UTC):
        raise unauthorized
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        await _revoke_family(session, row.family_id)
        raise unauthorized
    row.revoked_at = datetime.now(UTC)
    new = await _new_refresh(session, user, row.family_id, user_agent)
    return IssuedTokens(make_access(secret, user), new, user)


async def logout(session: AsyncSession, raw: str | None) -> None:
    if not raw:
        return
    row = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw))
    )
    if row is not None:
        await _revoke_family(session, row.family_id)
