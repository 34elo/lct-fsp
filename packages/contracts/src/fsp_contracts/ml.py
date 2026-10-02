"""DTO ML: ml-api (api.md §2.10, §3) и результаты задач ml-worker (ml.md §2, §7, §9, §10)."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from fsp_contracts.enums import (
    EmploymentType,
    Grade,
    RoleSlug,
    TrustLevel,
    WorkFormat,
)

# --- Резюме (ml.md §2, api.md §3 ParsedResume) ---


class ResumePerson(BaseModel):
    """ПДн: в логи и аналитику не попадает."""

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    telegram: str | None = None
    city: str | None = None
    links: list[str] = Field(default_factory=list)


class ResumeExperience(BaseModel):
    company: str | None = None
    title: str | None = None
    start: str | None = None  # YYYY-MM
    end: str | None = None  # None — по настоящее время
    description: str | None = None
    skills: list[str] = Field(default_factory=list)
    is_commercial: bool = True


class ResumeEducation(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field: str | None = None
    year_end: int | None = None


class ResumeSkill(BaseModel):
    raw: str
    slug: str | None = None
    quote: str  # дословная цитата из текста; без неё навык отбрасывается
    method: str  # alias | fuzzy | new | …
    confidence: float = Field(ge=0, le=1)


class ParsedResume(BaseModel):
    parser_version: str
    person: ResumePerson = Field(default_factory=ResumePerson)
    summary: str | None = None
    experience: list[ResumeExperience] = Field(default_factory=list)
    education: list[ResumeEducation] = Field(default_factory=list)
    skills: list[ResumeSkill] = Field(default_factory=list)
    unknown_skills: list[str] = Field(default_factory=list)
    total_experience_months: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)


# --- Поиск текстом (ml.md §7, api.md §3 SearchFilters/ParsedQuery) ---


class SkillRequirement(BaseModel):
    slug: str
    min_level: TrustLevel | None = None


class SearchFilters(BaseModel):
    roles: list[RoleSlug] | None = None
    grade_min: Grade | None = None
    grade_max: Grade | None = None
    skills_must: list[SkillRequirement] | None = None
    skills_nice: list[str] | None = None
    formats: list[WorkFormat] | None = None
    employment_types: list[EmploymentType] | None = None
    salary_max: int | None = Field(default=None, ge=0)  # ₽/мес
    cities: list[str] | None = None
    relocation_ok: bool | None = None
    min_trust: TrustLevel | None = None
    fsp_only: bool | None = None
    fsp_disciplines: list[str] | None = None
    active_only: bool | None = None
    semantic_text: str | None = None


class FilterChip(BaseModel):
    key: str  # имя поля SearchFilters
    value: Any
    label: str
    source: Literal["rule", "llm"]
    confidence: float = Field(ge=0, le=1)


class ParsedQuery(BaseModel):
    filters: SearchFilters
    chips: list[FilterChip] = Field(default_factory=list)
    unparsed: list[str] = Field(default_factory=list)
    refining: bool = False


class QueryParseRequest(BaseModel):
    text: str
    rule_hint: SearchFilters | None = None
    taxonomy_version: int


# --- Эмбеддинги ---


class EmbeddingsRequest(BaseModel):
    texts: list[str] = Field(min_length=1)
    kind: Literal["query", "passage"]


class EmbeddingsResponse(BaseModel):
    model: str
    dim: int
    vectors: list[list[float]]


# --- Сопоставление навыков (skills.md §3) ---


class SkillMention(BaseModel):
    raw: str
    context: str | None = None


class SkillsResolveRequest(BaseModel):
    mentions: list[SkillMention] = Field(min_length=1, max_length=50)
    taxonomy_version: int


class SkillRelationGuess(BaseModel):
    type: Literal["same", "narrower", "broader", "related"]
    to_slug: str
    confidence: float = Field(ge=0, le=1)


class SkillResolveItem(BaseModel):
    raw: str
    norm: str
    decision: Literal["alias", "fuzzy", "new", "same_pending", "rejected"]
    skill_slug: str | None = None
    kind: Literal["hard", "soft", "domain", "not_skill"]
    relation: SkillRelationGuess | None = None
    reason: str | None = None


class MlHealth(BaseModel):
    llm: Literal["up", "down"]
    embedder: Literal["up", "down"]
    model: str
    queue_depth: int


# --- Обоснования матчинга (ml.md §6.3, api.md §3 ExplanationItem) ---

ExplanationCode = Literal[
    "skill_confirmed",
    "skill_adjacent",
    "skill_missing",
    "skill_claimed_only",
    "fsp_achievement",
    "salary_fit",
    "salary_below_min",
    "grade_fit",
    "grade_mismatch",
    "format_fit",
    "active_search",
    "team_signal",
    "semantic_only",
]


class ExplanationItem(BaseModel):
    kind: Literal["plus", "minus", "warn"]
    code: ExplanationCode
    text: str
    skill: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    weight: float


class MatchToExplain(BaseModel):
    """Без ПДн: только вычисленные факторы (правило приватности для промптов)."""

    candidate_id: UUID
    profile_version: int
    score: float
    explanation: list[ExplanationItem]


class MatchRationale(BaseModel):
    candidate_id: UUID
    profile_version: int
    rationale: str


# --- ДНК кода (ml.md §9, data-model.md §3.6) ---

CodeFlag = Literal[
    "fork_no_changes", "giant_commit", "overnight", "author_mismatch", "template_like"
]


class CodeLanguage(BaseModel):
    lang: str
    share: float = Field(ge=0, le=1)
    loc_authored: int = 0


class CodeTechnology(BaseModel):
    skill: str
    strength: float = Field(ge=0, le=1)
    repos: list[str] = Field(default_factory=list)


class CodeRepo(BaseModel):
    full_name: str
    url: str
    is_fork: bool = False
    stars: int = 0
    pushed_at: str | None = None
    deep: bool = False
    own_commit_share: float | None = Field(default=None, ge=0, le=1)
    metrics: dict[str, Any] = Field(default_factory=dict)
    flags: list[CodeFlag] = Field(default_factory=list)
    contributors: list[dict[str, Any]] = Field(
        default_factory=list
    )  # {github_login, commits, share}


class CodeAnalysisResult(BaseModel):
    analyzer_version: str
    radar: dict[
        Literal["backend", "frontend", "devops", "data", "quality", "open_source"], float
    ] = Field(default_factory=dict)
    languages: list[CodeLanguage] = Field(default_factory=list)
    technologies: list[CodeTechnology] = Field(default_factory=list)
    maturity: dict[str, Any] = Field(default_factory=dict)
    flags: list[CodeFlag] = Field(default_factory=list)
    repos: list[CodeRepo] = Field(default_factory=list)
    summary: str | None = None  # 🚀 характеристика от LLM


# --- ИИ-интервью по коду (ml.md §10) ---


class InterviewQuestion(BaseModel):
    id: str
    file: str
    lines: str  # «120-168»
    snippet: str
    question: str
    rubric: list[str] = Field(min_length=3, max_length=5)
    difficulty: int = Field(ge=1, le=5)


class InterviewAnswer(BaseModel):
    question_id: str
    question: str
    rubric: list[str]
    snippet: str
    answer: str
    seconds: int = Field(ge=0)


class InterviewGrade(BaseModel):
    question_id: str
    score: int = Field(ge=0, le=3)
    matched_rubric: list[int] = Field(default_factory=list)
    rationale: str


# --- Вопросы для структурированного интервью (ml.md §10.1) ---


class KitSkill(BaseModel):
    slug: str
    level: TrustLevel
    sources: list[str] = Field(default_factory=list)
    claimed_only: bool = False


class KitGap(BaseModel):
    slug: str
    kind: Literal["below_required", "claimed_only", "adjacent_only"]
    required_level: TrustLevel | None = None
    current_level: TrustLevel | None = None
    adjacent_slug: str | None = None


class KitQuestion(BaseModel):
    skill: str
    purpose: Literal["strength", "gap"]
    question: str
    rubric: dict[Literal["weak", "good", "strong"], str]
    follow_ups: list[str] = Field(min_length=1, max_length=2)


# --- Черновики вопросов теста (ml.md §8) ---


class QuestionOption(BaseModel):
    id: str
    text: str


class QuestionDraft(BaseModel):
    text: str
    code: str | None = None
    options: list[QuestionOption] = Field(min_length=2)
    correct_option: str
    difficulty: int = Field(ge=1, le=5)
    explanation: str | None = None
