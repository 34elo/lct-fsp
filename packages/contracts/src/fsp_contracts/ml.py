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


class SkillCardDraftRequest(BaseModel):
    """`POST /v1/skills/card-draft`: черновик карточки для нового (provisional) навыка (E16-4)."""

    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["hard", "soft", "domain"] = "hard"
    skill_type: (
        Literal["fundamental", "hard", "thinking", "business", "soft", "experience"] | None
    ) = None
    description: str | None = Field(default=None, max_length=500)
    aliases: list[str] = Field(default_factory=list, max_length=20)


class SkillCardConcept(BaseModel):
    term: str = Field(min_length=1, max_length=80)
    note: str = Field(min_length=3, max_length=300)


class SkillCardMisconception(BaseModel):
    claim: str = Field(min_length=3, max_length=300)
    truth: str = Field(min_length=3, max_length=300)


class SkillCardDraft(BaseModel):
    """Форма карточки `data/skills/cards/*.yaml` (core `taxonomy/cards.py`, `schema_version` 1).

    Это всегда черновик: в `data/skills/cards` он попадает только после проверки человеком.
    """

    schema_version: Literal[1] = 1
    skill: str
    type: Literal["fundamental", "hard", "thinking", "business", "soft", "experience"]
    summary: str = Field(min_length=10, max_length=400)
    levels: dict[Literal["junior", "middle", "senior"], list[str]]
    concepts: list[SkillCardConcept] = Field(min_length=3)
    misconceptions: list[SkillCardMisconception] = Field(min_length=2)
    model: str  # чем сделан: имя LLM или `rules-template`
    draft: Literal[True] = True


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


# --- Черновик ключа задания конструктора (assessment.md §4, §7; E30-1) ---

FamilyKind = Literal["exact", "estimate", "choice", "find_bug", "order", "sjt", "open"]


class FamilyKeyDraftRequest(BaseModel):
    """Пример варианта задания без ключа: ml-api предлагает ключ и рубрику (черновик)."""

    kind: FamilyKind
    stem: str = Field(max_length=6000)
    options: list[str] = Field(default_factory=list, max_length=8)  # choice, порядок автора
    lines: list[str] = Field(default_factory=list, max_length=60)  # find_bug, строки с 1
    actions: list[str] = Field(default_factory=list, max_length=8)  # sjt
    steps: list[str] = Field(default_factory=list, max_length=10)  # order, порядок автора
    rubric: list[str] = Field(default_factory=list, max_length=10)  # open: рубрика автора


class FamilyKeyDraft(BaseModel):
    """Черновик ключа: в оценке не используется, пока его не утвердит админ (ADR-024)."""

    correct: int | None = None  # choice: индекс в `options`
    bug_lines: list[int] | None = None  # find_bug: номера строк с 1
    scores: list[float] | None = None  # sjt: оценка эффективности каждого действия
    answer: float | str | None = None  # exact, estimate: примерный ответ на этот вариант
    rubric: list[str] | None = None  # open: пункты рубрики
    rationale: str | None = Field(default=None, max_length=1000)
    model: str = ""


# --- «Объясни ответ» (E24-2) ---


class AnswerExplainRequest(BaseModel):
    """Причину ошибки определил core по правилам; LLM только формулирует текст (без ПДн и ключа)."""

    kind: Literal[
        "exact", "estimate", "choice", "find_bug", "order", "sjt", "open", "chain"
    ]  # как FamilyKind + chain
    skill: str = Field(max_length=80)
    stem: str = Field(max_length=6000)
    reason_code: str = Field(max_length=40)
    reason_label: str = Field(max_length=200)
    misconception: str | None = Field(
        default=None, max_length=300
    )  # утверждение из карточки навыка
    truth: str | None = Field(default=None, max_length=300)  # как на самом деле


class AnswerExplain(BaseModel):
    text: str = Field(max_length=800)
    model: str = ""


# --- Офлайн-конвейер LLM-заданий (E26-4, ADR-024, assessment.md §7) ---


class FamilyGenerateRequest(BaseModel):
    """Заказ генератору: предложить `n` спецификаций семейства для навыка, `kind` и уровня."""

    skill: str = Field(min_length=1, max_length=80)  # slug из data/taxonomy
    skill_type: str = Field(default="", max_length=40)  # SkillType навыка (подсказка генератору)
    kind: FamilyKind
    level: int = Field(ge=1, le=5)
    domain: str | None = Field(default=None, max_length=40)  # e-commerce, fintech…
    n: int = Field(default=1, ge=1, le=5)


class FamilyGenerateResponse(BaseModel):
    """Черновики форм конструктора (`FamilySpec`); core проверяет их схемой и автопроверкой."""

    specs: list[dict[str, Any]] = Field(default_factory=list, max_length=5)
    model: str = ""


class FamilySolveRequest(BaseModel):
    """Вариант задания так, как его видит кандидат (без ключа): LLM решает его как кандидат."""

    kind: FamilyKind
    stem: str = Field(max_length=6000)
    options: list[str] = Field(default_factory=list, max_length=10)  # choice, order, sjt


class FamilySolveAnswer(BaseModel):
    """Ответ LLM в формате ответа кандидата: число/строка, индекс, строки дефекта, порядок."""

    answer: int | float | str | list[int] | None = None
    model: str = ""
