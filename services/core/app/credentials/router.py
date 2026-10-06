"""Open Badge 3.0 (api.md §2.4 `/me/credentials`, §2.7 публичные, E18-9)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fsp_platform.app import ProblemError
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.credentials import service
from app.credentials.models import IssuedCredential
from app.deps import get_session
from app.identity.deps import require_roles
from app.identity.models import User
from app.openapi_errors import problem_responses

router = APIRouter(tags=["credentials"])
_candidate = require_roles("candidate")
_JSONLD = "application/ld+json"


def _issuer(request: Request) -> service.Issuer:
    return service.Issuer.from_settings(request.app.state.settings)


class CredentialIssueIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profession: str | None = None


class CredentialOut(BaseModel):
    id: uuid.UUID
    profession: str
    grade: str
    url: str
    issued_at: datetime
    valid_until: str
    revoked_at: datetime | None = None
    credential: dict[str, Any]


class CredentialCheckOut(BaseModel):
    id: str | None
    valid: bool
    signature_valid: bool
    known: bool
    revoked: bool
    expired: bool
    issuer: str
    checked_at: str


def _out(issuer: service.Issuer, row: IssuedCredential) -> CredentialOut:
    return CredentialOut(
        id=row.id,
        profession=row.profession,
        grade=row.grade,
        url=service.credential_url(issuer, row.id),
        issued_at=row.issued_at,
        valid_until=row.credential["validUntil"],
        revoked_at=row.revoked_at,
        credential=row.credential,
    )


@router.post(
    "/me/credentials",
    response_model=CredentialOut,
    status_code=201,
    responses=problem_responses(401, 403, 404, 409),
)
async def issue_credential(
    body: CredentialIssueIn,
    request: Request,
    user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
):
    """Выпустить Open Badge на действующую категорию. Тот же грейд повторно: тот же бейдж."""
    issuer = _issuer(request)
    row = await service.issue(session, issuer, user.id, body.profession)
    return _out(issuer, row)


@router.get(
    "/me/credentials", response_model=list[CredentialOut], responses=problem_responses(401, 403)
)
async def my_credentials(
    request: Request,
    user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
):
    issuer = _issuer(request)
    return [_out(issuer, r) for r in await service.list_own(session, user.id)]


@router.post(
    "/me/credentials/{credential_id}/revoke",
    response_model=CredentialOut,
    responses=problem_responses(401, 403, 404),
)
async def revoke_credential(
    credential_id: uuid.UUID,
    request: Request,
    user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
):
    """Отозвать свой бейдж. Чужой или несуществующий: 404."""
    row = await service.revoke_own(session, user.id, credential_id)
    return _out(_issuer(request), row)


@router.get(
    "/public/credentials/{credential_id}",
    response_class=Response,
    responses={200: {"content": {_JSONLD: {}}}, **problem_responses(404)},
)
async def get_credential(credential_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    """Подписанный OpenBadgeCredential (JSON-LD). Скрыт, если отозван или профиль не публичный."""
    row = await service.get_public(session, credential_id)
    if row is None:
        raise ProblemError(404, "credential_not_found", "Бейдж не найден")
    return Response(
        content=json.dumps(row.credential, ensure_ascii=False),
        media_type=_JSONLD,
        headers={"Cache-Control": "public, max-age=60"},
    )


@router.get(
    "/public/credentials/{credential_id}/verify",
    response_model=CredentialCheckOut,
    responses=problem_responses(404),
)
async def verify_credential(
    credential_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session)
):
    """Подпись, отзыв, срок. Отозванный бейдж: `200 {valid:false, revoked:true}`."""
    result = await service.verify(session, _issuer(request), credential_id)
    if result is None:
        raise ProblemError(404, "credential_not_found", "Бейдж не найден")
    return result


@router.post("/public/credentials/verify", response_model=CredentialCheckOut)
async def verify_presented(
    credential: dict[str, Any], request: Request, session: AsyncSession = Depends(get_session)
):
    """Проверка предъявленного документа (например, файла из кабинета): подделка → `valid:false`."""
    return await service.verify_document(session, _issuer(request), credential)


@router.get("/.well-known/did.json", include_in_schema=True)
async def did_document(request: Request):
    """Публичный ключ издателя (`did:web`)."""
    return Response(
        content=json.dumps(_issuer(request).did_document()),
        media_type="application/did+json",
        headers={"Cache-Control": "public, max-age=300"},
    )
