"""Конверт сообщения (messaging.md §2.4)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Envelope(BaseModel):
    message_id: UUID = Field(default_factory=uuid4)
    type: str
    schema_version: int = 1
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str | None = None
    producer: str
    payload: dict[str, Any] = Field(default_factory=dict)


def new_envelope(
    type: str,
    producer: str,
    payload: dict[str, Any] | BaseModel | None = None,
    *,
    correlation_id: str | None = None,
    schema_version: int = 1,
) -> Envelope:
    if isinstance(payload, BaseModel):
        data = payload.model_dump(mode="json")
    else:
        data = payload or {}
    return Envelope(
        type=type,
        producer=producer,
        payload=data,
        correlation_id=correlation_id,
        schema_version=schema_version,
    )
