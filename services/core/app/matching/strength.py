"""Сила профиля внутри категории и итоговый `rank` (assessment.md §9, E23-2). Без БД.

`strength = (0.5·T + 0.2·F + 0.15·S + 0.1·R + 0.05·C) · (I < 0.6 ? 0.8 : 1)`,
`rank = 0.6·match + 0.4·strength`. Веса и пороги — `data/scoring.yaml`, секция `strength`.
Без ФСП слагаемое F равно 0, и никакого дополнительного штрафа нет.
"""

from __future__ import annotations

import functools
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from app.matching.scoring import DEFAULT_SCORING_PATH

TERMS = ("T", "F", "S", "R", "C")
TERM_TEXT = {
    "T": "Уровень внутри грейда",
    "F": "Подтверждение результатами ФСП",
    "S": "Подтверждённые навыки",
    "R": "Свежесть теста",
    "C": "Полнота профиля",
}


@dataclass(frozen=True, slots=True)
class StrengthConfig:
    weights: Mapping[str, float] = field(
        default_factory=lambda: {"T": 0.5, "F": 0.2, "S": 0.15, "R": 0.1, "C": 0.05}
    )
    integrity_threshold: float = 0.6
    integrity_mult: float = 0.8
    recency_days: float = 180.0
    rank_match: float = 0.6
    rank_strength: float = 0.4
    top_explanations: int = 3

    @classmethod
    def load(cls, path: Path | str | None = None) -> StrengthConfig:
        return _load(str(path or DEFAULT_SCORING_PATH))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StrengthConfig:
        src = data.get("strength") or {}
        base = cls()
        return cls(
            weights={k: float(v) for k, v in (src.get("weights") or base.weights).items()},
            integrity_threshold=float(src.get("integrity_threshold", base.integrity_threshold)),
            integrity_mult=float(src.get("integrity_mult", base.integrity_mult)),
            recency_days=float(src.get("recency_days", base.recency_days)),
            rank_match=float(src.get("rank_match", base.rank_match)),
            rank_strength=float(src.get("rank_strength", base.rank_strength)),
            top_explanations=int(src.get("top_explanations", base.top_explanations)),
        )


@functools.lru_cache(maxsize=4)
def _load(path: str) -> StrengthConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return StrengthConfig.from_dict(data)


class StrengthPart(BaseModel):
    code: str  # T | F | S | R | C
    text: str
    value: float  # значение слагаемого ∈ [0, 1]
    weight: float  # вклад в strength (вес × значение)


class StrengthView(BaseModel):
    value: float
    rank: float | None = None  # только когда есть match и категория выбрана
    top: list[StrengthPart] = []


@dataclass(frozen=True, slots=True)
class StrengthInput:
    band_position: float  # T из таблицы grades (θ внутри полосы грейда)
    fsp: float = 0.0  # F; нет ФСП — 0
    skills: float = 0.0  # S
    days_since_test: float | None = None  # для R; нет даты — 0
    completeness: float = 0.0  # C
    integrity: float = 1.0  # I


@dataclass(frozen=True, slots=True)
class StrengthResult:
    value: float
    terms: dict[str, float]
    contributions: dict[str, float]
    integrity_penalty: bool


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def recency(days: float | None, cfg: StrengthConfig) -> float:
    if days is None:
        return 0.0
    return math.exp(-max(0.0, days) / cfg.recency_days)


def band_position(theta: float, cut_lo: float, cut_hi: float) -> float:
    """T = clamp((θ − cut_g) / (cut_{g+1} − cut_g), 0, 1); у Senior ширина полосы 1.0."""
    width = cut_hi - cut_lo
    return _clip((theta - cut_lo) / width) if width > 0 else 0.0


def strength(inp: StrengthInput, cfg: StrengthConfig) -> StrengthResult:
    terms = {
        "T": _clip(inp.band_position),
        "F": _clip(inp.fsp),
        "S": _clip(inp.skills),
        "R": recency(inp.days_since_test, cfg),
        "C": _clip(inp.completeness),
    }
    contrib = {k: cfg.weights.get(k, 0.0) * terms[k] for k in TERMS}
    penalty = inp.integrity < cfg.integrity_threshold
    value = sum(contrib.values()) * (cfg.integrity_mult if penalty else 1.0)
    return StrengthResult(round(_clip(value), 6), terms, contrib, penalty)


