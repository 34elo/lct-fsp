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
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.identity.mailer import Mailer
from app.identity.models import EmailVerification, RefreshToken, User, utcnow
from app.identity.profile import signature as staff_signature  # noqa: F401  (E39-24)

REFRESH_TTL = timedelta(days=30)
ACCESS_TTL = timedelta(minutes=15)
SELF_REGISTER_ROLES = {"candidate", "employer"}

_hasher = PasswordHasher()
# Хеш для выравнивания времени ответа, когда пользователя нет
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")
# E40-1: домен демо-аккаунтов (seed, жюри); такие пользователи помечаются `is_demo`
DEMO_EMAIL_DOMAIN = "@demo.fsp.test"


def is_demo_email(email: str | None) -> bool:
    """Демо-аккаунт: email в домене `demo.fsp.test` (вымышленный, письма туда не доходят)."""
    return bool(email) and str(email).lower().endswith(DEMO_EMAIL_DOMAIN)


async def is_demo_user(session: AsyncSession, user_id: uuid.UUID | None) -> bool:
    """Пользователь помечен как демо (E40-1)."""
    if user_id is None:
        return False
    return bool(await session.scalar(select(User.is_demo).where(User.id == user_id)))


def demo_user_ids():
    """Подзапрос id демо-пользователей (кандидат: `candidate_id = user_id`) — для фильтров."""
    return select(User.id).where(User.is_demo.is_(True))


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
    user = User(
        email=email, password_hash=_hasher.hash(password), role=role, is_demo=is_demo_email(email)
    )
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


def is_email_verified(user: User, *, required: bool | None = None) -> bool:
    """`True`, если проверка выключена (`EMAIL_VERIFICATION_REQUIRED=false`) или email подтверждён.

    `required` переопределяет настройку (для тестов); по умолчанию читается из окружения.
    """
    if required is None:
        required = Settings().email_verification_required
    return not required or user.email_verified_at is not None


def require_verified_email(user: User, *, required: bool | None = None) -> None:
    """403 `email_not_verified`, если проверка включена, а email не подтверждён."""
    if not is_email_verified(user, required=required):
        raise ProblemError(403, "email_not_verified", "Подтвердите email")


def _code_hash(user_id: uuid.UUID, code: str) -> str:
    return hash_token(f"{user_id}:{code}")


async def send_verification_code(
    session: AsyncSession,
    mailer: Mailer,
    settings: Settings,
    user: User,
    *,
    now: datetime | None = None,
) -> None:
    """Новый 6-значный код (старый аннулируется) и письмо. 409 `cooldown` — слишком часто."""
    if user.email is None:
        raise ProblemError(409, "email_missing", "У аккаунта нет email")
    now = now or datetime.now(UTC)
    row = await session.get(EmailVerification, user.id)
    if row is not None:
        ready = _aware(row.sent_at) + timedelta(seconds=settings.email_resend_cooldown_seconds)
        if ready > now:
            raise ProblemError(
                409, "cooldown", "Код уже отправлен", f"Повторить можно после {ready.isoformat()}"
            )
    code = f"{secrets.randbelow(10**6):06d}"
    expires = now + timedelta(minutes=settings.email_code_ttl_minutes)
    if row is None:
        session.add(
            EmailVerification(
                user_id=user.id,
                code_hash=_code_hash(user.id, code),
                expires_at=expires,
                sent_at=now,
            )
        )
    else:
        row.code_hash, row.expires_at, row.sent_at, row.attempts = (
            _code_hash(user.id, code),
            expires,
            now,
            0,
        )
    await session.flush()
    await mailer.send(
        user.email,
        "Код подтверждения email — ФСП Карьера",
        f"Ваш код: {code}\nОн действует {settings.email_code_ttl_minutes} минут.",
    )


async def verify_code(
    session: AsyncSession, settings: Settings, user: User, code: str, *, now: datetime | None = None
) -> bool:
    """True — подтверждён (повтор после успеха тоже True); False — неверный код: вызывающий
    обязан зафиксировать транзакцию (счётчик попыток) и ответить 400 `invalid_code`.
    Истёкший код → 400 `code_expired`, исчерпаны попытки → 429 `too_many_attempts`."""
    if user.email_verified_at is not None:
        return True
    now = now or datetime.now(UTC)
    row = await session.get(EmailVerification, user.id)
    if row is None:
        return False
    if row.attempts >= settings.email_code_max_attempts:
        raise ProblemError(429, "too_many_attempts", "Слишком много попыток", "Запросите новый код")
    if _aware(row.expires_at) <= now:
        raise ProblemError(400, "code_expired", "Код истёк", "Запросите новый код")
    if not secrets.compare_digest(row.code_hash, _code_hash(user.id, code.strip())):
        row.attempts += 1
        return False
    user.email_verified_at = now
    await session.delete(row)
    return True


def password_matches(user: User, password: str) -> bool:
    """Проверка пароля владельца (подтверждение необратимых действий)."""
    if not user.password_hash:
        return False
    try:
        _hasher.verify(user.password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    return True


async def change_password(
    session: AsyncSession, user: User, current: str, new: str, keep_raw: str | None
) -> None:
    """Смена пароля (E39-8): сверка текущего, новый хеш, чужие сессии закрываются.

    Сессия с refresh-токеном `keep_raw` (текущая вкладка) остаётся. Нет пароля
    (вход через Telegram) или неверный текущий — 403 `wrong_password`.
    """
    if not password_matches(user, current):
        raise ProblemError(403, "wrong_password", "Неверный текущий пароль")
    user.password_hash = _hasher.hash(new)
    keep_family = None
    if keep_raw:
        keep_family = await session.scalar(
            select(RefreshToken.family_id).where(RefreshToken.token_hash == hash_token(keep_raw))
        )
    stmt = (
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    if keep_family is not None:
        stmt = stmt.where(RefreshToken.family_id != keep_family)
    await session.execute(stmt)
    await session.flush()


async def erase_user(session: AsyncSession, user: User) -> None:
    """Удаление профиля (F13): обезличить учётную запись, закрыть сессии и коды."""
    await session.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))
    await session.execute(delete(EmailVerification).where(EmailVerification.user_id == user.id))
    user.email = None
    user.password_hash = None
    user.email_verified_at = None
    user.is_active = False
    user.deleted_at = utcnow()
    await session.flush()
