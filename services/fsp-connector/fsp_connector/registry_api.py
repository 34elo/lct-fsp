"""Internal API реестра ФСП для core-api (api.md §2.9, E39-28): `Authorization: Service <token>`.

Права (админ/кандидат) проверяет core; здесь — только сервисный токен.
"""

from __future__ import annotations

from datetime import date as Date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fsp_contracts.enums import FspDiscipline, FspLevel
from pydantic import BaseModel, Field

from fsp_connector.api import require_core
from fsp_connector.registry import RegistryService

router = APIRouter(prefix="/internal/registry", dependencies=[Depends(require_core)])


def get_registry(request: Request) -> RegistryService:
    return request.app.state.registry


class EventIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    discipline: FspDiscipline
    level: FspLevel
    date: Date


class EventPatch(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    discipline: FspDiscipline | None = None
    level: FspLevel | None = None
    date: Date | None = None


class ParticipantIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=32)


class CsvIn(BaseModel):
    csv: str = Field(max_length=1_000_000)


class ResultIn(BaseModel):
    participant_id: str = Field(min_length=1, max_length=64)
    event_id: str = Field(min_length=1, max_length=64)
    place: int | None = Field(default=None, ge=1, le=100000)
    team: str | None = Field(default=None, max_length=120)


class MatchIn(BaseModel):
    candidate_id: UUID
    emails: list[str] = Field(default_factory=list, max_length=5)
    phones: list[str] = Field(default_factory=list, max_length=5)


class MatchOut(BaseModel):
    linked: bool
    participant_id: str | None = None
    matched_by: Literal["email", "phone"] | None = None


class RequestIn(BaseModel):
    candidate_id: UUID
    full_name: str = Field(min_length=2, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=32)
    event: str | None = Field(default=None, max_length=200)


class AcceptIn(BaseModel):
    participant_id: str = Field(min_length=1, max_length=64)


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


# ------------------------------------------------------------------------ мероприятия
@router.get("/events")
async def list_events(reg: RegistryService = Depends(get_registry)) -> list[dict]:
    return await reg.list_events()


@router.post("/events", status_code=201)
async def create_event(body: EventIn, reg: RegistryService = Depends(get_registry)) -> dict:
    return await reg.create_event(body.model_dump(mode="json") | {"date": body.date})


@router.patch("/events/{event_id}")
async def update_event(
    event_id: str, body: EventPatch, reg: RegistryService = Depends(get_registry)
) -> dict:
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    data = {k: (v.value if hasattr(v, "value") else v) for k, v in data.items()}
    return await reg.update_event(event_id, data)


# ------------------------------------------------------------------------ участники
@router.get("/participants")
async def list_participants(
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    reg: RegistryService = Depends(get_registry),
) -> list[dict]:
    return await reg.list_participants(q, limit)


@router.post("/participants", status_code=201)
async def create_participant(
    body: ParticipantIn, reg: RegistryService = Depends(get_registry)
) -> dict:
    return await reg.create_participant(body.full_name, body.email, body.phone)


@router.post("/participants/import")
async def import_participants(body: CsvIn, reg: RegistryService = Depends(get_registry)) -> dict:
    return await reg.import_csv(body.csv)


class ResultsImportIn(BaseModel):
    csv: str = Field(min_length=1, max_length=1_000_000)
    commit: bool = False
    skip_errors: bool = False
    create_events: list[str] = Field(default_factory=list, max_length=1000)
    default_discipline: FspDiscipline = FspDiscipline.algorithmic
    default_level: FspLevel = FspLevel.regional


@router.post("/results/import")
async def import_results(body: ResultsImportIn, reg: RegistryService = Depends(get_registry)):
    return await reg.import_results(
        body.csv,
        commit=body.commit,
        skip_errors=body.skip_errors,
        create_events=body.create_events,
        default_discipline=body.default_discipline.value,
        default_level=body.default_level.value,
    )


# ------------------------------------------------------------------------ результаты
@router.get("/results")
async def list_results(
    event_id: str | None = None,
    participant_id: str | None = None,
    reg: RegistryService = Depends(get_registry),
) -> list[dict]:
    return await reg.list_results(event_id, participant_id)


@router.put("/results")
async def upsert_result(body: ResultIn, reg: RegistryService = Depends(get_registry)) -> dict:
    rid = await reg.upsert_result(body.participant_id, body.event_id, body.place, body.team)
    return {"id": rid}


@router.delete("/results/{result_id}", status_code=204)
async def delete_result(result_id: int, reg: RegistryService = Depends(get_registry)) -> None:
    await reg.delete_result(result_id)


# ------------------------------------------------------------------------ привязка и заявки
@router.post("/match")
async def match(body: MatchIn, reg: RegistryService = Depends(get_registry)) -> MatchOut:
    res = await reg.match(body.candidate_id, body.emails, body.phones)
    return MatchOut(linked=res.linked, participant_id=res.participant_id, matched_by=res.matched_by)


@router.post("/requests", status_code=201)
async def create_request(body: RequestIn, reg: RegistryService = Depends(get_registry)) -> dict:
    return await reg.create_request(
        body.candidate_id, body.full_name, body.email, body.phone, body.event
    )


@router.get("/requests/by-candidate/{candidate_id}")
async def candidate_request(
    candidate_id: UUID, reg: RegistryService = Depends(get_registry)
) -> dict | None:
    return await reg.candidate_request(candidate_id)


@router.get("/requests")
async def list_requests(
    status: Literal["pending", "accepted", "rejected"] | None = None,
    reg: RegistryService = Depends(get_registry),
) -> list[dict]:
    return await reg.list_requests(status)


@router.post("/requests/{request_id}/accept")
async def accept_request(
    request_id: UUID, body: AcceptIn, reg: RegistryService = Depends(get_registry)
) -> dict:
    return await reg.accept_request(request_id, body.participant_id)


@router.post("/requests/{request_id}/reject")
async def reject_request(
    request_id: UUID, body: RejectIn, reg: RegistryService = Depends(get_registry)
) -> dict:
    return await reg.reject_request(request_id, body.reason)