def rank(match: float, strength_value: float, cfg: StrengthConfig) -> float:
    return round(cfg.rank_match * match + cfg.rank_strength * strength_value, 6)


def explain(res: StrengthResult, cfg: StrengthConfig) -> list[StrengthPart]:
    """Топ слагаемых с наибольшим вкладом; при равенстве — в порядке T, F, S, R, C."""
    order = sorted(TERMS, key=lambda k: (-res.contributions[k], TERMS.index(k)))
    return [
        StrengthPart(
            code=k, text=TERM_TEXT[k], value=round(res.terms[k], 4),
            weight=round(res.contributions[k], 4),
        )
        for k in order[: cfg.top_explanations]
        if res.contributions[k] > 0
    ]  # fmt: skip


def view(res: StrengthResult, cfg: StrengthConfig, match: float | None = None) -> StrengthView:
    return StrengthView(
        value=res.value,
        rank=None if match is None else rank(match, res.value, cfg),
        top=explain(res, cfg),
    )


COMPLETENESS_FIELDS = (
    "city", "salary_min", "formats", "employment_types", "primary_role",
    "experience_months", "primary_stack", "profile_text",
)  # fmt: skip


def completeness(cand: Any, skills_count: int = 0) -> float:
    """C — доля заполненных полей анкеты (+ есть хотя бы один навык)."""
    filled = sum(1 for f in COMPLETENESS_FIELDS if getattr(cand, f, None) not in (None, "", [], ()))
    filled += 1 if skills_count > 0 else 0
    return filled / (len(COMPLETENESS_FIELDS) + 1)


# --- справедливость (metrics.md §9: «без ФСП / с ФСП» при равном θ) ------------------------


def impact_ratio(items: Iterable[tuple[str, bool]]) -> dict[str, float]:
    """Impact ratio групп: доля группы в выбранных / размер группы, делённая на то же для
    группы с наибольшей долей. `items` — `(группа, попал_в_выбранные)`. Группа без членов
    пропускается; ниже 0.8 — правило четырёх пятых нарушено."""
    total: dict[str, int] = defaultdict(int)
    chosen: dict[str, int] = defaultdict(int)
    for group, sel in items:
        total[group] += 1
        chosen[group] += 1 if sel else 0
    rates = {g: chosen[g] / n for g, n in total.items() if n}
    top = max(rates.values(), default=0.0)
    return {g: (r / top if top else 1.0) for g, r in rates.items()}


def fsp_impact_ratio(
    pool: Sequence[tuple[float, bool, float]], *, top_share: float = 0.3, bins: int = 5
) -> float:
    """Impact ratio «без ФСП / с ФСП» при равном θ. `pool` — `(T, есть_ФСП, strength)`.

    Кандидаты режутся на `bins` полос по T; в каждой берётся топ `top_share` по strength;
    считается доля выбранных в группах, итог — среднее по полосам отношения доли «без ФСП»
    к доле «с ФСП» (полосы, где нет обеих групп или выбрано 0 «с ФСП», пропускаются).
    """
    ratios: list[float] = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        band = [x for x in pool if lo <= x[0] < hi or (b == bins - 1 and x[0] == 1.0)]
        if not band:
            continue
        band.sort(key=lambda x: -x[2])
        k = max(1, round(len(band) * top_share))
        chosen = {id(x) for x in band[:k]}
        no = [x for x in band if not x[1]]
        yes = [x for x in band if x[1]]
        if not no or not yes:
            continue
        r_no = sum(id(x) in chosen for x in no) / len(no)
        r_yes = sum(id(x) in chosen for x in yes) / len(yes)
        if r_yes > 0:
            ratios.append(r_no / r_yes)
    return round(sum(ratios) / len(ratios), 4) if ratios else 1.0
