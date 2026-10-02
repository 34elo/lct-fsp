"""Сила доказательства ФСП (ml.md §3.2), без БД.

`strength = min(0.95, w_rule × k_level × k_result × k_stage)`; коэффициенты — из
`evidence_sources.fsp` в `data/scoring.yaml`. Затухание (3 года) и ×0.5 для неверифицированной
привязки применяет `trust.effective_strength`, здесь их нет.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class FspStrengthConfig:
    max_strength: float = 0.95
    level_k: Mapping[str, float] = field(
        default_factory=lambda: {
            "regional": 0.60,
            "interregional": 0.75,
            "national": 0.90,
            "international": 1.00,
        }
    )
    prize: float = 1.00  # 1-3 место
    top_10: float = 0.90
    top_25: float = 0.80
    top_50: float = 0.70
    participated: float = 0.55
    prize_places: int = 3
    stage_k: Mapping[str, float] = field(default_factory=lambda: {"final": 1.00, "qualifier": 0.85})

    @classmethod
    def from_dict(cls, data: Mapping | None) -> FspStrengthConfig:
        src = ((data or {}).get("evidence_sources") or {}).get("fsp")
        if not src:
            return cls()
        base = cls()
        res = src.get("result_coefficients", {})
        stage = src.get("stage_coefficients", {})
        return cls(
            max_strength=float(src.get("max_strength", base.max_strength)),
            level_k={k: float(v) for k, v in src.get("level_coefficients", base.level_k).items()},
            prize=float(res.get("1_to_3", base.prize)),
            top_10=float(res.get("top_10", base.top_10)),
            top_25=float(res.get("top_25", base.top_25)),
            top_50=float(res.get("top_50", base.top_50)),
            participated=float(res.get("participated", base.participated)),
            stage_k={
                "final": float(stage.get("final", base.stage_k["final"])),
                "qualifier": float(stage.get("qualifying", base.stage_k["qualifier"])),
            },
        )


def k_level(level: str | None, cfg: FspStrengthConfig) -> float:
    return cfg.level_k.get(level or "", min(cfg.level_k.values()))


def k_result(place: int | None, total: int | None, cfg: FspStrengthConfig) -> float:
    if place is None:
        return cfg.participated
    if place <= cfg.prize_places:
        return cfg.prize
    if not total or total <= 0:
        return cfg.participated
    pct = place / total
    for bound, k in ((0.10, cfg.top_10), (0.25, cfg.top_25), (0.50, cfg.top_50)):
        if pct <= bound:
            return k
    return cfg.participated


def k_stage(stage: str, cfg: FspStrengthConfig) -> float:
    return cfg.stage_k.get(stage, cfg.stage_k["qualifier"])


def result_strength(
    weight: float,
    *,
    level: str | None,
    place: int | None,
    total: int | None,
    stage: str,
    cfg: FspStrengthConfig,
) -> float:
    s = weight * k_level(level, cfg) * k_result(place, total, cfg) * k_stage(stage, cfg)
    return round(min(cfg.max_strength, s), 6)
