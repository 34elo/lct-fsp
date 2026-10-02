"""JWT: выпуск и проверка access-токенов."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt


class TokenError(Exception):
    pass


def encode_token(
    secret: str, subject: str, role: str, ttl: timedelta = timedelta(minutes=15), **claims: Any
) -> str:
    now = datetime.now(UTC)
    payload = {"sub": subject, "role": role, "iat": now, "exp": now + ttl, **claims}
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(secret: str, token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
