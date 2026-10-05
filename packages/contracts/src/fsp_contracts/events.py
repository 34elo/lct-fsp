"""Доменные события: обменник `events` (topic), routing key = `Envelope.type` (messaging.md §2.1).

Событие — «что-то случилось», подписаться может кто угодно. Payload без ПДн.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from fsp_contracts.assessment import ASSESSMENT_EVENTS
from fsp_contracts.enums import DeclineReason, Grade, OfferStatus, RoleSlug, TrustLevel
from fsp_contracts.fsp import FspCompetition, FspRank, FspResult, FspTeam
from fsp_contracts.hiring import HIRING_EVENTS
from fsp_contracts.ml import (
    CodeAnalysisResult,
    InterviewGrade,
    InterviewQuestion,
    KitQuestion,
    MatchRationale,
    ParsedResume,
    QuestionDraft,
    SkillResolveItem,
)

EVENTS_EXCHANGE = "events"

# --- candidate.* ---


class CandidateRegistered(BaseModel):
    candidate_id: UUID
    channel: Literal["web", "tg"]


class CandidatePreferencesUpdated(BaseModel):
    candidate_id: UUID
    fields: list[str]


class CandidateDeleted(BaseModel):
    candidate_id: UUID


class ResumeEvent(BaseModel):
    """`resume.parsed` / `resume.confirmed`."""

    resume_id: UUID
    candidate_id: UUID


class EvidenceChanged(BaseModel):
    candidate_id: UUID
    sources: list[str]


# --- skills.* ---


class SkillLevelChange(BaseModel):
    slug: str
    from_: TrustLevel | None = Field(default=None, alias="from")
    to: TrustLevel

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class GradeChange(BaseModel):
    from_: Grade | None = Field(default=None, alias="from")
    to: Grade

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class CategoryChange(BaseModel):
    from_: RoleSlug | None = Field(default=None, alias="from")
    to: RoleSlug

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class ProfileDiff(BaseModel):
    skills_up: list[SkillLevelChange] = Field(default_factory=list)
    skills_new: list[SkillLevelChange] = Field(default_factory=list)
    grade: GradeChange | None = None
    category: CategoryChange | None = None


class SkillsProfileUpdated(BaseModel):
    candidate_id: UUID
    profile_version: int = Field(ge=1)
    diff: ProfileDiff = Field(default_factory=ProfileDiff)


class CategoryDisputed(BaseModel):
    """Оспаривание категории кандидатом; комментарий (ПДн) в событие не попадает."""

    dispute_id: UUID
    candidate_id: UUID
    claimed_role: RoleSlug
    claimed_grade: Grade


class TaxonomyUpdated(BaseModel):
    version: int
    changed_skill_ids: list[UUID] = Field(default_factory=list)


# --- vacancy.*, matches.* ---


class VacancyEvent(BaseModel):
    """`vacancy.published` / `vacancy.updated` / `vacancy.closed`."""

    vacancy_id: UUID
    version: int = Field(ge=1)


class MatchesReady(BaseModel):
    vacancy_id: UUID
    count: int = Field(ge=0)


# --- offer.* ---


class OfferEvent(BaseModel):
    """Все `offer.*`.

    Для `offer.message` заполнен `message_id`, для `offer.declined` — `decline_reason`.
    """

    offer_id: UUID
    candidate_id: UUID
    company_id: UUID
    vacancy_id: UUID | None = None
    status: OfferStatus
    prev_status: OfferStatus | None = None
    actor: Literal["candidate", "company", "system"] = "system"
    message_id: UUID | None = None
    decline_reason: DeclineReason | None = None


# --- fsp.* (fsp-connector) ---


class FspLinked(BaseModel):
    candidate_id: UUID
    participant_id: str
    verified: bool
    method: Literal["oauth", "code", "manual"]


class FspResultsImported(BaseModel):
    candidate_id: UUID
    participant_id: str
    results: list[FspResult] = Field(default_factory=list)
    ranks: list[FspRank] = Field(default_factory=list)
    teams: list[FspTeam] = Field(default_factory=list)
    new: bool = False


class FspCompetitionsUpdated(BaseModel):
    competitions: list[FspCompetition]


# --- ml.* (ml-worker) ---


class MlResumeResult(BaseModel):
    """`ml.resume.completed` (есть `parsed`) / `ml.resume.failed` (есть `error`)."""

    resume_id: UUID
    candidate_id: UUID
    parsed: ParsedResume | None = None
    error: str | None = None  # машинный код: scanned_pdf, bad_file, llm_timeout, …


class MlCodeResult(BaseModel):
    """`ml.code.completed` / `ml.code.failed`."""

    analysis_id: UUID
    candidate_id: UUID
    result: CodeAnalysisResult | None = None
    error: str | None = None


class MlInterviewGenerated(BaseModel):
    interview_id: UUID
    candidate_id: UUID
    questions: list[InterviewQuestion] = Field(default_factory=list)
    error: str | None = None


class MlInterviewGraded(BaseModel):
    interview_id: UUID
    candidate_id: UUID
    grades: list[InterviewGrade] = Field(default_factory=list)
    total: float | None = None
    error: str | None = None


class MlInterviewKitGenerated(BaseModel):
    kit_id: UUID
    vacancy_id: UUID
    vacancy_version: int
    candidate_id: UUID
    profile_version: int
    questions: list[KitQuestion] = Field(default_factory=list)
    error: str | None = None


class MlSkillsResolved(BaseModel):
    request_id: UUID
    taxonomy_version: int
    items: list[SkillResolveItem]


class MlMatchesExplained(BaseModel):
    vacancy_id: UUID
    vacancy_version: int
    items: list[MatchRationale]


class MlQuestionsGenerated(BaseModel):
    skill_slug: str
    questions: list[QuestionDraft]


EVENTS: dict[str, type[BaseModel]] = {
    "candidate.registered": CandidateRegistered,
    "candidate.preferences.updated": CandidatePreferencesUpdated,
    "candidate.deleted": CandidateDeleted,
    "resume.parsed": ResumeEvent,
    "resume.confirmed": ResumeEvent,
    "evidence.changed": EvidenceChanged,
    "skills.profile.updated": SkillsProfileUpdated,
    "category.disputed": CategoryDisputed,
    "taxonomy.updated": TaxonomyUpdated,
    "vacancy.published": VacancyEvent,
    "vacancy.updated": VacancyEvent,
    "vacancy.closed": VacancyEvent,
    **{
        f"offer.{name}": OfferEvent
        for name in (
            "sent",
            "viewed",
            "accepted",
            "declined",
            "expired",
            "withdrawn",
            "message",
            "status_changed",
        )
    },
    "matches.ready": MatchesReady,
    "fsp.linked": FspLinked,
    "fsp.results.imported": FspResultsImported,
    "fsp.competitions.updated": FspCompetitionsUpdated,
    "ml.resume.completed": MlResumeResult,
    "ml.resume.failed": MlResumeResult,
    "ml.code.completed": MlCodeResult,
    "ml.code.failed": MlCodeResult,
    "ml.interview.generated": MlInterviewGenerated,
    "ml.interview.graded": MlInterviewGraded,
    "ml.interview_kit.generated": MlInterviewKitGenerated,
    "ml.skills.resolved": MlSkillsResolved,
    "ml.matches.explained": MlMatchesExplained,
    "ml.questions.generated": MlQuestionsGenerated,
    **ASSESSMENT_EVENTS,
    **HIRING_EVENTS,
}

# Кто публикует (для AsyncAPI и проверки producer в конверте).
EVENT_PRODUCERS: dict[str, str] = {
    t: ("fsp-connector" if t.startswith("fsp.") else "ml" if t.startswith("ml.") else "core")
    for t in EVENTS
}
