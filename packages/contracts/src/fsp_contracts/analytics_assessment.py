"""Props аналитики блока 1: `survey_*`, `assessment_*`, `family_*`, `regular_task_*`.

Только числа, флаги, перечисления и slug'и (blocks.md §4.7).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Source = Literal["server", "web", "bot"]  # как в analytics.Source (импорт был бы цикличным)


class _Props(BaseModel):
    model_config = ConfigDict(extra="forbid")


ASSESSMENT_ANALYTICS_EVENTS: dict[str, tuple[type[_Props], tuple[Source, ...]]] = {}

__all__ = ["ASSESSMENT_ANALYTICS_EVENTS"]
