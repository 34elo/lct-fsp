"""Реестр ФСП: кнопка «Привязать ФСП», заявка кандидата, раздел админа.

Хранилище — fsp-connector (`/internal/registry/*`); core проверяет права и передаёт контакты
аккаунта. Права: кандидат — только своё (без ID в пути), админ — роль `fsp_admin`.
ПДн (email, телефон, ФИО) в логи не пишем.
"""

from __future__ import annotations

import uuid
from datetime import date as Date
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fsp_contracts.enums import FspDiscipline, FspLevel
from fsp_platform.ratelimit import RateLimiter
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service as candidates
from app.deps import get_limiter, get_session
from app.fsp.client import ConnectorClient
from app.fsp.router import get_connector, owner, writer
from app.identity.deps import require_roles
from app.identity.models import User
from app.openapi_errors import problem_responses

router = APIRouter(tags=["fsp"])
admin_router = APIRouter(prefix="/admin/fsp", tags=["admin"])
_admin = require_roles("fsp_admin")


# ------------------------------------------------------------------------------ схемы
class RegistryLinkOut(BaseModel):
    linked: bool
    matched_by: Literal["email", "phone"] | None = None
    participant_id: str | None = None


RequestStatus = Literal["pending", "accepted", "rejected"]


class FspRequestIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=32)
    event: str | None = Field(default=None, max_length=200)


class FspRequestOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str | None = None
    phone: str | None = None
    event: str | None = None
    status: RequestStatus
    reason: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


class RegistryEventIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    discipline: FspDiscipline
    level: FspLevel
    date: Date


class RegistryEventPatch(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    discipline: FspDiscipline | None = None
    level: FspLevel | None = None
    date: Date | None = None


class RegistryEventOut(BaseModel):
    id: str
    title: str
    discipline: FspDiscipline
    level: FspLevel
    date: Date
    results: int = 0


class RegistryParticipantIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=32)


class RegistryParticipantOut(BaseModel):
    id: str
    full_name: str
    email: str | None = None
    phone: str | None = None
    linked: bool = False


class CsvImportIn(BaseModel):
    csv: str = Field(min_length=1, max_length=1_000_000)


class CsvImportError(BaseModel):
    line: int
    reason: str


class CsvImportOut(BaseModel):
    created: int
    updated: int
    errors: list[CsvImportError]


class RegistryResultIn(BaseModel):
    participant_id: str = Field(min_length=1, max_length=64)
    event_id: str = Field(min_length=1, max_length=64)
    place: int | None = Field(default=None, ge=1, le=100000)
    team: str | None = Field(default=None, max_length=120)


class RegistryResultOut(BaseModel):
    id: int
    participant_id: str
    participant_name: str
    event_id: str
    event_title: str
    place: int | None = None
    team: str | None = None


class AdminFspRequestOut(FspRequestOut):
    candidate_id: uuid.UUID
    participant_id: str | None = None
    candidates: list[RegistryParticipantOut] = Field(
        default_factory=list, description="Участники реестра с теми же контактами — подсказка"
    )


class FspRequestAcceptIn(BaseModel):
    participant_id: str = Field(min_length=1, max_length=64)


class FspRequestRejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class RegistryResultIdOut(BaseModel):
    id: int


class ResultsImportIn(BaseModel):
    """`commit=false` — превью (dry-run), `true` — запись; повтор идемпотентен."""

    csv: str = Field(min_length=1, max_length=1_000_000)
    commit: bool = False
    skip_errors: bool = Field(
        default=False, description="Записать годные строки, ошибочные пропустить"
    )
    create_events: list[str] = Field(
        default_factory=list,
        max_length=1000,
        description="Ключи новых мероприятий из превью, создание которых подтверждено",
    )
    default_discipline: FspDiscipline = FspDiscipline.algorithmic
    default_level: FspLevel = FspLevel.regional


class ResultsImportLine(BaseModel):
    line: int
    participant: str
    participant_id: str | None = None
    participant_name: str | None = None
    event: str
    date: str | None = None
    result: str | None = None
    status: Literal["ok", "error"]
    action: Literal["create", "update", "unchanged"] | None = None
    error: str | None = Field(default=None, description="Машинный код ошибки строки")
    new_event_key: str | None = None


class ResultsImportNewEvent(BaseModel):
    key: str
    title: str
    date: Date
    discipline: FspDiscipline
    level: FspLevel
    rows: int
    confirmed: bool = False


