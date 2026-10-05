"""Стартовые кодовые семейства каркаса (E22-1): по одному на `exact`, `choice`, `estimate`.

Ключ вычисляется на Python напрямую, код кандидата не исполняется. Полный банк — E22-6.
"""

from __future__ import annotations

from random import Random

from fsp_contracts.assessment import SkillType

from app.assessment.families.base import BaseFamily, Item, Kind
from app.assessment.world import World


class PyLoopSum(BaseFamily):
    """Трассировка: сумма кратных в диапазоне. Ответ — число."""

    slug = "py_loop_sum"
    kind = Kind.exact
    skill = "python"
    skill_type = SkillType.hard
    level = 2

    def generate(self, rng: Random, world: World) -> Item:
        var = world.entities[0][0]
        lo, hi, k = rng.randint(0, 5), rng.randint(10, 30), rng.randint(2, 5)
        code = (
            "total = 0\n"
            f"for {var} in range({lo}, {hi}):\n"
            f"    if {var} % {k} == 0:\n"
            f"        total += {var}\n"
            "print(total)"
        )
        key = sum(i for i in range(lo, hi) if i % k == 0)
        return Item(
            kind=self.kind,
            stem=f"Что выведет код сервиса {world.services[0]} ({world.company})?\n\n{code}",
            key=key,
            time_limit_s=90,
        )


_COMPLEXITY = ["O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n²)"]
_SNIPPETS = [
    ("for x in {t}:\n    if x.id == target:\n        return x", "O(n)"),
    (
        "for a in {t}:\n    for b in {t}:\n        if a.id == b.parent_id:\n            pairs += 1",
        "O(n²)",
    ),
    (
        "lo, hi = 0, len({t})\nwhile lo < hi:\n    mid = (lo + hi) // 2\n    "
        "if {t}[mid].id < target: lo = mid + 1\n    else: hi = mid",
        "O(log n)",
    ),
    ("rows = sorted({t}, key=lambda r: r.created_at)", "O(n log n)"),
    ("first = {t}[0] if {t} else None", "O(1)"),
]


class ComplexityChoice(BaseFamily):
    """Оценка асимптотики фрагмента по n = len(таблицы). Ответ — индекс варианта."""

    slug = "complexity_choice"
    kind = Kind.choice
    skill = "algorithms"
    skill_type = SkillType.fundamental
    level = 2

    def generate(self, rng: Random, world: World) -> Item:
        tmpl, answer = rng.choice(_SNIPPETS)
        table = world.tables[0]
        options = rng.sample(_COMPLEXITY, k=len(_COMPLEXITY))
        return Item(
            kind=self.kind,
            stem=f"Какова временная сложность фрагмента, n = len({table})?\n\n"
            + tmpl.format(t=table),
            options=options,
            key=options.index(answer),
            time_limit_s=60,
        )


class PeakRpsEstimate(BaseFamily):
    """Оценка порядка пикового RPS. Ответ — число."""

    slug = "peak_rps_estimate"
    kind = Kind.estimate
    skill = "estimation"
    skill_type = SkillType.thinking
    level = 3

    def generate(self, rng: Random, world: World) -> Item:
        users = 10**world.scale * rng.choice([1, 2, 3, 5])
        per_user = rng.choice([5, 10, 20, 40])
        peak = rng.choice([2, 3, 5])
        key = users * per_user * peak / 86_400
        users_s = f"{users:_}".replace("_", " ")
        return Item(
            kind=self.kind,
            stem=(
                f"{world.company}: сервисом {world.services[1]} пользуются {users_s} человек в "
                f"сутки, каждый делает около {per_user} запросов. В пик нагрузка в {peak} раза "
                "выше средней. Оцените пиковый RPS (достаточно порядка)."
            ),
            key=key,
            time_limit_s=180,
        )


FAMILIES = [PyLoopSum(), ComplexityChoice(), PeakRpsEstimate()]
