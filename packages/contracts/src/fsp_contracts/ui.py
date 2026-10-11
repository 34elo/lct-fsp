"""Сообщения для SSE: обменник `ui` (topic), routing key `ui.user.<user_id>`.

core-api пересылает `UiMessage` своим SSE-соединениям как `event: <event>`, `data: <data>`.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from fsp_contracts.enums import OfferStatus
from fsp_contracts.events import ProfileDiff

UI_EXCHANGE = "ui"


def ui_routing_key(user_id: UUID | str) -> str:
    return f"ui.user.{user_id}"


class JobProgress(BaseModel):
    job_id: UUID
    kind: Literal["resume", "code", "interview", "fsp_sync"]
    stage: str
    pct: int = Field(ge=0, le=100)
    message: str


class ResumeStatus(BaseModel):
    """`resume.parsed` / `resume.failed`."""

    resume_id: UUID
    reason: str | None = None


class FspAchievementSkill(BaseModel):
    slug: str
    strength: float


class FspAchievementCompetition(BaseModel):
    id: str
    title: str
    discipline: str
    level: str
    date: str


class FspAchievementTeam(BaseModel):
    id: str
    name: str
    role: str


class FspAchievement(BaseModel):
    competition: FspAchievementCompetition
    stage: str
    place: int | None = None
    of: int | None = None
    team: FspAchievementTeam | None = None
    skills: list[FspAchievementSkill] = Field(default_factory=list)


class FspImported(BaseModel):
    new_achievements: list[FspAchievement]


class CodeAnalysisCompleted(BaseModel):
    analysis_id: UUID


class ProfileUpdated(BaseModel):
    profile_version: int
    diff: ProfileDiff


class OfferCreated(BaseModel):
    offer_id: UUID


class OfferUpdated(BaseModel):
    offer_id: UUID
    status: OfferStatus
    awaiting_reply_from: Literal["candidate", "company"] | None = None


class OfferMessage(BaseModel):
    offer_id: UUID
    message_id: UUID


class UiMatchesReady(BaseModel):
    vacancy_id: UUID
    count: int


class MatchesRationaleReady(BaseModel):
    vacancy_id: UUID
    candidate_pseudo_ids: list[str]


class NotificationNew(BaseModel):
    id: UUID
    type: str
    title: str


UI_EVENTS: dict[str, type[BaseModel]] = {
    "job.progress": JobProgress,
    "resume.parsed": ResumeStatus,
    "resume.failed": ResumeStatus,
    "fsp.imported": FspImported,
    "code.analysis.completed": CodeAnalysisCompleted,
    "profile.updated": ProfileUpdated,
    "offer.created": OfferCreated,
    "offer.updated": OfferUpdated,
    "offer.message": OfferMessage,
    "matches.ready": UiMatchesReady,
    "matches.rationale_ready": MatchesRationaleReady,
    "notification.new": NotificationNew,
}

UiEventName = Literal[
    "job.progress",
    "resume.parsed",
    "resume.failed",
    "fsp.imported",
    "code.analysis.completed",
    "profile.updated",
    "offer.created",
    "offer.updated",
    "offer.message",
    "matches.ready",
    "matches.rationale_ready",
    "notification.new",
]


class UiMessage(BaseModel):
    user_id: UUID
    event: UiEventName
    data: dict


def new_ui_message(user_id: UUID, event: UiEventName, data: BaseModel) -> UiMessage:
    expected = UI_EVENTS[event]
    if not isinstance(data, expected):
        raise TypeError(f"{event}: ожидается {expected.__name__}, получено {type(data).__name__}")
    return UiMessage(user_id=user_id, event=event, data=data.model_dump(mode="json"))
