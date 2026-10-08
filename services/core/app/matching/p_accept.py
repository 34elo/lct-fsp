"""p_accept: вероятность принятия оффера кандидатом (matching.md §4.1), логистическая формула.

Коэффициенты и пороги — `data/scoring.yaml`, секция `p_accept`. Без БД: на вход приходят уже
выбранные значения. `p_accept` только подсказывает и сортирует, в жёстких фильтрах не участвует.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SCORING_PATH = ROOT / "data" / "scoring.yaml"


@dataclass(frozen=True, slots=True)
class PAcceptConfig:
    intercept: float = -0.5
    salary_gap: float = 4.0
    format_match: float = 1.0
    stack_interest: float = 1.5
    company_rating: float = 0.5
    active_seeking: float = 0.5
    low: float = 0.35
    high: float = 0.65
    raise_step: float = 0.05  # шаг подсказки «поднимите верх вилки», доля текущего верха
    raise_max_steps: int = 8
    raise_round: int = 5_000
    response_min_sample: int = 3

    @classmethod
    def load(cls, path: Path | None = None) -> PAcceptConfig:
        raw = yaml.safe_load((path or DEFAULT_SCORING_PATH).read_text(encoding="utf-8"))
        sec = raw["p_accept"]
        k, t = sec["coefficients"], sec["thresholds"]
        f = sec.get("forecast", {})
        return cls(
            intercept=k["intercept"], salary_gap=k["salary_gap"], format_match=k["format_match"],
            stack_interest=k["stack_interest"], company_rating=k["company_rating"],
            active_seeking=k["active_seeking"], low=t["low"], high=t["high"],
            raise_step=f.get("raise_step", 0.05), raise_max_steps=f.get("raise_max_steps", 8),
            raise_round=f.get("raise_round", 5_000),
            response_min_sample=f.get("response_min_sample", 3),
        )  # fmt: skip


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def p_accept(
    *,
    salary_to: int,
    salary_min: int | None,
    vacancy_formats: Collection[str],
    candidate_formats: Collection[str],
    vacancy_skills: Collection[str],
    primary_stack: Collection[str],
    responsibility_score: float | None,
    active: bool,
    cfg: PAcceptConfig,
) -> float:
    """σ(b0 + b1·salary_gap + b2·format_match + b3·stack_interest + b4·rating + b5·active)."""
    gap = 0.0
    if salary_min:
        gap = _clamp((salary_to - salary_min) / salary_min, -0.5, 0.5)
    fmt = 1.0 if set(vacancy_formats) & set(candidate_formats) else 0.0
    stack = 0.0
    if primary_stack:
        stack = len(set(primary_stack) & set(vacancy_skills)) / len(set(primary_stack))
    rating = _clamp(((responsibility_score or 3.0) - 3.0) / 2.0, -1.0, 1.0)
    z = (
        cfg.intercept + cfg.salary_gap * gap + cfg.format_match * fmt
        + cfg.stack_interest * stack + cfg.company_rating * rating
        + cfg.active_seeking * (1.0 if active else 0.0)
    )  # fmt: skip
    return 1.0 / (1.0 + math.exp(-z))


def hint(p: float, cfg: PAcceptConfig) -> str:
    """`low` < 0.35 ≤ `medium` ≤ 0.65 < `high`."""
    return "low" if p < cfg.low else "high" if p > cfg.high else "medium"


def suggest_raise(
    salary_to: int, p_now: float, compute: Callable[[int], float], cfg: PAcceptConfig
) -> tuple[int, float] | None:
    """Минимальный верх вилки (шаг `raise_step`, округление `raise_round`), при котором
    `p_accept` достигает порога `high`; если недостижим — порога `low` (уровень «средняя»).
    Уже высокая или ничего не достигается — `None`."""
    if p_now >= cfg.high:
        return None
    steps = []
    for i in range(1, cfg.raise_max_steps + 1):
        to = int(-(-salary_to * (1 + cfg.raise_step * i) // cfg.raise_round) * cfg.raise_round)
        steps.append((to, compute(to)))
    for target in (cfg.high, cfg.low) if p_now < cfg.low else (cfg.high,):
        for to, p in steps:
            if p >= target:
                return to, p
    return None


def mutual(score: float, p: float) -> float:
    """H = 2·score·p / (score + p) — гармоническое среднее (matching.md §4.1)."""
    return 0.0 if score + p <= 0 else 2.0 * score * p / (score + p)
