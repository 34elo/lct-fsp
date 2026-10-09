"""Реестр кодовых семейств (assessment.md §4). Новый модуль семейств — строка в `_MODULES`."""

from __future__ import annotations

from app.assessment.families import (
    ai_engineer,
    behavior,
    code,
    incident_chains,
    reasoning,
    starter,
    world_tasks,
)
from app.assessment.families.base import BaseFamily, Family, Item, Kind

_MODULES = [starter, code, reasoning, behavior, world_tasks, incident_chains, ai_engineer]

REGISTRY: dict[str, Family] = {}


def register(family: Family) -> Family:
    """Регистрирует кодовое семейство; повтор slug или уровень вне 1..5 — ошибка при импорте."""
    if not isinstance(family, Family):
        raise TypeError(f"{family!r} не реализует Family")
    if family.slug in REGISTRY:
        raise ValueError(f"семейство {family.slug} уже зарегистрировано")
    if not 1 <= family.level <= 5:
        raise ValueError(f"{family.slug}: level вне 1..5")
    REGISTRY[family.slug] = family
    return family


def get(slug: str) -> Family | None:
    return REGISTRY.get(slug)


for _m in _MODULES:
    for _f in _m.FAMILIES:
        register(_f)

__all__ = ["REGISTRY", "BaseFamily", "Family", "Item", "Kind", "get", "register"]
