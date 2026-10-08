"""DTO ФСП, нормализованные (fsp.md §2–3). Порт и маппинги — в fsp-connector."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from fsp_contracts.enums import FspDiscipline, FspLevel, FspRankCode

FspStage = Literal["qualifier", "final"]
FspTeamRole = Literal["captain", "member", "individual"]


class FspResult(BaseModel):
    competition_id: str
    discipline: FspDiscipline
    stage: FspStage
    team_id: str | None = None
    team_role: FspTeamRole
    place: int | None = Field(default=None, ge=1)
    participants_total: int | None = Field(default=None, ge=1)  # участников или команд в зачёте
    score: float | None = None
    track: str | None = None  # трек хакатона, если есть
    date: date


class FspCompetition(BaseModel):
    id: str
    title: str
    discipline: FspDiscipline
    level: FspLevel
    format: Literal["online", "offline"]
    region: str | None = None
    start_date: date
    end_date: date | None = None
    status: Literal["announced", "registration", "ongoing", "finished"]
    tracks: list[str] = Field(default_factory=list)
    registration_url: str | None = None


class FspRank(BaseModel):
    discipline: FspDiscipline
    rank: FspRankCode
    assigned_at: date | None = None


class FspTeamMember(BaseModel):
    participant_id: str
    role: FspTeamRole


class FspTeam(BaseModel):
    id: str
    name: str
    competition_id: str
    members: list[FspTeamMember] = Field(default_factory=list)


class FspParticipant(BaseModel):
    """Полная карточка участника. ПДн: живёт только в fsp-connector и core, в события не идёт."""

    id: str
    last_name: str
    first_name: str
    middle_name: str | None = None
    birth_year: int | None = None
    region: str | None = None
    email_masked: str | None = None
    phone_masked: str | None = None
    ranks: list[FspRank] = Field(default_factory=list)


class FspParticipantBrief(BaseModel):
    id: str
    full_name_masked: str
    region: str | None = None
    birth_year: int | None = None


class FspStandingRow(BaseModel):
    place: int = Field(ge=1)
    team_id: str | None = None
    participant_ids: list[str] = Field(default_factory=list)
    score: float | None = None


class MaskedContact(BaseModel):
    channel: Literal["email", "phone"]
    masked: str


class FspOAuthIdentity(BaseModel):
    participant_id: str
    full_name: str | None = None


class FspWebhook(BaseModel):
    """Тело вебхука ФСП/мока → `POST /integrations/fsp/webhook` (подпись `X-Signature`)."""

    event_id: str
    type: Literal["result.published"]
    participant_id: str
    competition_id: str
    occurred_at: datetime
