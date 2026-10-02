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


async def get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    unauthorized = ProblemError(401, "unauthorized", "Нужна авторизация")
    token = _bearer(request)
    if not token:
        raise unauthorized
    try:
        user_id = UUID(decode_token(request.app.state.settings.jwt_secret, token)["sub"])
    except (TokenError, ValueError, KeyError) as exc:
        raise unauthorized from exc
    user = await session.get(User, user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise unauthorized
    return user


def require_roles(*roles: str) -> Callable[..., User]:
    async def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise ProblemError(403, "forbidden", "Недостаточно прав")
        return user

    return dep
