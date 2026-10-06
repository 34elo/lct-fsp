"""Индекс честности прохождения `I` — чистые формулы (assessment.md §8).

`I` начинается с 1 и снижается за сигналы (значения — `scoring.yaml`, `assessment.integrity`):

| Сигнал | Штраф |
|---|---|
| Верный ответ на нелёгком (θ − b < 0.5) быстрее 0.3 × медианы семейства | −0.15 за каждый |
| Уход со вкладки > 10 с, затем верный ответ | −0.15 за каждый, максимум −0.45 |
| Person-fit lz < −2 | −0.2 |
| Совпадение «невозможных» неверных ответов с другими кандидатами | −0.3 |

`I < threshold` (0.6) → «требует подтверждения». Вставки из буфера считаются, но не штрафуются
(в §8 штрафа нет). Без БД и без случайности: покрыто юнит-тестами на числах из документа.

Person-fit `lz` (Drasgow, частичный балл как дробный исход), P = P(θ, b) по финальному θ:
`l₀ = Σ y·ln P + (1 − y)·ln(1 − P)`, `E = Σ P·ln P + (1 − P)·ln(1 − P)`,
`V = Σ P(1 − P)·ln²(P/(1 − P))`, `lz = (l₀ − E)/√V`.

«Нелёгкое» задание определяется по опорному θ — EAP без «быстрых» ответов (быстрее
`fast_ratio` × медианы): иначе списанные верные ответы завышают θ и прячут сами себя.
Person-fit считается по итоговому θ попытки.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.assessment.config import DEFAULT_SCORING_PATH, AssessmentConfig
from app.assessment.psychometrics import Observation, eap, p_correct

_EPS = 1e-9


@dataclass(frozen=True)
class IntegrityConfig:
    correct_min: float = 1.0  # балл, с которого ответ считается верным
    fast_margin: float = 0.5  # нелёгкое задание: θ − b < fast_margin (P < 0.62)
    fast_ratio: float = 0.3  # быстрее fast_ratio × медианы семейства
    fast_penalty: float = 0.15
    away_min_ms: int = 10_000
    away_penalty: float = 0.15
    away_max: float = 0.45
    lz_threshold: float = -2.0
    lz_penalty: float = 0.2
    lz_min_items: int = 6
    copy_penalty: float = 0.3
    copy_min_matches: int = 2  # сколько «невозможных» совпадений дают сигнал
    copy_kinds: tuple[str, ...] = ("exact", "estimate", "find_bug")
    rt_min_n: int = 20  # минимум ответов семейства для медианы и p95
    rt_window: int = 500  # сколько последних ответов семейства берём в статистику
    timer_quantile: float = 0.95
    timer_min_s: int = 15


@lru_cache(maxsize=4)
def load_integrity_config(path: str | None = None) -> IntegrityConfig:
    doc = yaml.safe_load(Path(path or DEFAULT_SCORING_PATH).read_text(encoding="utf-8")) or {}
    a = doc.get("assessment") or {}
    i = a.get("integrity") or {}
    t = a.get("timer") or {}
    d = IntegrityConfig()
    return IntegrityConfig(
        correct_min=float(i.get("correct_min", d.correct_min)),
        fast_margin=float(i.get("fast_margin", d.fast_margin)),
        fast_ratio=float(i.get("fast_ratio", d.fast_ratio)),
        fast_penalty=float(i.get("fast_penalty", d.fast_penalty)),
        away_min_ms=int(i.get("away_min_ms", d.away_min_ms)),
        away_penalty=float(i.get("away_penalty", d.away_penalty)),
        away_max=float(i.get("away_max", d.away_max)),
        lz_threshold=float(i.get("lz_threshold", d.lz_threshold)),
        lz_penalty=float(i.get("lz_penalty", d.lz_penalty)),
        lz_min_items=int(i.get("lz_min_items", d.lz_min_items)),
        copy_penalty=float(i.get("copy_penalty", d.copy_penalty)),
        copy_min_matches=int(i.get("copy_min_matches", d.copy_min_matches)),
        copy_kinds=tuple(i.get("copy_kinds", d.copy_kinds)),
        rt_min_n=int(t.get("min_n", d.rt_min_n)),
        rt_window=int(t.get("window", d.rt_window)),
        timer_quantile=float(t.get("quantile", d.timer_quantile)),
        timer_min_s=int(t.get("min_s", d.timer_min_s)),
    )


@dataclass(frozen=True)
class ItemSignal:
    """Оцениваемый ответ попытки с телеметрией."""

    b: float
    score: float
    rt_ms: int | None = None
    median_ms: float | None = None  # медиана времени семейства; None — данных мало
    away_ms: tuple[int, ...] = ()  # длительности уходов со вкладки во время задания
    pastes: int = 0


@dataclass(frozen=True)
class IntegrityResult:
    index: float
    fast_correct: int
    tab_away: int
    lz: float | None
    copy_matches: int
    pastes: int
    penalties: dict[str, float] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "fast_correct": self.fast_correct,
            "tab_away": self.tab_away,
            "lz": None if self.lz is None else round(self.lz, 4),
            "copy_matches": self.copy_matches,
            "pastes": self.pastes,
            "penalties": self.penalties,
        }


def parse_telemetry(raw: Any) -> tuple[tuple[int, ...], int]:
    """Телеметрия ответа `{"away_ms": [мс, …], "pastes": n}` → (уходы, вставки). Мусор — пусто."""
    if not isinstance(raw, dict):
        return (), 0
    away = raw.get("away_ms")
    away_t = (
        tuple(int(x) for x in away if isinstance(x, int | float) and x >= 0)
        if isinstance(away, list)
        else ()
    )
    pastes = raw.get("pastes")
    return away_t, int(pastes) if isinstance(pastes, int | float) and pastes > 0 else 0


def quantile(values: Sequence[float], q: float) -> float:
    """Квантиль с линейной интерполяцией (как `numpy.quantile` по умолчанию)."""
    xs = sorted(values)
    if not xs:
        raise ValueError("empty")
    pos = (len(xs) - 1) * q
    lo = math.floor(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def time_limit_s(rts_ms: Sequence[int], default_s: int, cfg: IntegrityConfig) -> int:
    """Таймер задания = p95 времени ответа семейства (не меньше `timer_min_s`).

    Ответов меньше `rt_min_n` — таймер по умолчанию из семейства.
    """
    if len(rts_ms) < cfg.rt_min_n:
        return default_s
    return max(cfg.timer_min_s, math.ceil(quantile(rts_ms, cfg.timer_quantile) / 1000))


def person_fit_lz(theta: float, obs: Iterable[tuple[float, float]]) -> float | None:
    """lz по парам (b, y); `None`, если дисперсия нулевая."""
    l0 = e = v = 0.0
    for b, y in obs:
        p = min(max(p_correct(theta, b), _EPS), 1.0 - _EPS)
        y = min(max(y, 0.0), 1.0)
        lp, lq = math.log(p), math.log(1.0 - p)
        l0 += y * lp + (1.0 - y) * lq
        e += p * lp + (1.0 - p) * lq
        v += p * (1.0 - p) * (lp - lq) ** 2
    if v <= 0:
        return None
    return (l0 - e) / math.sqrt(v)


def is_fast(it: ItemSignal, cfg: IntegrityConfig) -> bool:
    """Ответ быстрее `fast_ratio` × медианы семейства (медиана известна)."""
    if it.rt_ms is None or it.median_ms is None:
        return False
    return it.rt_ms < cfg.fast_ratio * it.median_ms


def integrity_index(
    items: Sequence[ItemSignal],
    theta: float,
    copy_matches: int,
    cfg: IntegrityConfig,
    *,
    theta_ref: float | None = None,
) -> IntegrityResult:
    """Индекс `I ∈ [0, 1]` и разбор сигналов по §8.

    `theta` — итоговый θ (person-fit), `theta_ref` — опорный θ для «нелёгкого» задания
    (по умолчанию `theta`).
    """
    ref = theta if theta_ref is None else theta_ref
    correct = [it for it in items if it.score >= cfg.correct_min - _EPS]
    fast = sum(1 for it in correct if ref - it.b < cfg.fast_margin and is_fast(it, cfg))
    away = sum(1 for it in correct if any(a > cfg.away_min_ms for a in it.away_ms))
    lz = person_fit_lz(theta, [(it.b, it.score) for it in items])
    if len(items) < cfg.lz_min_items:
        lz = None
    penalties: dict[str, float] = {}
    if fast:
        penalties["fast_correct"] = round(cfg.fast_penalty * fast, 4)
    if away:
        penalties["tab_away"] = round(min(cfg.away_penalty * away, cfg.away_max), 4)
    if lz is not None and lz < cfg.lz_threshold:
        penalties["person_fit"] = cfg.lz_penalty
    if copy_matches >= cfg.copy_min_matches:
        penalties["copy"] = cfg.copy_penalty
    index = round(min(1.0, max(0.0, 1.0 - sum(penalties.values()))), 4)
    return IntegrityResult(
        index=index,
        fast_correct=fast,
        tab_away=away,
        lz=lz,
        copy_matches=copy_matches,
        pastes=sum(it.pastes for it in items),
        penalties=penalties,
    )


def assess(
    items: Sequence[ItemSignal], copy_matches: int, acfg: AssessmentConfig, cfg: IntegrityConfig
) -> IntegrityResult:
    """θ (EAP по всем ответам) и опорный θ (без «быстрых») → индекс `I`."""
    theta = eap([Observation(b=it.b, score=it.score) for it in items], acfg).theta
    slow = [Observation(b=it.b, score=it.score) for it in items if not is_fast(it, cfg)]
    theta_ref = eap(slow, acfg).theta
    return integrity_index(items, theta, copy_matches, cfg, theta_ref=theta_ref)
