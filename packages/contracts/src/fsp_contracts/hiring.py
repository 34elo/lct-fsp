"""Контракты блока 2 (подбор, отклики): события v2. Владелец — блок 2 (blocks.md §5.3)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

# `offer.*` с полями ADR-022 (`initiator`, необязательная вакансия) — schema_version 2
OFFER_SCHEMA_VERSION = 2


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


HIRING_EVENTS: dict[str, type[BaseModel]] = {}

__all__ = ["HIRING_EVENTS", "OFFER_SCHEMA_VERSION", "ContactMethod", "OfferInitiator"]
