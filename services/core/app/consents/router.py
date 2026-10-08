from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from fsp_contracts.enums import ConsentType
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.consents import service
from app.deps import get_session
from app.identity.deps import get_current_user
from app.identity.models import User
from app.openapi_errors import problem_responses

router = APIRouter(tags=["consents"])


class ConsentOut(BaseModel):
    type: ConsentType
    required: bool
    granted: bool
    version: str | None  # версия выданного текста
    current_version: str
    granted_at: datetime | None


class ConsentChange(BaseModel):
    type: ConsentType
    granted: bool
    version: str | None = None  # версия текста, которую увидел пользователь


class ConsentsIn(BaseModel):
    consents: list[ConsentChange] = Field(min_length=1, max_length=len(ConsentType))


async def list_out(session: AsyncSession, user: User) -> list[ConsentOut]:
    act = await service.active(session, user.id)
    out = []
    for t in ConsentType:
        c = act.get(t.value)
        out.append(
            ConsentOut(
                type=t,
                required=t in service.REQUIRED,
                granted=c is not None,
                version=c.version if c else None,
                current_version=service.CURRENT_VERSIONS[t],
                granted_at=c.granted_at if c else None,
            )
        )
    return out


@router.get("/me/consents", response_model=list[ConsentOut], responses=problem_responses(401))
async def get_consents(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    return await list_out(session, user)


@router.put("/me/consents", response_model=list[ConsentOut], responses=problem_responses(401, 422))
async def put_consents(
    body: ConsentsIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await service.set_consents(
        session, user.id, [(c.type, c.granted, c.version) for c in body.consents]
    )
    return await list_out(session, user)