class ResultsImportSummary(BaseModel):
    total: int
    errors: int
    created: int
    updated: int
    unchanged: int


class ResultsImportOut(BaseModel):
    committed: bool
    summary: ResultsImportSummary
    new_events: list[ResultsImportNewEvent]
    lines: list[ResultsImportLine]


# ------------------------------------------------------------------------------ кандидат
async def _ensure_candidate(request: Request, session: AsyncSession, user: User):
    return await candidates.get_or_create(
        session, user.id, request.app.state.settings.pseudo_id_secret
    )


@router.post(
    "/candidates/me/fsp/registry-link",
    response_model=RegistryLinkOut,
    responses=problem_responses(401, 403, 409, 429, 503),
)
async def fsp_registry_link(
    request: Request,
    user: User = Depends(writer),
    session: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_limiter),
    connector: ConnectorClient = Depends(get_connector),
):
    """Кнопка «Привязать ФСП»: ищем в реестре email аккаунта и телефон из контактов.

    Совпал ровно один участник — привязка сразу (`fsp.linked`, затем синхронизация достижений);
    иначе `linked=false` и кандидат заполняет заявку.
    """
    await limiter.check(f"fspreg:{user.id}", 10, 600)
    cand = await _ensure_candidate(request, session, user)
    await session.commit()  # кандидат должен существовать до события fsp.linked
    contacts = candidates.contacts_of(cand, request.app.state.settings.pii_key)
    emails = [e for e in (user.email, contacts.get("email")) if e]
    phones = [p for p in (contacts.get("phone"),) if p]
    data = await connector.registry(
        "POST",
        "/match",
        json={"candidate_id": str(user.id), "emails": emails, "phones": phones},
    )
    return RegistryLinkOut(**data)


@router.get(
    "/candidates/me/fsp/request",
    response_model=FspRequestOut | None,
    responses=problem_responses(401, 403, 503),
)
async def fsp_my_request(
    user: User = Depends(owner), connector: ConnectorClient = Depends(get_connector)
):
    """Последняя заявка кандидата на привязку (или `null`)."""
    data = await connector.registry("GET", f"/requests/by-candidate/{user.id}")
    return FspRequestOut(**data) if data else None


@router.post(
    "/candidates/me/fsp/requests",
    status_code=201,
    response_model=FspRequestOut,
    responses=problem_responses(401, 403, 409, 422, 429, 503),
)
async def fsp_create_request(
    body: FspRequestIn,
    request: Request,
    user: User = Depends(writer),
    session: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_limiter),
    connector: ConnectorClient = Depends(get_connector),
):
    """Заявка админу: ФИО, email/телефон, под которыми кандидат участвовал, мероприятие."""
    await limiter.check(f"fspreq:{user.id}", 5, 600)
    await _ensure_candidate(request, session, user)
    await session.commit()
    data = await connector.registry(
        "POST", "/requests", json={"candidate_id": str(user.id), **body.model_dump()}
    )
    return FspRequestOut(**data)


# ------------------------------------------------------------------------------ админ
@admin_router.get(
    "/events", response_model=list[RegistryEventOut], responses=problem_responses(401, 403, 503)
)
async def registry_events(
    _: User = Depends(_admin), connector: ConnectorClient = Depends(get_connector)
):
    return await connector.registry("GET", "/events")


@admin_router.post(
    "/events",
    status_code=201,
    response_model=RegistryEventOut,
    responses=problem_responses(401, 403, 422, 503),
)
async def registry_create_event(
    body: RegistryEventIn,
    _: User = Depends(_admin),
    connector: ConnectorClient = Depends(get_connector),
):
    return await connector.registry("POST", "/events", json=body.model_dump(mode="json"))


@admin_router.patch(
    "/events/{event_id}",
    response_model=RegistryEventOut,
    responses=problem_responses(401, 403, 404, 422, 503),
)
async def registry_update_event(
    event_id: str,
    body: RegistryEventPatch,
    _: User = Depends(_admin),
    connector: ConnectorClient = Depends(get_connector),
):
    return await connector.registry(
        "PATCH",
        f"/events/{event_id}",
        json=body.model_dump(mode="json", exclude_unset=True, exclude_none=True),
    )


@admin_router.get(
    "/participants",
    response_model=list[RegistryParticipantOut],
    responses=problem_responses(401, 403, 503),
)
async def registry_participants(
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(_admin),
    connector: ConnectorClient = Depends(get_connector),
):
    params: dict[str, str | int] = {"limit": limit}
    if q:
        params["q"] = q
    return await connector.registry("GET", "/participants", params=params)


