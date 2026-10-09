"""Сила доказательства ФСП (ml.md §3.2), без БД.

`strength = min(0.95, w_rule × k_level × k_result × k_stage)`; коэффициенты — из
`evidence_sources.fsp` в `data/scoring.yaml`. Затухание (3 года) и ×0.5 для неверифицированной
привязки применяет `trust.effective_strength`, здесь их нет.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date


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
    # слагаемое F силы профиля (assessment.md §9, ADR-025 п. 3): по результативности, без уровней
    f_tier: Mapping[str, float] = field(
        default_factory=lambda: {
            "winner": 1.0,
            "prize": 0.85,
            "finalist": 0.55,
            "participant": 0.25,
            "no_result": 0.05,
        }
    )
    f_finalist_share: float = 0.25  # место в верхней четверти или выход в финал — финалист
    f_diminish: float = 0.5  # каждое следующее соревнование даёт вдвое меньше
    f_decay_floor: float = 0.6  # давность — мягкий множитель: старый результат не ниже 0.6
    f_decay_half_life_years: float = 3.0
    f_unverified: float = 0.5
    # релевантность дисциплины профессии (ADR-027 п. 2): множитель floor + (1 − floor)·rel
    f_relevance_floor: float = 0.4  # нерелевантная дисциплина весит меньше, но не ноль
    f_relevant_threshold: float = 0.5  # rel ≥ порога — «релевантно», иначе «другое направление»

    @classmethod
    def from_dict(cls, data: Mapping | None) -> FspStrengthConfig:
        src = ((data or {}).get("evidence_sources") or {}).get("fsp")
        if not src:
            return cls()
        base = cls()
        res = src.get("result_coefficients", {})
        stage = src.get("stage_coefficients", {})
        f = src.get("f_term", {})
        return cls(
            f_tier={k: float(v) for k, v in f.get("tiers", base.f_tier).items()},
            f_finalist_share=float(f.get("finalist_share", base.f_finalist_share)),
            f_diminish=float(f.get("diminish", base.f_diminish)),
            f_decay_floor=float(f.get("decay_floor", base.f_decay_floor)),
            f_decay_half_life_years=float(
                f.get("decay_half_life_years", base.f_decay_half_life_years)
            ),
            f_unverified=float(f.get("unverified", base.f_unverified)),
            f_relevance_floor=float(f.get("relevance_floor", base.f_relevance_floor)),
            f_relevant_threshold=float(f.get("relevant_threshold", base.f_relevant_threshold)),
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
    """Коэффициент уровня соревнования; неизвестный уровень — минимальный (ml.md §3.2)."""
    return cfg.level_k.get(level or "", min(cfg.level_k.values()))


def k_result(place: int | None, total: int | None, cfg: FspStrengthConfig) -> float:
    """Коэффициент результата: призёр, топ-10/25/50 % по месту среди участников, иначе «участие»
    (ml.md §3.2).
    """
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
    """Коэффициент этапа (финал или отбор); неизвестный — как отбор (ml.md §3.2)."""
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
    """Сила доказательства результата ФСП: `min(0.95, w_rule × k_level × k_result × k_stage)` (ml.md
    §3.2).
    """
    s = weight * k_level(level, cfg) * k_result(place, total, cfg) * k_stage(stage, cfg)
    return round(min(cfg.max_strength, s), 6)


@dataclass(frozen=True, slots=True)
class FspResultIn:
    """Результат участия для слагаемого F: только то, что говорит о результативности."""

    place: int | None
    total: int | None
    final: bool
    observed_at: date
    verified: bool = True
    discipline: str | None = None  # дисциплина и трек — для релевантности профессии
    track: str | None = None
    relevance: float | None = None  # доля дисциплины в профиле профессии; None — неизвестна


def discipline_relevance(
    rules: Iterable[tuple[str, float, str | None]],
    profile: Mapping[str, float],
    track: str | None = None,
) -> float | None:
    """Релевантность дисциплины профессии ∈ [0, 1]: доля веса навыков дисциплины
    (`discipline_rules`, правила без трека и трека результата), входящих в профиль профессии
    с весом > 0. Правил нет — None (множитель не применяется)."""
    w: dict[str, float] = {}
    for slug, weight, rule_track in rules:
        if rule_track in (None, track):
            w[slug] = max(w.get(slug, 0.0), weight)
    total = sum(w.values())
    if total <= 0:
        return None
    return round(sum(v for k, v in w.items() if profile.get(k, 0.0) > 0) / total, 6)


def relevance_multiplier(relevance: float | None, cfg: FspStrengthConfig) -> float:
    """floor + (1 − floor)·rel; релевантность неизвестна — 1 (как до E36-3)."""
    if relevance is None:
        return 1.0
    rel = max(0.0, min(1.0, relevance))
    return cfg.f_relevance_floor + (1 - cfg.f_relevance_floor) * rel


def is_relevant(relevance: float | None, cfg: FspStrengthConfig) -> bool | None:
    """Релевантно ли соревнование профессии (порог `f_relevant_threshold`); `None` — релевантность
    неизвестна.
    """
    return None if relevance is None else relevance >= cfg.f_relevant_threshold


def result_tier(r: FspResultIn, cfg: FspStrengthConfig) -> str:
    """winner | prize | finalist | participant | no_result; уровень соревнования не смотрим."""
    if r.place is None:
        return "finalist" if r.final else "no_result"
    if r.place <= 1:
        return "winner"
    if r.place <= cfg.prize_places:
        return "prize"
    if r.final or (r.total and r.total > 0 and r.place / r.total <= cfg.f_finalist_share):
        return "finalist"
    return "participant"


def fsp_term(results: Iterable[FspResultIn], today: date, cfg: FspStrengthConfig) -> float:
    """F ∈ [0, max_strength]: лучший результат полностью, каждый следующий — с коэффициентом
    `diminish^i` (убывающая отдача). Давность — мягкий множитель в [floor, 1], релевантность
    дисциплины профессии — множитель в [relevance_floor, 1]. Нет результатов — 0, без штрафа."""
    vals: list[float] = []
    for r in results:
        age = max(0.0, (today - r.observed_at).days / 365.25)
        decay = cfg.f_decay_floor + (1 - cfg.f_decay_floor) * 0.5 ** (
            age / cfg.f_decay_half_life_years
        )
        v = (
            cfg.f_tier.get(result_tier(r, cfg), 0.0)
            * decay
            * relevance_multiplier(r.relevance, cfg)
        )
        vals.append(v if r.verified else v * cfg.f_unverified)
    total = sum(v * cfg.f_diminish**i for i, v in enumerate(sorted(vals, reverse=True)))
    return round(min(cfg.max_strength, total), 6)
