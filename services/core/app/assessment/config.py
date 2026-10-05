"""Параметры теста из `data/scoring.yaml`, раздел `assessment` (assessment.md §5, §7)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

DEFAULT_SCORING_PATH = Path(__file__).resolve().parents[4] / "data" / "scoring.yaml"


@dataclass(frozen=True)
class AssessmentConfig:
    cuts: dict[str, float]
    b_by_level: dict[int, float]
    min_items: int
    max_items: int
    simple_pass_share: float
    # EAP (§5): сетка θ и априорное N(prior_mean, prior_sd²)
    grid_min: float = -4.0
    grid_max: float = 4.0
    grid_step: float = 0.1
    prior_mean: float = 0.0
    prior_sd: float = 1.0
    # Калибровка (§7): K = max(k_min, k0/√(1 + n))
    k0: float = 0.5
    k_min: float = 0.05

    def prior_b(self, level: int) -> float:
        return self.b_by_level[level]


@lru_cache(maxsize=4)
def load_config(path: str | None = None) -> AssessmentConfig:
    doc = yaml.safe_load(Path(path or DEFAULT_SCORING_PATH).read_text(encoding="utf-8")) or {}
    a = doc["assessment"]
    eap = a.get("eap") or {}
    cal = a.get("calibration") or {}
    return AssessmentConfig(
        cuts={g: float(v["cut"]) for g, v in a["grades"].items()},
        b_by_level={int(k): float(v) for k, v in a["b_by_level"].items()},
        min_items=int(a["items"]["min"]),
        max_items=int(a["items"]["max"]),
        simple_pass_share=float(a["simple_pass_share"]),
        grid_min=float(eap.get("grid_min", -4.0)),
        grid_max=float(eap.get("grid_max", 4.0)),
        grid_step=float(eap.get("step", 0.1)),
        prior_mean=float(eap.get("prior_mean", 0.0)),
        prior_sd=float(eap.get("prior_sd", 1.0)),
        k0=float(cal.get("k0", 0.5)),
        k_min=float(cal.get("k_min", 0.05)),
    )