@admin_router.post(
    "/participants",
    status_code=201,
    response_model=RegistryParticipantOut,
    responses=problem_responses(401, 403, 409, 422, 503),
)
async def registry_create_participant(
    body: RegistryParticipantIn,
    _: User = Depends(_admin),
    connector: ConnectorClient = Depends(get_connector),
):
    return await connector.registry("POST", "/participants", json=body.model_dump())


@admin_router.post(
    "/participants/import",
    response_model=CsvImportOut,
    responses=problem_responses(401, 403, 422, 503),
)
async def registry_import_participants(
    body: CsvImportIn,
    _: User = Depends(_admin),
    connector: ConnectorClient = Depends(get_connector),
):
    """CSV «ФИО, email, телефон» (`,` или `;`, заголовок необязателен).

    Совпал email или телефон — запись обновляется.
    """
    return await connector.registry("POST", "/participants/import", json=body.model_dump())


@admin_router.get(
    "/results", response_model=list[RegistryResultOut], responses=problem_responses(401, 403, 503)
)
async def registry_results(
    event_id: str | None = Query(default=None, max_length=64),
    participant_id: str | None = Query(default=None, max_length=64),
    _: User = Depends(_admin),
    connector: ConnectorClient = Depends(get_connector),
):
    params = {
        k: v for k, v in {"event_id": event_id, "participant_id": participant_id}.items() if v
    }
    return await connector.registry("GET", "/results", params=params)


@admin_router.put(
    "/results",
    response_model=RegistryResultIdOut,
    responses=problem_responses(401, 403, 404, 422, 503),
)
async def registry_upsert_result(
    body: RegistryResultIn,
    _: User = Depends(_admin),
    connector: ConnectorClient = Depends(get_connector),
):
    """Результат участника на мероприятии (повтор — правка). Привязанному кандидату — пересчёт."""
    return await connector.registry("PUT", "/results", json=body.model_dump())


@admin_router.delete(
    "/results/{result_id}", status_code=204, responses=problem_responses(401, 403, 404, 503)
)
async def registry_delete_result(
    result_id: int,
    _: User = Depends(_admin),
    connector: ConnectorClient = Depends(get_connector),
):
    await connector.registry("DELETE", f"/results/{result_id}")
    return Response(status_code=204)


@admin_router.post(
    "/registry/import",
    response_model=ResultsImportOut,
    responses=problem_responses(401, 403, 422, 503),
)
async def registry_import_results(
    body: ResultsImportIn,
    _: User = Depends(_admin),
    connector: ConnectorClient = Depends(get_connector),
):
    """Результаты списком: CSV `участник;мероприятие;дата;результат`, до 1000 строк.

    Без `commit` — превью с построчной проверкой. С `commit` — запись и пересчёт профилей
    затронутых кандидатов (outbox). Новые мероприятия создаются только по `create_events`.
    """
    return await connector.registry("POST", "/results/import", json=body.model_dump(mode="json"))


@admin_router.get(
    "/requests",
    response_model=list[AdminFspRequestOut],
    responses=problem_responses(401, 403, 503),
)
async def registry_requests(
    status: RequestStatus | None = None,
    _: User = Depends(_admin),
    connector: ConnectorClient = Depends(get_connector),
):
    return await connector.registry("GET", "/requests", params={"status": status} if status else {})


@admin_router.post(
    "/requests/{request_id}/accept",
    response_model=AdminFspRequestOut,
    responses=problem_responses(401, 403, 404, 409, 503),
)
async def registry_accept_request(
    request_id: uuid.UUID,
    body: FspRequestAcceptIn,
    _: User = Depends(_admin),
    connector: ConnectorClient = Depends(get_connector),
):
    """Принять заявку: кандидат привязывается к выбранному участнику реестра."""
    return await connector.registry(
        "POST", f"/requests/{request_id}/accept", json=body.model_dump()
    )


@admin_router.post(
    "/requests/{request_id}/reject",
    response_model=AdminFspRequestOut,
    responses=problem_responses(401, 403, 404, 409, 422, 503),
)
async def registry_reject_request(
    request_id: uuid.UUID,
    body: FspRequestRejectIn,
    _: User = Depends(_admin),
    connector: ConnectorClient = Depends(get_connector),
):
    return await connector.registry(
        "POST", f"/requests/{request_id}/reject", json=body.model_dump()
    )
