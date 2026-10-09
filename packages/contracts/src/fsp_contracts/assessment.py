"""Контракты блока 1 (тест, грейды v2): словарь, DTO стыка и события (blocks.md §4.1, §4.3, §4.4).

Владелец — блок 1. Добавлять можно, ломать нельзя. Payload без ПДн.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class SkillType(StrEnum):
    fundamental = "fundamental"  # фундамент
    hard = "hard"  # хард
    thinking = "thinking"  # инженерное мышление
    business = "business"  # бизнес
    soft = "soft"  # софт
    experience = "experience"  # опыт («учиться»)


class TestGrade(StrEnum):
    """Грейды v2. Значения совпадают с `enums.Grade`, других грейдов v2 не использует."""

    __test__ = False  # не тестовый класс для pytest

    junior = "junior"
    middle = "middle"
    senior = "senior"


TEST_GRADE_ORDER: tuple[TestGrade, ...] = (TestGrade.junior, TestGrade.middle, TestGrade.senior)

# Режим теста: обычный или экспресс для жюри (ADR-025, E32-4a). Экспресс — короче и грубее.
AttemptMode = Literal["standard", "express"]

# Профессия — данные (создаёт админ), не enum. Slug из data/taxonomy/roles.yaml.
ProfessionSlug = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")]


class CategoryRef(BaseModel):
    profession: ProfessionSlug
    grade: TestGrade


class StandingPart(BaseModel):
    """Слагаемое силы профиля (T/F/S/R/C): что даёт больше всего."""

    code: str
    text: str
    value: float = Field(ge=0, le=1)
    weight: float = Field(ge=0)


class StandingGap(BaseModel):
    """Разрыв до следующей «десятки» (топ-30 → топ-20): на сколько п.п. относительной силы."""

    top_percent: int = Field(ge=1, le=90)  # целевая граница: 10, 20, …
    gap_relative: float = Field(ge=0)  # п.п. «от лидера», которых не хватает до границы


class StandingLeader(BaseModel):
    """Лидер категории — анонимно: только грейд и 100 % (никаких идентификаторов)."""

    grade: TestGrade
    relative: float = 100.0


class StandingStrength(BaseModel):
    """Сила профиля и место среди кандидатов той же категории (ранг 1 — сильнейший)."""

    value: float = Field(ge=0, le=1)
    rank: int = Field(ge=1)
    top_percent: int = Field(ge=1, le=100)  # «топ-30 %»: ceil(rank / category_size · 100)
    relative: float = Field(default=100.0, ge=0, le=100)  # сила / сила лидера категории, % (E39-12)
    gap_to_next_ten: StandingGap | None = None  # до ближайшей «десятки» выше; у топ-10 % нет
    parts: list[StandingPart] = Field(default_factory=list)


class StandingPeer(BaseModel):
    """Точка графика «Где ты среди своих»: без идентификаторов, только числа."""

    strength: float = Field(ge=0, le=1)
    salary_min: int | None = None


class CandidateStanding(BaseModel):
    """`GET /candidates/me/standing` (E35-12a). Без действующего грейда все поля пустые."""

    profession: ProfessionSlug | None = None
    grade: TestGrade | None = None
    mode: AttemptMode | None = None
    confirmed_at: datetime | None = None
    strength: StandingStrength | None = None
    leader: StandingLeader | None = None
    category_size: int = 0
    peers: list[StandingPeer] = Field(default_factory=list)  # включая самого кандидата


class CandidateGrade(BaseModel):
    candidate_id: UUID
    profession: ProfessionSlug
    grade: TestGrade
    theta: float
    se: float | None = None
    band_position: float  # T ∈ [0, 1]
    theta_by_type: dict[SkillType, float] = Field(default_factory=dict)
    integrity: float = 1.0
    needs_confirmation: bool = False
    low_confidence: bool = False
    source: Literal["test", "seed"]
    attempt_id: UUID | None = None
    confirmed_at: datetime
    valid_until: datetime
    next_change_at: datetime
    mode: AttemptMode = "standard"  # ADR-025: «экспресс» показывается меткой


class DeclaredGrade(BaseModel):
    """Заявленный в опросе грейд без действующего подтверждения тестом (ADR-025).

    Есть только по профессиям, где у кандидата нет действующей строки `grades`. В выдаче
    показывается с меткой «не подтверждён» и ниже подтверждённых; видимость и согласия — Б2.
    """

    candidate_id: UUID
    profession: ProfessionSlug
    grade: TestGrade
    declared_at: datetime  # дата опроса


class ClaimedVsConfirmed(BaseModel):
    profession: ProfessionSlug
    declared_grade: TestGrade | None = None  # последний опрос
    resume_grade: str | None = None  # из резюме (старая шкала enums.Grade), только «заявлено»
    confirmed_grade: TestGrade | None = None  # из grades
    status: Literal["confirmed", "overclaimed", "underclaimed", "unconfirmed"]


class ProfessionInfo(BaseModel):
    slug: ProfessionSlug
    title: str
    # slug навыка → вес 0..1 («насколько типичен», как в roles.yaml); не нормирован
    skill_weights: dict[str, float]
    skill_types: dict[str, SkillType] = Field(default_factory=dict)  # заполняет E21-1
    active: bool = True  # false — скрыта в опросе и выдаче, данные остаются (ADR-027 п.1)
    # тонкий банк: есть пустая ячейка «грейд × тип навыка», в опросе — метка «бета» (E39-6)
    beta: bool = False


class SkillSuggestion(BaseModel):
    """Подсказка навыка `GET /taxonomy/skills/suggest` (E39-3)."""

    slug: str
    name: str
    group: str | None = None
    provisional: bool = False  # новый навык, ещё не подтверждён (сила доказательства ≤ 0.25)
    matched: str | None = None  # синоним, по которому нашли (если не название)
    score: float = Field(ge=0, le=1)


class ProfessionSuggestion(BaseModel):
    """Подсказка профессии `GET /taxonomy/professions/suggest` (E39-3)."""

    slug: str
    title: str
    score: float = Field(ge=0, le=1)


# --- события (outbox -> exchange events) ---


class AttemptFinished(BaseModel):
    """`assessment.attempt.finished`."""

    candidate_id: UUID
    attempt_id: UUID
    profession: ProfessionSlug
    declared_grade: TestGrade
    stage: Literal["main", "bonus"]
    result: Literal["passed", "failed", "abandoned"]
    grade: TestGrade | None = None  # действующий грейд после попытки
    theta: float
    se: float
    integrity: float
    needs_confirmation: bool
    low_confidence: bool
    finished_at: datetime
    profile_version: int
    mode: AttemptMode = "standard"
    # ADR-025: бонусный этап не повышает, а приглашает на отдельный тест этого грейда
    invited_grade: TestGrade | None = None


class CategoryChanged(BaseModel):
    """`candidate.category.changed`: полный текущий набор категорий, а не дельта."""

    candidate_id: UUID
    categories: list[CategoryRef]
    profile_version: int


class VisibilityChanged(BaseModel):
    """`candidate.visibility.changed` (E36-4, ADR-027): кандидат изменил, что видно работодателю.

    Только ключи и булевы значения, без ПДн. `changed` — изменившиеся ключи,
    `visibility` — полный текущий набор.
    """

    candidate_id: UUID
    changed: dict[str, bool]
    visibility: dict[str, bool]


class FamilyStatusChanged(BaseModel):
    """`assessment.family.status_changed` (внутреннее для блока 1)."""

    model_config = ConfigDict(populate_by_name=True)

    family_id: UUID
    from_: str | None = Field(default=None, alias="from")
    to: str


class RegularTaskPublished(BaseModel):
    """`regular_task.published`: рассылка регулярного задания (E25-1). Без ПДн: только id.

    `recipients` — кандидаты с действующим грейдом ровно `profession × grade` и согласием
    `profile_publication`. `round` растёт с каждой новой рассылкой; повтор публикации в
    пределах периода события не создаёт.
    """

    # `family_id` и `candidate_ids` — прежние имена полей (обработчик уведомлений блока 2, E9-6)
    task_id: UUID = Field(validation_alias=AliasChoices("task_id", "family_id"))
    company_id: UUID | None = None
    profession: ProfessionSlug
    grade: TestGrade | None = None
    round: int = Field(default=1, ge=1)
    period_days: int = 7
    recipients: list[UUID] = Field(
        default_factory=list, validation_alias=AliasChoices("recipients", "candidate_ids")
    )

    @property
    def family_id(self) -> UUID:
        """Совместимость с обработчиком уведомлений блока 2 (E9-6): задание = `task_id`."""
        return self.task_id

    @property
    def candidate_ids(self) -> list[UUID]:
        """Совместимость с обработчиком блока 2: получатели рассылки."""
        return self.recipients

    published_at: datetime | None = None


ASSESSMENT_EVENTS: dict[str, type[BaseModel]] = {
    "assessment.attempt.finished": AttemptFinished,
    "candidate.category.changed": CategoryChanged,
    "candidate.visibility.changed": VisibilityChanged,
    "assessment.family.status_changed": FamilyStatusChanged,
    "regular_task.published": RegularTaskPublished,
}

__all__ = [
    "ASSESSMENT_EVENTS",
    "TEST_GRADE_ORDER",
    "AttemptFinished",
    "AttemptMode",
    "CandidateGrade",
    "CandidateStanding",
    "CategoryChanged",
    "CategoryRef",
    "ClaimedVsConfirmed",
    "DeclaredGrade",
    "FamilyStatusChanged",
    "ProfessionInfo",
    "ProfessionSlug",
    "ProfessionSuggestion",
    "RegularTaskPublished",
    "SkillSuggestion",
    "SkillType",
    "StandingPart",
    "StandingPeer",
    "StandingStrength",
    "TestGrade",
    "VisibilityChanged",
]
