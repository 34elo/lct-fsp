"""Контракты блока 2 (подбор, отклики): события v2. Владелец — блок 2 (blocks.md §5.3)."""

from __future__ import annotations

from pydantic import BaseModel

HIRING_EVENTS: dict[str, type[BaseModel]] = {}

__all__ = ["HIRING_EVENTS"]
