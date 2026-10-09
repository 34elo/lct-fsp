"""Командные сигналы L/T/R/G и коэффициент `K_soft` (skills.md §8), без БД.

Сигналы считаются только из проверяемых фактов: результатов ФСП (`fact_type=fsp_result`,
`details`: `level`, `place`, `participants`, `final|stage`, `team_role`, `team_size`,
`teammates` — непрозрачные id напарников) и репозиториев (`source=github`,
`fact_type=code_repo`, `details`: `maintainer`, `external_authors_merged`, `active_authors`).
Заявленные в резюме качества в расчётах не участвуют. Отсутствие сигнала ничего не снижает.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SCORING_PATH = ROOT / "data" / "scoring.yaml"

KINDS = ("leadership", "teamwork", "results", "growth")  # L, T, R, G
DAYS_IN_YEAR = 365.25
HALF_LIFE_YEARS = 3.0  # как у ФСП-доказательств
_GRADE_GROUP = {
    "intern": "intern_junior",
    "junior": "intern_junior",
    "junior_plus": "intern_junior",
    "middle": "middle",
    "middle_plus": "middle",
    "senior": "senior",
    "lead": "lead",
}
STRONG, PRESENT = 0.6, 0.3  # пороги подписи (skills.md §8.5)


@dataclass(frozen=True, slots=True)
class TeamConfig:
    level_k: Mapping[str, float] = field(
        default_factory=lambda: {
            "regional": 0.60,
            "interregional": 0.75,
            "national": 0.90,
            "international": 1.00,
        }
    )
    # (верхняя граница процентиля, k_result); участие — 0.55
    result_k: tuple[tuple[float, float], ...] = ((0.10, 0.90), (0.25, 0.80), (0.50, 0.70))
    participated_k: float = 0.55
    prize_places: int = 3
    captain_base: float = 0.5
    captain_min_result: float = 0.6
    captain_team_size_full: int = 5  # k_size = min(1, (n-1)/(этот-1))
    maintainer_base: float = 0.3
    maintainer_authors_full: int = 10
    team_tau: float = 0.25
    mate_bonus: float = 0.05
    mate_bonus_max_mates: int = 4
    repo_bonus: float = 0.05
    b_cap: float = 0.15
    repo_min_active_authors: int = 2
    results_min_attempts: int = 2
    growth_min_performances: int = 3
    growth_min_seasons: int = 2
    growth_min_value: float = 0.6
    growth_slope_k: float = 2.0
    weights: Mapping[str, Mapping[str, float]] = field(
        default_factory=lambda: {
            "intern_junior": {
                "leadership": 0.01,
                "teamwork": 0.03,
                "results": 0.02,
                "growth": 0.03,
                "beta": 0.06,
            },
            "middle": {
                "leadership": 0.02,
                "teamwork": 0.03,
                "results": 0.02,
                "growth": 0.02,
                "beta": 0.06,
            },
            "senior": {
                "leadership": 0.04,
                "teamwork": 0.03,
                "results": 0.02,
                "growth": 0.01,
                "beta": 0.08,
            },
            "lead": {
                "leadership": 0.08,
                "teamwork": 0.03,
                "results": 0.02,
                "growth": 0.01,
                "beta": 0.12,
            },
        }  # fmt: skip
    )
    emphasis_multiplier: float = 2.0
    emphasis_ceiling_bonus: float = 0.02
    beta_hard_cap: float = 0.12  # skills.md §8.6

    @classmethod
    def load(cls, path: Path | str | None = None) -> TeamConfig:
        data = yaml.safe_load(Path(path or DEFAULT_SCORING_PATH).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Mapping | None) -> TeamConfig:
        if not data or "team_signal_weights" not in data:
            return cls()
        f = data.get("team_signal_formulas", {})
        base = cls()
        weights = {
            g: {
                "leadership": float(w["alpha_leadership"]),
                "teamwork": float(w["alpha_teamwork"]),
                "results": float(w["alpha_results"]),
                "growth": float(w["alpha_growth"]),
                "beta": float(w["beta_ceiling"]),
            }
            for g, w in data["team_signal_weights"].items()
        }
        emph = data.get("employer_emphasis", {})
        fsp = data.get("evidence_sources", {}).get("fsp", {})
        kw: dict[str, Any] = {k: v for k, v in f.items() if k in cls.__dataclass_fields__}
        if "level_coefficients" in fsp:
            kw["level_k"] = {k: float(v) for k, v in fsp["level_coefficients"].items()}
        return cls(
            **kw,
            weights=weights,
            emphasis_multiplier=float(emph.get("multiplier", base.emphasis_multiplier)),
            emphasis_ceiling_bonus=float(emph.get("ceiling_bonus", base.emphasis_ceiling_bonus)),
            beta_hard_cap=float(data.get("team_signal_beta_hard_cap", base.beta_hard_cap)),
        )


@dataclass(frozen=True, slots=True)
class FspPerformance:
    """Выступление на соревновании ФСП (одно на `fact_id`, даже если навыков несколько)."""

    fact_id: uuid.UUID
    observed_at: date
    level: str
    place: int | None = None
    participants: int | None = None
    final: bool = False
    team_role: str = "individual"  # captain | member | individual
    team_size: int = 1
    teammates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RepoFact:
    fact_id: uuid.UUID
    maintainer: bool = False
    external_authors_merged: int = 0
    active_authors: int = 1


@dataclass(frozen=True, slots=True)
class TeamFact:
    """Основание сигнала для UI: без ПДн, только тип и вклад."""

    kind: str  # captain | maintainer | team_competition | performance | trend
    fact_id: str | None
    contribution: float
    level: str | None = None
    place: int | None = None
    year: int | None = None

    def as_json(self) -> dict:
        return {k: v for k, v in {
            "kind": self.kind, "fact_id": self.fact_id, "contribution": self.contribution,
            "level": self.level, "place": self.place, "year": self.year,
        }.items() if v is not None}  # fmt: skip


@dataclass(frozen=True, slots=True)
class TeamSignals:
    values: Mapping[str, float]  # только присутствующие сигналы
    facts: Mapping[str, list[TeamFact]]

    def as_json(self, *, management_confirmed: bool = False) -> dict | None:
        out: dict[str, Any] = {
            k: {"value": v, "facts": [f.as_json() for f in self.facts.get(k, [])]}
            for k, v in self.values.items()
        }
        if management_confirmed:
            out["management_confirmed"] = True
        return out or None


def decay(observed: date, today: date) -> float:
    """Затухание факта по возрасту: период полураспада `HALF_LIFE_YEARS` (skills.md §8.2)."""
    age_years = max(0, (today - observed).days) / DAYS_IN_YEAR
    return 0.5 ** (age_years / HALF_LIFE_YEARS)


def k_level(level: str, cfg: TeamConfig) -> float:
    """Коэффициент уровня соревнования для командных сигналов (skills.md §8.2)."""
    return cfg.level_k.get(level, min(cfg.level_k.values()))


def k_result(place: int | None, participants: int | None, cfg: TeamConfig) -> float:
    """Коэффициент результата команды по месту и числу участников (skills.md §8.2)."""
    if place is None:
        return cfg.participated_k
    if place <= cfg.prize_places:
        return 1.0
    if not participants or participants <= 0:
        return cfg.participated_k
    pct = place / participants
    for bound, k in cfg.result_k:
        if pct <= bound:
            return k
    return cfg.participated_k


def _percentile(p: FspPerformance) -> float | None:
    if p.place is None or not p.participants or p.participants <= 0:
        return None
    return 1.0 - p.place / p.participants


def _is_success(p: FspPerformance, cfg: TeamConfig) -> bool:
    """Успех: финал, призовое место или топ-25%."""
    if p.final or (p.place is not None and p.place <= cfg.prize_places):
        return True
    return bool(p.place and p.participants and p.place / p.participants <= 0.25)


def _noisy_or(xs: Sequence[float]) -> float:
    return 1.0 - math.prod(1.0 - x for x in xs)


def _r2(x: float) -> float:
    return round(x, 4)


def leadership(
    perfs: Sequence[FspPerformance], repos: Sequence[RepoFact], today: date, cfg: TeamConfig
) -> tuple[float, list[TeamFact]]:
    """L — лидерство: капитанство (уровень, результат, размер команды, затухание) и сопровождение
    репозиториев с внешними авторами; noisy-OR (skills.md §8.2).
    """
    parts: list[float] = []
    facts: list[TeamFact] = []
    for p in perfs:
        if p.team_role != "captain":
            continue
        k_size = min(1.0, max(0, p.team_size - 1) / (cfg.captain_team_size_full - 1))
        kr = max(cfg.captain_min_result, k_result(p.place, p.participants, cfg))
        ell = cfg.captain_base * k_level(p.level, cfg) * kr * k_size * decay(p.observed_at, today)
        if ell > 0:
            parts.append(ell)
            facts.append(
                TeamFact("captain", str(p.fact_id), _r2(ell), p.level, p.place, p.observed_at.year)
            )
    for r in repos:
        if not r.maintainer:
            continue
        ell = cfg.maintainer_base * min(
            1.0, r.external_authors_merged / cfg.maintainer_authors_full
        )
        if ell > 0:
            parts.append(ell)
            facts.append(TeamFact("maintainer", str(r.fact_id), _r2(ell)))
    return _noisy_or(parts), facts


def teamwork(
    perfs: Sequence[FspPerformance], repos: Sequence[RepoFact], today: date, cfg: TeamConfig
) -> tuple[float, list[TeamFact]]:
    """T — командная работа: `1 − Π(1 − τ)·(1 − b)` по командным выступлениям, бонус `b` за разных
    напарников и общий репозиторий (skills.md §8.2).
    """
    taus: list[float] = []
    facts: list[TeamFact] = []
    mates: set[str] = set()
    for p in perfs:
        if p.team_role == "individual" or p.team_size < 2:
            continue
        tau = cfg.team_tau * k_level(p.level, cfg) * decay(p.observed_at, today)
        taus.append(tau)
        mates.update(p.teammates)
        facts.append(
            TeamFact(
                "team_competition", str(p.fact_id), _r2(tau), p.level, p.place, p.observed_at.year
            )
        )
    shared = any(r.active_authors >= cfg.repo_min_active_authors for r in repos)
    if not taus and not shared:
        return 0.0, []
    b = cfg.mate_bonus * min(cfg.mate_bonus_max_mates, max(0, len(mates) - 1))
    if shared:
        b += cfg.repo_bonus
    b = min(cfg.b_cap, b)
    value = 1.0 - math.prod(1.0 - t for t in taus) * (1.0 - b)
    return value, facts


def results(perfs: Sequence[FspPerformance], cfg: TeamConfig) -> tuple[float, list[TeamFact]]:
    """R — результативность: сглаженная доля успешных выступлений `(успехи + 1) / (всего + 3)`
    (skills.md §8.2).
    """
    if len(perfs) < cfg.results_min_attempts:
        return 0.0, []
    wins = [p for p in perfs if _is_success(p, cfg)]
    value = (len(wins) + 1) / (len(perfs) + 3)
    facts = [
        TeamFact("performance", str(p.fact_id), 1.0, p.level, p.place, p.observed_at.year)
        for p in wins
    ]
    return value, facts


def growth(perfs: Sequence[FspPerformance], cfg: TeamConfig) -> tuple[float, list[TeamFact]]:
    """G — рост: наклон перцентиля по сезонам, `clip(0.5 + k·slope, 0, 1)` (skills.md §8.2)."""
    pts = [(p.observed_at.year, pc) for p in perfs if (pc := _percentile(p)) is not None]
    if len(pts) < cfg.growth_min_performances or len({x for x, _ in pts}) < cfg.growth_min_seasons:
        return 0.0, []
    n = len(pts)
    mx, my = sum(x for x, _ in pts) / n, sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    slope = sum((x - mx) * (y - my) for x, y in pts) / sxx
    value = min(1.0, max(0.0, 0.5 + cfg.growth_slope_k * slope))
    if value < cfg.growth_min_value:
        return 0.0, []
    first, last = min(pts), max(pts)
    return value, [TeamFact("trend", None, _r2(slope), year=last[0])] if first != last else []


def compute_team_signals(
    perfs: Sequence[FspPerformance],
    repos: Sequence[RepoFact],
    today: date,
    cfg: TeamConfig | None = None,
) -> TeamSignals:
    """Все сигналы L/T/R/G с фактами-основаниями; в подбор идут через `K_soft` (skills.md §8.3)."""
    cfg = cfg or TeamConfig()
    values: dict[str, float] = {}
    facts: dict[str, list[TeamFact]] = {}
    for kind, (v, f) in {
        "leadership": leadership(perfs, repos, today, cfg),
        "teamwork": teamwork(perfs, repos, today, cfg),
        "results": results(perfs, cfg),
        "growth": growth(perfs, cfg),
    }.items():
        if v > 0:
            values[kind] = round(v, 4)
            facts[kind] = f
    return TeamSignals(values, facts)


def strength_label(value: float) -> str | None:
    """`≥0.6` — сильное подтверждение, `0.3–0.6` — есть подтверждение, ниже — не показываем."""
    if value >= STRONG:
        return "strong"
    if value >= PRESENT:
        return "present"
    return None


def k_soft(
    signals: Mapping[str, float],
    vacancy_grade: str,
    cfg: TeamConfig | None = None,
    emphasis: Collection[str] = (),
) -> float:
    """`K_soft = 1 + min(β, Σ α_k·s_k)`; важное для работодателя качество удваивает `α_k`."""
    cfg = cfg or TeamConfig()
    w = cfg.weights[_GRADE_GROUP.get(vacancy_grade, "middle")]
    emph = {k for k in emphasis if k in KINDS}
    total = sum(
        w[k]
        * (cfg.emphasis_multiplier if k in emph else 1.0)
        * min(1.0, max(0.0, signals.get(k, 0.0)))
        for k in KINDS
    )
    beta = w["beta"] + (cfg.emphasis_ceiling_bonus if emph else 0.0)
    return 1.0 + min(min(beta, cfg.beta_hard_cap), total)
