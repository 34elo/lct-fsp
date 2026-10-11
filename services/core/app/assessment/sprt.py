"""Остановка теста — SPRT у порога грейда и бонусный этап. Чистые формулы.

- Гипотезы: θ₀ = cut − δ, θ₁ = cut + δ (δ = 0.7, подобрано на синтетике).
- После каждого оцениваемого ответа: `LLR += y·ln(P₁/P₀) + (1 − y)·ln((1 − P₁)/(1 − P₀))`.
- Границы при α = β = 0.1: `ln((1 − β)/α) = +2.197` → прошёл, `ln(β/(1 − α)) = −2.197` → не прошёл.
- Основной этап: минимум 10, максимум 24 оцениваемых задания. На максимуме (или когда банк
  кончился) решение по EAP θ относительно `cut` с пометкой «низкая уверенность».
- Бонус: прошёл за ≤ 10 заданий и θ ≥ cut_следующего − margin (margin = 0) → до 10 заданий с тем
  же SPRT у порога следующего грейда.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from fsp_contracts.assessment import TEST_GRADE_ORDER, TestGrade

from app.assessment.config import AssessmentConfig
from app.assessment.psychometrics import p_correct

Result = Literal["passed", "failed"]


@dataclass(frozen=True)
class Decision:
    result: Result
    low_confidence: bool  # решение по EAP на максимуме или при исчерпании банка


def hypotheses(cut: float, cfg: AssessmentConfig) -> tuple[float, float]:
    """Гипотезы SPRT у порога: `(θ₀, θ₁) = (cut − δ, cut + δ)`."""
    return cut - cfg.sprt_delta, cut + cfg.sprt_delta


def bounds(cfg: AssessmentConfig) -> tuple[float, float]:
    """(нижняя, верхняя) граница LLR по Вальду: ln(β/(1−α)), ln((1−β)/α)."""
    a, b = cfg.sprt_alpha, cfg.sprt_beta
    return math.log(b / (1.0 - a)), math.log((1.0 - b) / a)


def llr_increment(cut: float, b: float, score: float, cfg: AssessmentConfig) -> float:
    """Вклад одного ответа в LLR; частичный балл — дробный исход, как в EAP."""
    t0, t1 = hypotheses(cut, cfg)
    p0, p1 = p_correct(t0, b), p_correct(t1, b)
    y = min(max(score, 0.0), 1.0)
    return y * math.log(p1 / p0) + (1.0 - y) * math.log((1.0 - p1) / (1.0 - p0))


def decide(
    llr: float,
    n_scored: int,
    *,
    min_items: int,
    max_items: int,
    exhausted: bool,
    theta: float | None,
    cut: float,
    cfg: AssessmentConfig,
) -> Decision | None:
    """Решение этапа или `None` — продолжать.

    `theta` — EAP θ попытки; нужен только на максимуме или при исчерпании банка (`exhausted`).
    """
    lo, hi = bounds(cfg)
    if n_scored >= min_items:
        if llr >= hi:
            return Decision("passed", False)
        if llr <= lo:
            return Decision("failed", False)
    if n_scored >= max_items or exhausted:
        if theta is None:
            raise ValueError("нужен θ для решения на максимуме")
        return Decision("passed" if theta >= cut else "failed", True)
    return None


def next_grade(grade: TestGrade) -> TestGrade | None:
    """Следующий грейд по лестнице теста или `None` для старшего — для бонусного этапа."""
    i = TEST_GRADE_ORDER.index(grade)
    return TEST_GRADE_ORDER[i + 1] if i + 1 < len(TEST_GRADE_ORDER) else None


def bonus_eligible(
    grade: TestGrade, decision: Decision, n_main: int, theta: float, cfg: AssessmentConfig
) -> TestGrade | None:
    """Следующий грейд для бонусного этапа или `None`: прошёл за ≤ 10 и θ ≥ cut_след − margin."""
    nxt = next_grade(grade)
    if not cfg.bonus_enabled:  # экспресс-режим без бонуса
        return None
    if nxt is None or decision.result != "passed" or n_main > cfg.bonus_max_main_items:
        return None
    return nxt if theta >= cfg.cuts[nxt.value] - cfg.bonus_margin else None
