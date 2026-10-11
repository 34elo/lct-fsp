"""Текущий пользователь и проверка ролей."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, Request
from fsp_platform.app import ProblemError
from fsp_platform.jwt import TokenError, decode_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.identity.models import User


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


async def _user_by_token(request: Request, session: AsyncSession) -> User:
    unauthorized = ProblemError(401, "unauthorized", "Нужна авторизация")
    token = _bearer(request)
    if not token:
        raise unauthorized
    try:
        user_id = UUID(decode_token(request.app.state.settings.jwt_secret, token)["sub"])
    except (TokenError, ValueError, KeyError) as exc:
        raise unauthorized from exc
    user = await session.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


async def get_user_pending_password(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User:
    """Вошедший пользователь, в том числе ещё не сменивший временный пароль.

    Только для `/me` и `/auth/password/initial`; остальные эндпоинты — `get_current_user`.
    """
    user = await _user_by_token(request, session)
    if not user.is_active or user.deleted_at is not None:
        raise ProblemError(401, "unauthorized", "Нужна авторизация")
    return user


async def get_current_user(
    user: User = Depends(get_user_pending_password),
) -> User:
    """Вошедший пользователь; временный пароль не сменён — `403 password_change_required`."""
    if user.must_change_password:
        raise ProblemError(
            403, "password_change_required", "Смените временный пароль", "Задайте свой пароль"
        )
    return user


async def get_user_even_deleted(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User:
    """Как `get_current_user`, но удалённого отдаёт как есть: повтор удаления профиля → 404."""
    return await _user_by_token(request, session)


def require_roles(*roles: str) -> Callable[..., User]:
    async def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise ProblemError(403, "forbidden", "Недостаточно прав")
        return user

    return dep
