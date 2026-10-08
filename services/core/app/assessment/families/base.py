"""Интерфейс семейства заданий и правила оценки по `kind` (assessment.md §4).

Семейство — генератор вариантов с доказуемым ответом: `generate(rng, world)` даёт `Item` с ключом,
`score(item, answer)` — балл 0..1. Ключ живёт только на сервере: клиент получает `public()`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from random import Random
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

from fsp_contracts.assessment import SkillType

if TYPE_CHECKING:
    from app.assessment.world import World


class Kind(StrEnum):
    exact = "exact"
    estimate = "estimate"
    choice = "choice"
    find_bug = "find_bug"
    order = "order"
    sjt = "sjt"
    chain = "chain"  # цепочка шагов (E26-3): ответ — список ответов шагов, балл — средний
    open = "open"  # только регулярные задания, в θ не идёт


@dataclass(frozen=True)
class Item:
    """Вариант задания. `key` и `meta` на клиент не уходят.

    У `chain` шаги — свои `Item` (без `chain` и `open` внутри), ключ — список ключей шагов.
    """

    kind: Kind
    stem: str
    key: Any
    options: list[str] | None = None
    time_limit_s: int = 120
    meta: dict[str, Any] = field(default_factory=dict)
    steps: tuple[Item, ...] = ()

    def public(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": self.kind.value,
            "stem": self.stem,
            "options": self.options,
            "time_limit_s": self.time_limit_s,
        }
        if self.steps:
            out["steps"] = [s.public() for s in self.steps]
        return out


@runtime_checkable
class Family(Protocol):
    slug: str
    kind: Kind
    skill: str  # slug навыка из taxonomy
    skill_type: SkillType
    level: int  # 1..5

    def generate(self, rng: Random, world: World) -> Item: ...

    def score(self, item: Item, answer: Any) -> float: ...


def _norm(v: Any) -> str:
    return " ".join(str(v).strip().lower().split())


def score_exact(key: Any, answer: Any) -> float:
    """1 при совпадении после нормализации (регистр, пробелы; числа — по значению)."""
    if answer is None:
        return 0.0
    try:
        return 1.0 if math.isclose(float(answer), float(key), rel_tol=1e-9) else 0.0
    except (TypeError, ValueError, OverflowError):  # огромное целое из JSON — не число
        return 1.0 if _norm(answer) == _norm(key) else 0.0


def score_estimate(key: float, answer: Any) -> float:
    """1 — |log₁₀(ответ/истина)| ≤ 0.3; 0.5 — ≤ 0.6; иначе 0."""
    try:
        a = float(answer)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if a <= 0 or key <= 0:
        return 0.0
    d = abs(math.log10(a / key))
    return 1.0 if d <= 0.3 else 0.5 if d <= 0.6 else 0.0


def score_choice(key: int, answer: Any) -> float:
    ok = isinstance(answer, int) and not isinstance(answer, bool) and answer == key
    return 1.0 if ok else 0.0


def score_find_bug(key: list[int], answer: Any) -> float:
    """1 — найдены все строки дефекта; 0.5 — половина и больше; иначе 0. Лишние строки не в плюс."""
    if not isinstance(answer, list) or not key:
        return 0.0
    want = set(key)
    got = {a for a in answer if isinstance(a, int)}
    share = (len(got & want) - len(got - want)) / len(want)  # лишняя строка гасит найденную
    return 1.0 if share >= 1 else 0.5 if share >= 0.5 else 0.0


def score_order(key: list[int], answer: Any) -> float:
    """1 − D / D_max, D = Σ|позиция кандидата − позиция ключа| (`order`, `sjt`)."""
    if not isinstance(answer, list) or not all(
        isinstance(a, int) and not isinstance(a, bool) for a in answer
    ):
        return 0.0  # строки, списки и прочее от клиента — неверный ответ, а не 500
    if sorted(answer) != sorted(key):
        return 0.0
    n = len(key)
    pos = {v: i for i, v in enumerate(key)}
    d = sum(abs(i - pos[v]) for i, v in enumerate(answer))
    d_max = (n * n) // 2
    return 1.0 - d / d_max if d_max else 1.0


def score_chain(steps: tuple[Item, ...], answer: Any) -> float:
    """Средний балл шагов: ответ — список ответов по шагам; неполный список — недостающие 0."""
    if not steps or not isinstance(answer, list) or len(answer) > len(steps):
        return 0.0
    got = [SCORERS[s.kind](s.key, a) for s, a in zip(steps, answer, strict=False)]
    return sum(got) / len(steps)


SCORERS = {
    Kind.exact: score_exact,
    Kind.estimate: score_estimate,
    Kind.choice: score_choice,
    Kind.find_bug: score_find_bug,
    Kind.order: score_order,
    Kind.sjt: score_order,
}


class BaseFamily:
    """Удобная база для кодовых семейств: оценка по `kind` из `SCORERS`."""

    slug: str
    kind: Kind
    skill: str
    skill_type: SkillType
    level: int
    anchor: bool = False  # якорь держит шкалу: K = 0 при калибровке (assessment.md §7)
    # Ручки сложности и их границы для уровня: `generate` кладёт значения в `item.meta["knobs"]`,
    # `make families-check` проверяет, что они в границах (assessment.md §4).
    knob_bounds: ClassVar[dict[str, tuple[float, float]]] = {}

    def generate(self, rng: Random, world: World) -> Item:  # pragma: no cover - абстрактный
        raise NotImplementedError

    def score(self, item: Item, answer: Any) -> float:
        if item.kind == Kind.chain:
            return score_chain(item.steps, answer)
        return SCORERS[item.kind](item.key, answer)
