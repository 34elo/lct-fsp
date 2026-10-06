"""Props аналитики блока 1: `survey_*`, `assessment_*`, `family_*`, `regular_task_*`.

Только числа, флаги, перечисления и slug'и (blocks.md §4.7).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Source = Literal["server", "web", "bot"]  # как в analytics.Source (импорт был бы цикличным)


class _Props(BaseModel):
    model_config = ConfigDict(extra="forbid")


Slug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9.+#_-]{0,63}$")]  # как analytics.Slug
Nat = Annotated[int, Field(ge=0)]
Grade = Literal["junior", "middle", "senior"]
FamilyStatus = Literal["draft", "pilot", "active", "quarantine", "retired"]


class SurveySaved(_Props):
    """Сохранён опрос (только если он изменился). Без отрасли, стека и вилки: флаги и счётчики."""

    profession: Slug
    declared_grade: Grade | None = None
    stack_size: Nat = 0
    formats_count: Nat = 0
    has_salary: bool = False


class AssessmentStarted(_Props):
    attempt_id: Slug
    profession: Slug
    declared_grade: Grade


class AssessmentAnswered(_Props):
    """Ответ принят. Без содержимого ответа: только оценка, время и признак пилота."""

    attempt_id: Slug
    seq: Nat
    stage: Literal["main", "bonus"]
    is_pilot: bool
    score: Annotated[float, Field(ge=0, le=1)]
    rt_ms: Nat | None = None


class AssessmentFinished(_Props):
    attempt_id: Slug
    profession: Slug
    declared_grade: Grade
    stage: Literal["main", "bonus"]
    result: Literal["passed", "failed", "abandoned"]
    grade: Grade | None = None
    items: Nat = 0
    duration_s: Nat | None = None


class FamilyStatusChangedProps(_Props):
    family: Slug
    from_status: FamilyStatus
    to_status: FamilyStatus
    reason: Literal["autocheck", "admin", "alarm", "other"] = "other"


class RegularTaskProps(_Props):
    """Регулярное задание: выдача, ответ, пропуск (E25-1)."""

    task_kind: Slug | None = None
    profession: Slug | None = None
    grade: Grade | None = None
    latency_h: Nat | None = None  # от выдачи до ответа


_S: tuple[Source, ...] = ("server",)
_WB: tuple[Source, ...] = ("web", "bot")

ASSESSMENT_ANALYTICS_EVENTS: dict[str, tuple[type[_Props], tuple[Source, ...]]] = {
    "survey_saved": (SurveySaved, _S),
    "assessment_started": (AssessmentStarted, _S),
    "assessment_answered": (AssessmentAnswered, _S),
    "assessment_finished": (AssessmentFinished, _S),
    "family_status_changed": (FamilyStatusChangedProps, _S),
    "regular_task_sent": (RegularTaskProps, _S),
    "regular_task_answered": (RegularTaskProps, _S + _WB),
    "regular_task_skipped": (RegularTaskProps, _WB + _S),
}

__all__ = ["ASSESSMENT_ANALYTICS_EVENTS"]
