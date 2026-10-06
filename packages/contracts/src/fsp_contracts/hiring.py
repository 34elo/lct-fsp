"""Контракты блока 2 (подбор, отклики): события v2. Владелец — блок 2 (blocks.md §5.3)."""

from __future__ import annotations

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


HIRING_EVENTS: dict[str, type[BaseModel]] = {
    f"offer.interest.{name}": OfferInterestEvent
    for name in ("sent", "opened", "declined", "expired", "withdrawn")
}

__all__ = [
    "HIRING_EVENTS",
    "INTEREST_SCHEMA_VERSION",
    "OFFER_SCHEMA_VERSION",
    "ContactMethod",
    "OfferInitiator",
    "OfferInterestEvent",
    "SalaryBasis",
]
