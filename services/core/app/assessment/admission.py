"""Карточка допуска задания: профессии и грейд семейства, пример варианта с ответом.

Только чтение: ничего не пишет в БД. Пример собирается тем же `generate`, что и в тесте, поэтому
ответ решателя — это ключ, а не текст LLM.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fsp_contracts.assessment import ProfessionInfo

from app.assessment.families.base import Family, Item, Kind

MAX_PROFESSIONS = 3
MAIN_WEIGHT = 0.5  # навык «основной» для профессии, если его вес не ниже


def grade_of_level(level: int) -> str:
    """Уровень семейства 1..5 → грейд ячейки (GRADE_LEVEL: junior 2, middle 3, senior 4)."""
    return "junior" if level <= 2 else "middle" if level == 3 else "senior"


def professions_of(skill: str | None, professions: list[ProfessionInfo]) -> list[ProfessionInfo]:
    """Профессии, для которых навык основной (вес ≥ 0.5), до трёх по весу; иначе одна лучшая."""
    if not skill:
        return []
    ranked = sorted(
        ((p.skill_weights.get(skill, 0.0), p) for p in professions if p.skill_weights.get(skill)),
        key=lambda t: (-t[0], t[1].slug),
    )
    main = [p for w, p in ranked if w >= MAIN_WEIGHT][:MAX_PROFESSIONS]
    return main or [p for _, p in ranked[:1]]


def _option(item: Item, i: Any) -> str:
    opts = item.options or []
    return opts[i] if isinstance(i, int) and 0 <= i < len(opts) else str(i)


def answer_text(item: Item) -> str:
    """Ключ задания человеческим текстом (ответ решателя)."""
    if item.kind == Kind.chain:
        return "; ".join(f"{n}) {answer_text(s)}" for n, s in enumerate(item.steps, 1))
    key = item.key
    if item.kind == Kind.choice:
        return _option(item, key)
    if item.kind == Kind.order and isinstance(key, list):
        return " → ".join(_option(item, i) for i in key)
    if item.kind == Kind.find_bug and isinstance(key, list):
        return "строки " + ", ".join(str(i) for i in key)
    if item.kind == Kind.sjt and isinstance(key, list):
        return " → ".join(_option(item, i) for i in key)
    return str(key)


def example_of(fam: Family | None, slug: str, domain: str | None = None) -> dict[str, Any] | None:
    """Сгенерированный вариант: `{kind, stem, options, answer}`; не получилось собрать — `None`."""
    if fam is None:
        return None
    from app.assessment.attempts import build_item  # поздний импорт: attempts тяжёлый

    seed = int.from_bytes(hashlib.sha256(f"admission:{slug}".encode()).digest()[:8], "big")
    try:
        item = build_item(fam, seed & (2**63 - 1), domain)
        steps = [s.stem for s in item.steps]
        return {
            "kind": item.kind.value,
            "stem": "\n".join([item.stem, *steps]) if steps else item.stem,
            "options": item.options,
            "answer": answer_text(item),
        }
    except Exception:  # noqa: BLE001 - карточка не должна падать из-за одного плохого задания
        return None
