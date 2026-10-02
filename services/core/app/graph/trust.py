"""Доверие к навыкам: чистые формулы (ml.md §3.1, §3.3), без БД.

Параметры берутся из `data/scoring.yaml` (`TrustConfig.load`); формулы силы по источникам
(GitHub, тест, ФСП…) считают писатели evidence, здесь — только затухание и объединение.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SCORING_PATH = ROOT / "data" / "scoring.yaml"
CLAIMED_SOURCES = frozenset({"self", "resume"})
DAYS_IN_YEAR = 365.25
UNVERIFIED_FSP_FACTOR = 0.5  # ml.md §3.1: неверифицированная привязка ФСП


@dataclass(frozen=True, slots=True)
class TrustConfig:
    half_life_years: Mapping[str, float | None]
    level_min: tuple[float, ...]  # нижние границы уровней 0..4
    provisional_cap: float
    test_validity_months: int | None

    @classmethod
    def load(cls, path: Path | str | None = None) -> TrustConfig:
        data = yaml.safe_load(Path(path or DEFAULT_SCORING_PATH).read_text(encoding="utf-8"))
        levels = data["trust_levels"]
        sources = data["evidence_sources"]
        return cls(
            half_life_years={k: v.get("decay_half_life_years") for k, v in sources.items()},
            level_min=tuple(float(levels[i]["min"]) for i in range(5)),
            provisional_cap=float(data["provisional_skill_max_strength"]),
            test_validity_months=sources["test"].get("validity_months"),
        )


@dataclass(frozen=True, slots=True)
class EvidenceView:
    """Доказательство, как его видит пересчёт."""

    id: uuid.UUID
    source: str
    strength: float
    observed_at: date
    verified: bool = True


@dataclass(frozen=True, slots=True)
class SkillTrust:
    confidence: float
    level: int
    sources: list[str]
    top_evidence: list[uuid.UUID]
    claimed_only: bool


def effective_strength(
    ev: EvidenceView, today: date, cfg: TrustConfig, *, provisional: bool = False
) -> float:
    """`s_eff = s · 0.5^(age/half_life)`; 0 — если доказательство уже не действует."""
    age_days = max(0, (today - ev.observed_at).days)
    s = ev.strength
    if ev.source == "fsp" and not ev.verified:
        s *= UNVERIFIED_FSP_FACTOR
    if ev.source == "test" and cfg.test_validity_months:
        if age_days > cfg.test_validity_months * DAYS_IN_YEAR / 12:
            return 0.0
    half_life = cfg.half_life_years.get(ev.source)
    if half_life:
        s *= 0.5 ** (age_days / DAYS_IN_YEAR / half_life)
    if provisional:
        s = min(s, cfg.provisional_cap)
    return s


def level_for(confidence: float, cfg: TrustConfig) -> int:
    return max(i for i, lo in enumerate(cfg.level_min) if confidence >= lo)


def combine(
    evidence: Iterable[EvidenceView],
    today: date,
    cfg: TrustConfig,
    *,
    provisional: bool = False,
) -> SkillTrust | None:
    """Максимум внутри источника, noisy-OR между источниками (ml.md §3.3).

    None — если не осталось ни одного действующего доказательства.
    """
    best: dict[str, tuple[float, EvidenceView]] = {}
    for ev in evidence:
        s = effective_strength(ev, today, cfg, provisional=provisional)
        if s <= 0:
            continue
        cur = best.get(ev.source)
        if cur is None or s > cur[0]:
            best[ev.source] = (s, ev)
    if not best:
        return None
    confidence = round(1 - math.prod(1 - s for s, _ in best.values()), 6)
    ranked = sorted(best.items(), key=lambda kv: (-kv[1][0], kv[0]))
    return SkillTrust(
        confidence=confidence,
        level=level_for(confidence, cfg),
        sources=sorted(best),
        top_evidence=[ev.id for _, (_, ev) in ranked[:3]],
        claimed_only=set(best) <= CLAIMED_SOURCES,
    )


MAX_INHERIT_LEVELS = 2  # graph.md §5.1: наследуем вверх не больше двух уровней


def inherit(
    direct: Mapping[uuid.UUID, SkillTrust],
    parents_of: Callable[[uuid.UUID], Iterable[tuple[uuid.UUID, float]]],
    cfg: TrustConfig,
) -> dict[uuid.UUID, tuple[SkillTrust, uuid.UUID]]:
    """Наследование по иерархии (graph.md §5.1).

    Родитель получает `max(child_conf × coef(child→parent))`, если это выше его собственного
    доверия. Возвращает {родитель: (доверие, непосредственный дочерний навык-источник)}.
    """
    derived: dict[uuid.UUID, tuple[SkillTrust, uuid.UUID]] = {}
    frontier = dict(direct)
    for _ in range(MAX_INHERIT_LEVELS):
        nxt: dict[uuid.UUID, SkillTrust] = {}
        for child in sorted(frontier, key=str):
            src = frontier[child]
            for parent, coef in parents_of(child):
                val = round(src.confidence * coef, 6)
                own = direct.get(parent)
                cur = derived.get(parent)
                if val <= max(own.confidence if own else 0.0, cur[0].confidence if cur else 0.0):
                    continue
                t = SkillTrust(
                    val, level_for(val, cfg), src.sources, src.top_evidence, src.claimed_only
                )
                derived[parent] = (t, child)
                nxt[parent] = t
        frontier = nxt
    return derived
