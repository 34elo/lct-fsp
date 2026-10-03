"""Переранжирование выдачи (matching.md §5): множители и MMR по эмбеддингам.

Чистые функции, параметры — `data/scoring.yaml` (`limits`, `matching_*`). Пол, возраст, фото
и место жительства в признаках отсутствуют.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.matching.p_accept import DEFAULT_SCORING_PATH
from app.matching.scoring import cosine


@dataclass(frozen=True, slots=True)
class RerankConfig:
    top_k: int = 20
    mmr_lambda: float = 0.8
    max_unanswered: int = 3
    overload_penalty: float = 0.9
    max_shown: int = 5
    shown_decay: float = 0.95
    active_boost: float = 1.03
    fresh_boost: float = 1.01
    fresh_days: int = 7

    @classmethod
    def load(cls, path: Path | None = None) -> RerankConfig:
        raw = yaml.safe_load((path or DEFAULT_SCORING_PATH).read_text(encoding="utf-8"))
        lim = raw["limits"]
        return cls(
            top_k=int(lim["matching_reranking_top_k"]),
            mmr_lambda=float(lim["matching_mmr_lambda"]),
            max_unanswered=int(lim["max_unanswered_offers"]),
            overload_penalty=float(lim["matching_overload_penalty"]),
            max_shown=int(lim["max_shown_same_company"]),
            shown_decay=float(lim["shown_count_decay"]),
            active_boost=float(lim["matching_active_boost"]),
            fresh_boost=float(lim["matching_fresh_boost"]),
            fresh_days=int(lim["profile_fresh_days"]),
        )


def multiplier(
    *, unanswered: int, shown: int, active: bool, updated_days: float | None, cfg: RerankConfig
) -> float:
    """Совокупный множитель к скору: нагрузка офферами, застывание выдачи, готовность."""
    m = 1.0
    if unanswered >= cfg.max_unanswered:
        m *= cfg.overload_penalty
    if shown >= cfg.max_shown:
        m *= cfg.shown_decay
    if active:
        m *= cfg.active_boost
    if updated_days is not None and updated_days <= cfg.fresh_days:
        m *= cfg.fresh_boost
    return m


def mmr[T](
    items: Sequence[T],
    rel: Callable[[T], float],
    emb: Callable[[T], Sequence[float] | None],
    cfg: RerankConfig,
) -> list[T]:
    """MMR на первых `top_k` элементах (уже отсортированных по `rel`); хвост не трогаем."""
    head, tail = list(items[: cfg.top_k]), list(items[cfg.top_k :])
    out: list[T] = []
    lam = cfg.mmr_lambda
    while head:

        def gain(x: T) -> float:
            e = emb(x)
            sim = max((cosine(e, o) for s in out if e and (o := emb(s))), default=0.0)
            return lam * rel(x) - (1 - lam) * max(0.0, sim)

        best = max(head, key=gain)  # при равенстве — первый, то есть выше по скору
        head.remove(best)
        out.append(best)
    return out + tail
