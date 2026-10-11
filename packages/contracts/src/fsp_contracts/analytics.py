"""Схемы продуктовых событий аналитики.

Конверт `AnalyticsEvent` + модель `props` на каждое событие трекинг-плана.
Модели строгие (`extra="forbid"`): неизвестное событие или лишнее поле отклоняются.
В `props` только числа, флаги, перечисления и короткие slug'и: свободного текста и ПДн нет
`actor` — псевдоним `HMAC(id, ANALYTICS_SALT)`, не id.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal["candidate", "employer", "fsp_admin", "anon"]
Channel = Literal["web", "tg", "system"]
Source = Literal["server", "web", "bot"]

# slug навыка / роли / метрики: латиница, цифры и . + # _ - (без пробелов и свободного текста)
Slug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9.+#_-]{0,63}$")]
Nat = Annotated[int, Field(ge=0)]
Pct = Annotated[float, Field(ge=0, le=100)]


class _Props(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- кандидат ---


class SignupCompleted(_Props):
    channel: Literal["web", "tg"]
    method: Literal["email", "tg", "fsp"] | None = None


class ConsentProps(_Props):
    type: Slug


class ResumeUploaded(_Props):
    mime: Annotated[str, Field(pattern=r"^[a-z]+/[a-z0-9.+-]{1,60}$")]
    pages: Nat | None = None


class ResumeParsed(_Props):
    duration_ms: Nat | None = None
    skills_found: Nat
    skills_dropped_no_quote: Nat | None = None
    new_skills: Nat | None = None
    ok: bool


class ResumeConfirmed(_Props):
    edits_count: Nat | None = None
    skills_added: Nat | None = None
    skills_removed: Nat | None = None


class FspLinkStarted(_Props):
    method: Literal["oauth", "code", "manual", "registry"]


class FspLinkCompleted(_Props):
    method: Literal["oauth", "code", "manual", "registry"]
    verified: bool
    duration_ms: Nat | None = None
    results_imported: Nat | None = None


class GithubAnalysisCompleted(_Props):
    repos: Nat
    deep_repos: Nat
    flags: Nat
    duration_ms: Nat | None = None
    ok: bool = True


class ProfileUpdated(_Props):
    profile_version: Annotated[int, Field(ge=1)]
    skills_up: Nat
    skills_new: Nat = 0
    grade_from: Slug | None = None
    grade_to: Slug | None = None
    trigger: Slug | None = None


class SkillTestStarted(_Props):
    skill: Slug
    questions: Nat | None = None
    channel: Literal["web", "tg"] | None = None


class SkillTestCompleted(_Props):
    skill: Slug
    questions: Nat | None = None
    theta: float | None = None
    level_from: Annotated[int, Field(ge=0, le=4)] | None = None
    level_to: Annotated[int, Field(ge=0, le=4)] | None = None
    channel: Literal["web", "tg"] | None = None


class InterviewCompleted(_Props):
    questions: Nat
    avg_score: float | None = None


class UpliftProps(_Props):
    skill: Slug
    pct: Pct | None = None
    position: Nat | None = None
    action: Literal["test", "github", "competition"] | None = None


class CompetitionClicked(_Props):
    competition_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
    skill: Slug | None = None
    source: Literal["navigator", "uplift"]


class GraphOpened(_Props):
    nodes: Nat
    from_: Literal["profile", "card"] = Field(alias="from")

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)


class OfferReceived(_Props):
    offer_id: UUID
    channel: Literal["web", "tg"] | None = None
    score: float | None = None
    p_accept: float | None = None


class OfferOpened(_Props):
    offer_id: UUID
    channel: Literal["web", "tg"] | None = None


class OfferAccepted(_Props):
    offer_id: UUID
    time_to_respond_s: Nat | None = None
    channel: Literal["web", "tg"] | None = None


class OfferDeclined(OfferAccepted):
    reason: Slug | None = None


class OfferQuestionAsked(_Props):
    offer_id: UUID


class SkillRequestProps(_Props):
    skill: Slug


# --- работодатель ---


class Empty(_Props):
    pass


class VacancyPublished(_Props):
    version: Annotated[int, Field(ge=1)] | None = None
    role: Slug | None = None
    grade: Slug | None = None
    required_skills: Nat | None = None
    salary_range_ratio: float | None = None
    qualities: Nat | None = None


class SalaryRangeWarningShown(_Props):
    ratio: float


class MarketCellClicked(_Props):
    role: Slug
    grade: Slug | None = None
    metric: Slug | None = None


class SearchSubmitted(_Props):
    query_len: Nat
    chips: Nat
    parse_source: Literal["rule", "llm", "cache"]
    latency_ms: Nat | None = None
    refining: bool = False


class ChipProps(_Props):
    key: Slug
    source: Literal["rule", "llm"]


class ResultsShown(_Props):
    n: Nat
    latency_ms: Nat | None = None
    context: Literal["search", "vacancy", "similar"]
    session_id: Annotated[str, Field(max_length=64)] | None = None


class CardOpened(_Props):
    position: Nat
    score: float | None = None
    context: Literal["search", "vacancy", "similar"] | None = None


class CardDwell(_Props):
    seconds: Annotated[float, Field(ge=0, le=86400)]


class CardDecision(_Props):
    position: Nat | None = None
    reason: Slug | None = None


class RecAdjustmentApplied(_Props):
    features_changed: Nat


class GraphPathHighlighted(_Props):
    requirement: Slug


class SalaryHintShown(_Props):
    below_min: bool
    vs_median: float | None = None
    p_accept_bucket: Slug | None = None


class OfferSent(_Props):
    offer_id: UUID | None = None
    score: float | None = None
    p_accept: float | None = None
    below_min: bool | None = None


class InterviewKitGenerated(_Props):
    questions: Nat


# --- админ и система ---


class SkillNodeCreated(_Props):
    kind: Slug
    decision: Slug | None = None
    context: Slug | None = None


class SkillDecisionByAdmin(_Props):
    decision: Literal["merge", "distinct", "approve", "reject"]
    auto_suggestion: Literal["merge", "distinct", "approve", "reject"] | None = None


class SkillPromoted(_Props):
    support: Nat


class RecomputeDone(_Props):
    duration_ms: Nat
    evidence: Nat | None = None
    trigger: Slug | None = None


class MatchesComputed(_Props):
    vacancy_id: UUID
    candidates: Nat
    duration_ms: Nat | None = None


# событие → (модель props, допустимые источники)
_S: tuple[Source, ...] = ("server",)
_W: tuple[Source, ...] = ("web",)
_WB: tuple[Source, ...] = ("web", "bot")

ANALYTICS_EVENTS: dict[str, tuple[type[_Props], tuple[Source, ...]]] = {
    # кандидат
    "signup_completed": (SignupCompleted, _S),
    "consent_granted": (ConsentProps, _S),
    "consent_revoked": (ConsentProps, _S),
    "resume_uploaded": (ResumeUploaded, _S),
    "resume_parsed": (ResumeParsed, _S),
    "resume_confirmed": (ResumeConfirmed, _S),
    "fsp_link_started": (FspLinkStarted, _S),
    "fsp_link_completed": (FspLinkCompleted, _S),
    "github_analysis_completed": (GithubAnalysisCompleted, _S),
    "profile_updated": (ProfileUpdated, _S),
    "test_started": (SkillTestStarted, _S),
    "test_completed": (SkillTestCompleted, _S),
    "interview_completed": (InterviewCompleted, _S),
    "uplift_shown": (UpliftProps, _WB),
    "uplift_clicked": (UpliftProps, _WB),
    "competition_clicked": (CompetitionClicked, _WB),
    "graph_opened": (GraphOpened, _W),
    "offer_received": (OfferReceived, _S),
    "offer_opened": (OfferOpened, _S),
    "offer_accepted": (OfferAccepted, _S),
    "offer_declined": (OfferDeclined, _S),
    "offer_question_asked": (OfferQuestionAsked, _S),
    "skill_request_received": (SkillRequestProps, _S),
    "skill_request_completed": (SkillRequestProps, _S),
    # работодатель
    "company_registered": (Empty, _S),
    "company_verified": (Empty, _S),
    "vacancy_published": (VacancyPublished, _S),
    "salary_range_warning_shown": (SalaryRangeWarningShown, _W),
    "market_cell_clicked": (MarketCellClicked, _W),
    "search_submitted": (SearchSubmitted, _S),
    "chip_edited": (ChipProps, _W),
    "chip_removed": (ChipProps, _W),
    "results_shown": (ResultsShown, _S),
    "card_opened": (CardOpened, _S),
    "card_dwell": (CardDwell, _W),
    "shortlisted": (CardDecision, _S),
    "dismissed": (CardDecision, _S),
    "rec_adjustment_applied": (RecAdjustmentApplied, _S),
    "graph_path_highlighted": (GraphPathHighlighted, _W),
    "salary_hint_shown": (SalaryHintShown, _S),
    "offer_sent": (OfferSent, _S),
    "interview_kit_generated": (InterviewKitGenerated, _S),
    "skill_test_requested": (SkillRequestProps, _S),
    # админ и система
    "skill_node_created": (SkillNodeCreated, _S),
    "skill_decision_by_admin": (SkillDecisionByAdmin, _S),
    "skill_promoted": (SkillPromoted, _S),
    "recompute_done": (RecomputeDone, _S),
    "matches_computed": (MatchesComputed, _S),
}

# события теста и подбора; имена не должны пересекаться с общим списком
from fsp_contracts.analytics_assessment import ASSESSMENT_ANALYTICS_EVENTS  # noqa: E402
from fsp_contracts.analytics_hiring import HIRING_ANALYTICS_EVENTS  # noqa: E402

for _extra in (ASSESSMENT_ANALYTICS_EVENTS, HIRING_ANALYTICS_EVENTS):
    _dup = set(_extra) & set(ANALYTICS_EVENTS)
    if _dup:
        raise RuntimeError(f"дубли имён событий аналитики: {sorted(_dup)}")
    ANALYTICS_EVENTS.update(_extra)

MAX_TRACK_BATCH = 50  # до 50 событий в запросе


class AnalyticsEvent(BaseModel):
    """Конверт события; `props` проверяет `validate_event`."""

    model_config = ConfigDict(extra="forbid")

    event: str
    ts: datetime
    actor: Annotated[str, Field(pattern=r"^a_[0-9a-f]{16,64}$")] | None = None
    role: Role = "anon"
    session_id: Annotated[str, Field(max_length=64)] | None = None
    channel: Channel = "web"
    run_id: UUID | None = None
    app_version: Annotated[str, Field(max_length=32)] | None = None
    props: dict = Field(default_factory=dict)

    @field_validator("ts")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("ts должен быть в UTC с часовым поясом")
        return v


class UnknownAnalyticsEvent(ValueError):
    pass


def validate_event(event: AnalyticsEvent, source: Source = "server") -> AnalyticsEvent:
    """Проверка имени, источника и `props`; возвращает событие с нормализованными `props`.

    Исключения: `UnknownAnalyticsEvent` (нет в трекинг-плане или не из этого источника),
    `pydantic.ValidationError` (лишнее или неверное поле).
    """
    spec = ANALYTICS_EVENTS.get(event.event)
    if spec is None:
        raise UnknownAnalyticsEvent(event.event)
    model, sources = spec
    if source not in sources:
        raise UnknownAnalyticsEvent(f"{event.event}: источник {source} не допускается")
    props = model.model_validate(event.props).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    return event.model_copy(update={"props": props})


__all__ = [
    "ANALYTICS_EVENTS",
    "MAX_TRACK_BATCH",
    "AnalyticsEvent",
    "UnknownAnalyticsEvent",
    "validate_event",
]
