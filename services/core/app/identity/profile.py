"""Личный профиль пользователя: ФИО, должность, описание, аватар.

Профиль ведут сотрудники компаний и админ ФСП (у кандидата своя анкета —
`/candidates/me/profile`). Аватар — PNG/JPEG/WebP по сигнатуре, до 2 МБ, в MinIO;
отдаётся по `GET /users/{id}/avatar?v=` без авторизации: подпись приглашения
видна кандидату, а `<img>` не несёт Bearer-токен.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from fsp_platform.app import ProblemError
from fsp_platform.storage import ObjectStorage
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import User, UserProfile

PROFILE_ROLES = ("employer", "fsp_admin")
AVATAR_MAX_BYTES = 2 * 1024 * 1024
_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}


def sniff_image(data: bytes) -> str | None:
    """Расширение по сигнатуре файла (не по имени и не по Content-Type клиента)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def content_type(key: str) -> str:
    return _TYPES.get(key.rsplit(".", 1)[-1], "application/octet-stream")


def avatar_url(user_id: uuid.UUID, key: str | None) -> str | None:
    """Путь относительно API (`/api/v1` на gateway); `v` меняется с файлом — можно кешировать."""
    if not key:
        return None
    version = key.rsplit("/", 1)[-1].split(".", 1)[0]
    return f"/users/{user_id}/avatar?v={version}"


def check_image(data: bytes) -> str:
    """Расширение проверенной картинки или ошибка 422/413/415 (аватары и логотипы)."""
    if not data:
        raise ProblemError(422, "empty_file", "Пустой файл")
    if len(data) > AVATAR_MAX_BYTES:
        raise ProblemError(413, "file_too_large", "Файл больше 2 МБ")
    ext = sniff_image(data)
    if ext is None:
        raise ProblemError(415, "unsupported_file_type", "Нужна картинка PNG, JPEG или WebP")
    return ext


def image_key(prefix: str, data: bytes, ext: str) -> str:
    return f"{prefix}/{hashlib.sha256(data).hexdigest()[:16]}.{ext}"


async def get(session: AsyncSession, user_id: uuid.UUID) -> UserProfile | None:
    return await session.get(UserProfile, user_id)


async def get_or_create(session: AsyncSession, user_id: uuid.UUID) -> UserProfile:
    row = await session.get(UserProfile, user_id)
    if row is None:
        row = UserProfile(user_id=user_id)
        session.add(row)
        await session.flush()
    return row


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


async def update(session: AsyncSession, user_id: uuid.UUID, changes: dict) -> UserProfile:
    """Частичное обновление: пустая строка или `null` очищает поле."""
    row = await get_or_create(session, user_id)
    for key in ("full_name", "position", "about"):
        if key in changes:
            setattr(row, key, _clean(changes[key]))
    await session.flush()
    return row


async def set_avatar(
    session: AsyncSession, storage: ObjectStorage, user_id: uuid.UUID, data: bytes
) -> UserProfile:
    ext = check_image(data)
    row = await get_or_create(session, user_id)
    old = row.avatar_key
    key = image_key(f"avatars/{user_id}", data, ext)
    await storage.put(key, data, _TYPES[ext])
    row.avatar_key = key
    await session.flush()
    if old and old != key:
        try:
            await storage.delete(old)
        except Exception:  # старый файл не мешает: ссылка уже другая
            pass
    return row


async def clear_avatar(
    session: AsyncSession, storage: ObjectStorage, user_id: uuid.UUID
) -> UserProfile:
    row = await get_or_create(session, user_id)
    if row.avatar_key:
        old, row.avatar_key = row.avatar_key, None
        await session.flush()
        try:
            await storage.delete(old)
        except Exception:
            pass
    return row


async def public_avatar(session: AsyncSession, user_id: uuid.UUID) -> str:
    """Ключ аватара для публичной выдачи: только сотрудники компаний и админ ФСП, иначе 404."""
    user = await session.get(User, user_id)
    row = await session.get(UserProfile, user_id)
    if (
        user is None
        or user.deleted_at is not None
        or user.role not in PROFILE_ROLES
        or row is None
        or not row.avatar_key
    ):
        raise ProblemError(404, "avatar_not_found", "Аватар не найден")
    return row.avatar_key


@dataclass(frozen=True)
class Signature:
    """Подпись приглашения: кто из компании его отправил (без email и телефона)."""

    full_name: str
    position: str | None
    avatar_url: str | None


async def signature(session: AsyncSession, user_id: uuid.UUID | None) -> Signature | None:
    """Подпись сотрудника; нет ФИО — подписи нет (кандидат видит только компанию)."""
    if user_id is None:
        return None
    row = await session.get(UserProfile, user_id)
    if row is None or not row.full_name:
        return None
    return Signature(row.full_name, row.position, avatar_url(user_id, row.avatar_key))
