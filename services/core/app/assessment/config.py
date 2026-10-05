"""Параметры теста из `data/scoring.yaml`, раздел `assessment` (assessment.md §5)."""

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

    def prior_b(self, level: int) -> float:
        return self.b_by_level[level]


@lru_cache(maxsize=4)
def load_config(path: str | None = None) -> AssessmentConfig:
    doc = yaml.safe_load(Path(path or DEFAULT_SCORING_PATH).read_text(encoding="utf-8")) or {}
    a = doc["assessment"]
    return AssessmentConfig(
        cuts={g: float(v["cut"]) for g, v in a["grades"].items()},
        b_by_level={int(k): float(v) for k, v in a["b_by_level"].items()},
        min_items=int(a["items"]["min"]),
        max_items=int(a["items"]["max"]),
        simple_pass_share=float(a["simple_pass_share"]),
    )
