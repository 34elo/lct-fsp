"""Психометрия теста — чистые формулы (assessment.md §5, §7).

- Rasch: `P(θ, b) = 1 / (1 + e^-(θ − b))`.
- Частичный балл `y ∈ [0, 1]` входит в правдоподобие дробным исходом:
  `ln L = Σ y·ln P + (1 − y)·ln(1 − P)`.
- θ — EAP на сетке [−4, 4] с шагом 0.1, априорное N(0, 1); SE — СКО апостериорного.
- θ по типам навыков — тот же EAP по ответам одного типа.
- Калибровка после попытки по финальному θ: `b ← b + K·(P(θ, b) − y)`,
  `K = max(0.05, 0.5/√(1 + n))`; у якорей `K = 0` — они держат шкалу.

Без БД и без случайности: всё детерминировано и покрыто юнит-тестами на числах из документа.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from app.assessment.config import AssessmentConfig

_EPS = 1e-12


@dataclass(frozen=True)
class Observation:
    """Оцениваемый ответ: сложность семейства, балл 0..1, тип навыка семейства."""

    b: float
    score: float
    skill_type: str | None = None


@dataclass(frozen=True)
class Estimate:
    theta: float
    se: float
    n: int  # число ответов в оценке


def p_correct(theta: float, b: float) -> float:
    """Rasch: вероятность верного ответа (численно устойчивая сигмоида)."""
    z = theta - b
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def log_likelihood(theta: float, obs: Iterable[Observation]) -> float:
    """ln L(θ) с частичным баллом как дробным исходом."""
    ll = 0.0
    for o in obs:
        p = min(max(p_correct(theta, o.b), _EPS), 1.0 - _EPS)
        y = min(max(o.score, 0.0), 1.0)
        ll += y * math.log(p) + (1.0 - y) * math.log(1.0 - p)
    return ll


def grid(cfg: AssessmentConfig) -> list[float]:
    """Узлы сетки θ: [grid_min, grid_max] с шагом grid_step включительно (81 узел по умолчанию)."""
    steps = round((cfg.grid_max - cfg.grid_min) / cfg.grid_step)
    return [round(cfg.grid_min + i * cfg.grid_step, 10) for i in range(steps + 1)]


def eap(obs: Iterable[Observation], cfg: AssessmentConfig) -> Estimate:
    """EAP θ и SE (СКО апостериорного) на сетке с нормальным априорным."""
    items = list(obs)
    nodes = grid(cfg)
    log_post = [
        -0.5 * ((t - cfg.prior_mean) / cfg.prior_sd) ** 2 + log_likelihood(t, items) for t in nodes
    ]
    m = max(log_post)
    w = [math.exp(lp - m) for lp in log_post]
    total = sum(w)
    mean = sum(t * wi for t, wi in zip(nodes, w, strict=True)) / total
    var = sum((t - mean) ** 2 * wi for t, wi in zip(nodes, w, strict=True)) / total
    return Estimate(theta=mean, se=math.sqrt(var), n=len(items))


def theta_by_type(obs: Iterable[Observation], cfg: AssessmentConfig) -> dict[str, float]:
    """EAP по ответам каждого типа навыка (профиль, объяснения). Тип без ответов — нет ключа."""
    groups: dict[str, list[Observation]] = {}
    for o in obs:
        if o.skill_type:
            groups.setdefault(o.skill_type, []).append(o)
    return {t: eap(g, cfg).theta for t, g in sorted(groups.items())}


def calibration_k(n: int, cfg: AssessmentConfig, *, anchor: bool = False) -> float:
    """Шаг калибровки: `max(k_min, k0/√(1 + n))`, у якоря 0."""
    if anchor:
        return 0.0
    return max(cfg.k_min, cfg.k0 / math.sqrt(1.0 + n))


def calibrate_b(
    b: float, n: int, theta: float, score: float, cfg: AssessmentConfig, *, anchor: bool = False
) -> float:
    """Новая `b` после одного ответа: `b + K·(P(θ, b) − y)` по финальному θ попытки."""
    y = min(max(score, 0.0), 1.0)
    return b + calibration_k(n, cfg, anchor=anchor) * (p_correct(theta, b) - y)
