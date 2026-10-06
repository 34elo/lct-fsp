"""Props аналитики блока 2: `need_*`, `category_*`, `invite_*`, `response_*`, `shortlist_*`.

Только числа, флаги, перечисления и slug'и (blocks.md §4.7). Каталог метрик, которые
питаются этими событиями, — metrics.md §9.3. Запись событий — E31-2b.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Source = Literal["server", "web", "bot"]  # как в analytics.Source (импорт был бы цикличным)
Slug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9.+#_-]{0,63}$")]
Nat = Annotated[int, Field(ge=0)]


class _Props(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- потребности и категории ---


class NeedCreated(_Props):
    need_id: UUID
    skills: Nat
    parse_source: Literal["rule", "llm", "cache"] | None = None
    has_vacancy: bool = False
    grade: Slug | None = None


class NeedCategoriesShown(_Props):
    need_id: UUID
    categories: Nat
    latency_ms: Nat | None = None


class CategoryViewed(_Props):
    profession: Slug
    grade: Slug
    candidates: Nat
    need_id: UUID | None = None
    position: Nat | None = None  # место категории в рекомендациях потребности


class CategoryChanged(_Props):
    profession: Slug
    grade: Slug
    grade_from: Slug | None = None
    trigger: Slug | None = None  # attempt / manual / recompute


# --- шорт-лист ---


class ShortlistChanged(_Props):
    need_id: UUID | None = None
    profession: Slug | None = None
    grade: Slug | None = None
    position: Nat | None = None
    size: Nat | None = None  # размер шорт-листа после действия
    reason: Slug | None = None


class ShortlistRefined(_Props):
    need_id: UUID
    features_changed: Nat
    kept: Nat  # сколько кандидатов шорт-листа сохранилось


# --- приглашения (ADR-022) ---


class InviteSent(_Props):
    invite_id: UUID
    with_vacancy: bool
    need_id: UUID | None = None
    p_accept: float | None = None
    below_min: bool | None = None
    time_since_need_s: Nat | None = None  # потребность → приглашение


class InviteAnswered(_Props):
    invite_id: UUID
    decision: Literal["accepted", "declined", "expired"]
    time_to_respond_s: Nat | None = None
    reason: Slug | None = None
    channel: Literal["web", "tg"] | None = None


# --- отклики кандидатов (ADR-022) ---


class ResponseCreated(_Props):
    response_id: UUID
    vacancy_id: UUID
    category_match: bool | None = None  # категория кандидата подходит вакансии


class ResponseAnswered(_Props):
    response_id: UUID
    decision: Literal["accepted", "declined"]
    time_to_answer_s: Nat | None = None
    reason: Slug | None = None


_S: tuple[Source, ...] = ("server",)
_W: tuple[Source, ...] = ("web",)

HIRING_ANALYTICS_EVENTS: dict[str, tuple[type[_Props], tuple[Source, ...]]] = {
    "need_created": (NeedCreated, _S),
    "need_categories_shown": (NeedCategoriesShown, _S),
    "category_viewed": (CategoryViewed, _S),
    "category_changed": (CategoryChanged, _S),
    "shortlist_added": (ShortlistChanged, _S),
    "shortlist_removed": (ShortlistChanged, _S),
    "shortlist_refined": (ShortlistRefined, _S),
    "invite_sent": (InviteSent, _S),
    "invite_answered": (InviteAnswered, _S),
    "response_created": (ResponseCreated, _S),
    "response_answered": (ResponseAnswered, _S),
}

__all__ = ["HIRING_ANALYTICS_EVENTS"]
