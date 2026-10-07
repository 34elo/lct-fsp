"""Контракты блока 2 (подбор, отклики): события v2. Владелец — блок 2 (blocks.md §5.3)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from fsp_contracts.enums import DeclineReason, OfferStatus

# `offer.*` с полями ADR-022 (`initiator`, необязательная вакансия) — schema_version 2
OFFER_SCHEMA_VERSION = 2
# `offer.interest.*` (ADR-026, E33-1): статусы `interest`, `interest_opened` — schema_version 3
INTEREST_SCHEMA_VERSION = 3


class OfferInitiator(StrEnum):
    """Кто начал взаимодействие (ADR-022): приглашение работодателя или отклик кандидата."""

    employer = "employer"
    candidate = "candidate"


class ContactMethod(StrEnum):
    """Как компания предлагает связаться после принятия приглашения."""

    platform = "platform"  # переписка по офферу на платформе
    email = "email"
    phone = "phone"
    telegram = "telegram"


class SalaryBasis(StrEnum):
    """Вилка до НДФЛ (`gross`, по умолчанию) или на руки (`net`) — E32-5a."""

    gross = "gross"
    net = "net"


class OfferInterestEvent(BaseModel):
    """Все `offer.interest.*` (ADR-026): интерес работодателя до приглашения.

    Строка та же, что у оффера (`offer_id`); после `interest_opened → sent` дальше идут обычные
    `offer.*`. Без ПДн: только id, статусы, причина отказа и вилка (числа).
    """

    offer_id: UUID
    candidate_id: UUID
    company_id: UUID
    vacancy_id: UUID | None = None
    status: OfferStatus
    prev_status: OfferStatus | None = None
    actor: Literal["candidate", "company", "system"] = "system"
    decline_reason: DeclineReason | None = None
    salary_from: int = Field(ge=0)
    salary_to: int = Field(ge=0)


class ActivityKind(StrEnum):
    """Тип события ленты активности работодателя (`GET /employer/activity`, E35-12b)."""

    subscription_hit = "subscription_hit"  # новый кандидат по подписке на категорию
    interest_opened = "interest_opened"  # кандидат открыл интерес
    interest_declined = "interest_declined"  # кандидат отклонил интерес
    invitation_accepted = "invitation_accepted"  # приглашение принято
    invitation_declined = "invitation_declined"  # приглашение отклонено
    task_answered = "task_answered"  # ответ на задание в приглашении


class ActivityCandidate(BaseModel):
    """Анонимная карточка-превью: только псевдоним, без ПДн и контактов."""

    pseudo_id: str
    pseudonym: str
    primary_role: str | None = None
    grade: str | None = None


class ActivityEvent(BaseModel):
    """Событие ленты. `link` — внутренний маршрут веба; `offer_id` — приглашение или интерес."""

    id: str
    kind: ActivityKind
    at: datetime
    candidate: ActivityCandidate
    link: str
    offer_id: UUID | None = None
    subscription_id: UUID | None = None
    detail: str | None = None  # код причины отказа / название подписки (profession)


class ActivityFeed(BaseModel):
    items: list[ActivityEvent]


HIRING_EVENTS: dict[str, type[BaseModel]] = {
    f"offer.interest.{name}": OfferInterestEvent
    for name in ("sent", "opened", "declined", "expired", "withdrawn")
}

__all__ = [
    "ActivityCandidate",
    "ActivityEvent",
    "ActivityFeed",
    "ActivityKind",
    "HIRING_EVENTS",
    "INTEREST_SCHEMA_VERSION",
    "OFFER_SCHEMA_VERSION",
    "ContactMethod",
    "OfferInitiator",
    "OfferInterestEvent",
    "SalaryBasis",
]
