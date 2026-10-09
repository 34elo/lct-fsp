"""Личный профиль: `GET|PATCH /me/profile`, `PUT|DELETE /me/avatar`, `GET /users/{id}/avatar`."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fsp_platform.app import ProblemError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_limiter, get_session, get_storage
from app.identity import profile
from app.identity.deps import require_roles
from app.identity.models import User, UserProfile
from app.openapi_errors import problem_responses

router = APIRouter(tags=["profile"])
_staff = require_roles(*profile.PROFILE_ROLES)

AVATAR_LIMIT = 20  # загрузок в час
AVATAR_WINDOW = 3600


class UserProfileOut(BaseModel):
    full_name: str | None = None
    position: str | None = None
    about: str | None = None
    avatar_url: str | None = None


class UserProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, max_length=120)
    position: str | None = Field(default=None, max_length=120)
    about: str | None = Field(default=None, max_length=2000)


def profile_out(user_id: UUID, row: UserProfile | None) -> UserProfileOut:
    if row is None:
        return UserProfileOut()
    return UserProfileOut(
        full_name=row.full_name,
        position=row.position,
        about=row.about,
        avatar_url=profile.avatar_url(user_id, row.avatar_key),
    )


@router.get("/me/profile", response_model=UserProfileOut, responses=problem_responses(401, 403))
async def get_my_profile(
    user: User = Depends(_staff), session: AsyncSession = Depends(get_session)
):
    return profile_out(user.id, await profile.get(session, user.id))


@router.patch(
    "/me/profile", response_model=UserProfileOut, responses=problem_responses(401, 403, 422)
)
async def patch_my_profile(
    body: UserProfilePatch,
    user: User = Depends(_staff),
    session: AsyncSession = Depends(get_session),
):
    row = await profile.update(session, user.id, body.model_dump(exclude_unset=True))
    return profile_out(user.id, row)


@router.put(
    "/me/avatar",
    response_model=UserProfileOut,
    responses=problem_responses(401, 403, 413, 415, 422, 429),
)
async def put_my_avatar(
    request: Request,
    file: Annotated[UploadFile, File()],
    user: User = Depends(_staff),
    session: AsyncSession = Depends(get_session),
    storage=Depends(get_storage),
    limiter=Depends(get_limiter),
):
    """PNG, JPEG или WebP по сигнатуре, до 2 МБ; старый файл удаляется."""
    await limiter.check(f"avatar:{user.id}", AVATAR_LIMIT, AVATAR_WINDOW)
    data = await file.read(profile.AVATAR_MAX_BYTES + 1)
    if not getattr(request.app.state, "bucket_ready", False):  # лениво: MinIO не нужен для старта
        await storage.ensure_bucket()
        request.app.state.bucket_ready = True
    row = await profile.set_avatar(session, storage, user.id, data)
    return profile_out(user.id, row)


@router.delete("/me/avatar", response_model=UserProfileOut, responses=problem_responses(401, 403))
async def delete_my_avatar(
    user: User = Depends(_staff),
    session: AsyncSession = Depends(get_session),
    storage=Depends(get_storage),
):
    return profile_out(user.id, await profile.clear_avatar(session, storage, user.id))


@router.get(
    "/users/{user_id}/avatar",
    response_class=Response,
    responses={200: {"content": {"image/*": {}}}, **problem_responses(404)},
)
async def get_avatar(
    user_id: UUID,
    session: AsyncSession = Depends(get_session),
    storage=Depends(get_storage),
):
    """Без авторизации: аватары только сотрудников компаний и админа ФСП, остальным — 404."""
    key = await profile.public_avatar(session, user_id)
    try:
        data = await storage.get(key)
    except Exception as exc:  # файл пропал из хранилища
        raise ProblemError(404, "avatar_not_found", "Аватар не найден") from exc
    return Response(
        content=data,
        media_type=profile.content_type(key),
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )
