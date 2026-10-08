"""Потребность → категории (assessment.md §9, E23-4). Чистые функции, без БД.

`affinity(prof) = Σ_s min(w_need(s), w_prof(s)) / Σ_s w_need(s)`; показываем профессии с
affinity ≥ порога, грейд берём из потребности. Параметры — `data/scoring.yaml`, секция `needs`.
"""

from __future__ import annotations

import functools
import statistics
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fsp_contracts.assessment import TEST_GRADE_ORDER
from fsp_contracts.ml import SearchFilters

from app.matching.scoring import DEFAULT_SCORING_PATH

MEDIAN_MIN_SAMPLE = 3  # медиана ожиданий по меньшей группе не показывается
_TEST_GRADE_OF = {
    "intern": "junior", "junior": "junior", "junior_plus": "junior",
    "middle": "middle", "middle_plus": "middle", "senior": "senior", "lead": "senior",
}  # fmt: skip
_GRADE_ORDER = ("intern", "junior", "junior_plus", "middle", "middle_plus", "senior", "lead")


@dataclass(frozen=True, slots=True)
class NeedsConfig:
    affinity_min: float = 0.4
    must_weight: float = 1.0
    nice_weight: float = 0.5
    max_categories: int = 6
    fallback_top: int = 1
    subscription_digest_minutes: int = 60  # дайджест подписки не чаще (E33-4)
    max_subscriptions: int = 20  # подписок на компанию

    @classmethod
    def load(cls, path: Path | str | None = None) -> NeedsConfig:
        return _load(str(path or DEFAULT_SCORING_PATH))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NeedsConfig:
        src = data.get("needs") or {}
        base = cls()
        return cls(
            affinity_min=float(src.get("affinity_min", base.affinity_min)),
            must_weight=float(src.get("must_weight", base.must_weight)),
            nice_weight=float(src.get("nice_weight", base.nice_weight)),
            max_categories=int(src.get("max_categories", base.max_categories)),
            fallback_top=int(src.get("fallback_top", base.fallback_top)),
            subscription_digest_minutes=int(
                src.get("subscription_digest_minutes", base.subscription_digest_minutes)
            ),
            max_subscriptions=int(src.get("max_subscriptions", base.max_subscriptions)),
        )


@functools.lru_cache(maxsize=4)
def _load(path: str) -> NeedsConfig:
    return NeedsConfig.from_dict(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def need_weights(filters: SearchFilters, cfg: NeedsConfig) -> dict[str, float]:
    """Веса навыков потребности: «обязательно» — `must_weight`, «желательно» — `nice_weight`."""
    out: dict[str, float] = {}
    for s in filters.skills_nice or ():
        out[s] = cfg.nice_weight
    for m in filters.skills_must or ():
        out[m.slug] = cfg.must_weight  # обязательное перекрывает «желательно»
    return out


def need_grades(filters: SearchFilters) -> list[str]:
    """Грейды теста из потребности: диапазон `grade_min…grade_max`, без него — все три."""
    if filters.grade_min is None and filters.grade_max is None:
        return [str(g) for g in TEST_GRADE_ORDER]
    lo = _GRADE_ORDER.index(str(filters.grade_min)) if filters.grade_min else 0
    hi = _GRADE_ORDER.index(str(filters.grade_max)) if filters.grade_max else len(_GRADE_ORDER) - 1
    if lo > hi:
        lo, hi = hi, lo
    out: list[str] = []
    for g in _GRADE_ORDER[lo : hi + 1]:
        t = _TEST_GRADE_OF[g]
        if t not in out:
            out.append(t)
    return out


def affinity(need: Mapping[str, float], prof: Mapping[str, float]) -> float:
    total = sum(need.values())
    if total <= 0:
        return 0.0
    return sum(min(w, prof.get(s, 0.0)) for s, w in need.items()) / total


def recommend(
    need: Mapping[str, float],
    professions: Mapping[str, Mapping[str, float]],
    cfg: NeedsConfig,
    roles: Iterable[str] = (),
) -> list[tuple[str, float]]:
    """Профессии по убыванию affinity: с affinity ≥ порога плюс названные в потребности роли.
    Ни одной — берём `fallback_top` лучших с affinity > 0."""
    scored = sorted(
        ((p, round(affinity(need, w), 4)) for p, w in professions.items()),
        key=lambda x: (-x[1], x[0]),
    )
    named = {str(r) for r in roles}
    picked = [(p, a) for p, a in scored if a >= cfg.affinity_min or p in named]
    if not picked:
        picked = [(p, a) for p, a in scored[: cfg.fallback_top] if a > 0]
    return picked[: cfg.max_categories]


def median_salary(values: Iterable[int | None]) -> int | None:
    vals = [v for v in values if v is not None]
    return int(statistics.median(vals)) if len(vals) >= MEDIAN_MIN_SAMPLE else None
