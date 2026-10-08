"""Подстройка выдачи под работодателя в сессии (matching.md §7, E17-4).

Чистые детерминированные функции, параметры — `data/scoring.yaml` `session_tuning` и
`matching_weights`. Сигналы сессии (открытие, шорт-лист, «не подходит», оффер) дают:
1. вектор запроса по Роккио `q' = norm(q + α·mean(emb⁺) − β·mean(emb⁻))`;
2. веса признаков — онлайн-логрегрессия с L2 к стартовым весам, каждый вес в
   `[0.5·w₀, 1.5·w₀]`, сумма нормируется к сумме стартовых;
3. подсказки фильтров по причинам «не подходит».
Жёсткие фильтры не меняются: подстройка только переставляет уже подходящих.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.matching.p_accept import DEFAULT_SCORING_PATH
from app.matching.scoring import MatchConfig, cosine

FEATURES = ("skills", "semantic", "grade", "salary", "fsp", "captain", "github", "active")
_MATCH_KEYS = {
    "skills": "skills_coverage",
    "semantic": "semantic_similarity",
    "grade": "grade_fit",
    "salary": "salary_fit",
    "fsp": "fsp_strength",
}

CHIP_TEXT = {
    "skills": "чаще выбираете кандидатов с полным покрытием навыков",
    "semantic": "чаще выбираете кандидатов, близких по описанию",
    "grade": "чаще выбираете кандидатов точно в грейде",
    "salary": "чаще выбираете кандидатов, укладывающихся в вилку",
    "fsp": "чаще выбираете кандидатов с подтверждением ФСП",
    "captain": "чаще выбираете капитанов команд",
    "github": "чаще выбираете кандидатов с кодом на GitHub",
    "active": "чаще выбираете тех, кто активно ищет работу",
}

# причина «не подходит» → подсказка фильтра (код причины или ключевое слово в тексте)
REASON_HINTS = {
    "stack": ("make_skill_required", "Не тот стек — сделать нужный навык обязательным?"),
    "salary": ("raise_budget", "Дорого — поднять вилку, чтобы видеть больше кандидатов?"),
    "grade": ("adjust_grade", "Не тот уровень — уточнить грейд в фильтрах?"),
    "format": ("adjust_format", "Не тот формат — уточнить формат работы?"),
}
_REASON_WORDS = (
    ("stack", re.compile(r"стек|stack|технолог|навык")),
    ("salary", re.compile(r"дорог|зарплат|вилк|salary|budget|expensive")),
    ("grade", re.compile(r"грейд|уров|junior|middle|senior|grade|опыт")),
    ("format", re.compile(r"формат|удал[её]н|офис|гибрид|format|remote|relocat|переезд")),
)


@dataclass(frozen=True, slots=True)
class TuningConfig:
    signal_weights: Mapping[str, float] = field(
        default_factory=lambda: {"open": 1, "dwell": 1, "shortlist": 3, "offer": 5, "dismiss": -3}
    )
    min_signals: int = 3
    session_ttl_hours: int = 24
    alpha: float = 0.3
    beta: float = 0.15
    w0: Mapping[str, float] = field(
        default_factory=lambda: {
            "skills": 0.45,
            "semantic": 0.20,
            "grade": 0.15,
            "salary": 0.10,
            "fsp": 0.10,
            "captain": 0.03,
            "github": 0.03,
            "active": 0.03,
        }  # fmt: skip
    )
    learning_rate: float = 0.1
    l2: float = 1.0
    min_ratio: float = 0.5
    max_ratio: float = 1.5
    chip_min_change: float = 0.25
    semantic_floor: float = 0.30
    semantic_span: float = 0.55

    @classmethod
    def load(cls, path: Path | None = None) -> TuningConfig:
        raw = yaml.safe_load((path or DEFAULT_SCORING_PATH).read_text(encoding="utf-8"))
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> TuningConfig:
        st = raw.get("session_tuning") or {}
        mw = raw.get("matching_weights") or {}
        base = cls()
        mc = MatchConfig.from_dict(raw)
        w0 = {k: float(mw.get(src, base.w0[k])) for k, src in _MATCH_KEYS.items()}
        w0.update({k: float(v) for k, v in (st.get("extra_weights") or {}).items()})
        for k in FEATURES:
            w0.setdefault(k, base.w0[k])
        return cls(
            signal_weights={k: float(v) for k, v in (st.get("signal_weights") or {}).items()}
            or base.signal_weights,
            min_signals=int(st.get("min_signals", base.min_signals)),
            session_ttl_hours=int(st.get("session_ttl_hours", base.session_ttl_hours)),
            alpha=float(st.get("rocchio_alpha", base.alpha)),
            beta=float(st.get("rocchio_beta", base.beta)),
            w0=w0,
            learning_rate=float(st.get("learning_rate", base.learning_rate)),
            l2=float(st.get("l2_to_start", base.l2)),
            min_ratio=float(st.get("weight_min_ratio", base.min_ratio)),
            max_ratio=float(st.get("weight_max_ratio", base.max_ratio)),
            chip_min_change=float(st.get("chip_min_change", base.chip_min_change)),
            semantic_floor=mc.semantic_floor,
            semantic_span=mc.semantic_span,
        )


@dataclass(frozen=True, slots=True)
class Signal:
    """Реакция в сессии: кандидат (ключ), событие, причина."""

    candidate: str
    event: str
    reason: str | None = None


@dataclass(slots=True)
class Tuning:
    """Результат подстройки сессии."""

    signals: int
    active: bool
    weights: dict[str, float]
    labels: dict[str, float]  # кандидат → суммарный вес реакций (без нулевых)
    query: list[float] | None = None  # вектор Роккио; None — не менялся
    hints: list[dict[str, Any]] = field(default_factory=list)


def labels_of(signals: Iterable[Signal], cfg: TuningConfig) -> dict[str, float]:
    """Сумма весов реакций по кандидату; одна и та же реакция на кандидата — один раз."""
    seen: set[tuple[str, str]] = set()
    out: dict[str, float] = {}
    for s in signals:
        if (s.candidate, s.event) in seen or s.event not in cfg.signal_weights:
            continue
        seen.add((s.candidate, s.event))
        out[s.candidate] = out.get(s.candidate, 0.0) + cfg.signal_weights[s.event]
    return {k: v for k, v in out.items() if v != 0}


def count_signals(signals: Iterable[Signal], cfg: TuningConfig) -> int:
    """Число учтённых (уникальных по кандидату и событию) реакций."""
    return len({(s.candidate, s.event) for s in signals if s.event in cfg.signal_weights})


def _norm(v: Sequence[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else list(v)


def _mean(vs: list[Sequence[float]]) -> list[float]:
    return [sum(col) / len(vs) for col in zip(*vs, strict=True)]


def rocchio(
    q: Sequence[float] | None,
    pos: list[Sequence[float]],
    neg: list[Sequence[float]],
    cfg: TuningConfig,
) -> list[float] | None:
    """`q' = norm(q + α·mean(emb⁺) − β·mean(emb⁻))`; нет векторов реакций — None."""
    pos = [list(e) for e in pos if e is not None and len(e)]
    neg = [list(e) for e in neg if e is not None and len(e)]
    if not pos and not neg:
        return None
    dim = len((pos or neg)[0])
    out = list(q) if q is not None and len(q) == dim else [0.0] * dim
    if pos:
        out = [a + cfg.alpha * b for a, b in zip(out, _mean(pos), strict=True)]
    if neg:
        out = [a - cfg.beta * b for a, b in zip(out, _mean(neg), strict=True)]
    return _norm(out)


def _sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def learn_weights(
    labels: Mapping[str, float],
    features: Mapping[str, Mapping[str, float]],
    order: Sequence[str],
    cfg: TuningConfig,
) -> dict[str, float]:
    """Онлайн-логрегрессия: позитив (`label > 0`) против негатива, вес примера — `|label|`.

    Учим относительные множители `m_k = w_k / w₀_k` (так шаг соизмерим для крупных и мелких
    весов). Признаки центрируются средним по показанным в сессии (`features`):
    `m += η·(|y|·(t − σ(w·x̃))·x̃ − λ·(m − 1))`, `m ∈ [0.5, 1.5]`, затем нормировка
    `Σw = Σw₀` с сохранением границ. Порядок примеров — `order` (время первой реакции).
    """
    w0 = dict(cfg.w0)
    if not features:
        return w0
    m = dict.fromkeys(w0, 1.0)
    mu = {k: sum(float(x.get(k, 0.0)) for x in features.values()) / len(features) for k in w0}
    for cand in order:
        y = labels.get(cand)
        x = features.get(cand)
        if not y or x is None:
            continue
        xc = {k: float(x.get(k, 0.0)) - mu[k] for k in w0}
        t = 1.0 if y > 0 else 0.0
        p = _sigmoid(sum(w0[k] * m[k] * xc[k] for k in w0))
        for k in w0:
            g = abs(y) * (t - p) * xc[k] - cfg.l2 * (m[k] - 1.0)
            m[k] = min(cfg.max_ratio, max(cfg.min_ratio, m[k] + cfg.learning_rate * g))
    return _normalize({k: w0[k] * m[k] for k in w0}, w0, cfg)


def _clip(v: float, w0: float, cfg: TuningConfig) -> float:
    return min(cfg.max_ratio * w0, max(cfg.min_ratio * w0, v))


def _normalize(
    w: Mapping[str, float], w0: Mapping[str, float], cfg: TuningConfig
) -> dict[str, float]:
    """Множитель `s`, при котором `Σ clip(s·w_k) = Σ w₀` (бисекция): и сумма, и границы."""
    target = sum(w0.values())
    lo, hi = 0.0, cfg.max_ratio / cfg.min_ratio + 1
    for _ in range(60):
        s = (lo + hi) / 2
        if sum(_clip(s * w[k], w0[k], cfg) for k in w) < target:
            lo = s
        else:
            hi = s
    return {k: round(_clip(hi * w[k], w0[k], cfg), 6) for k in w}


def reason_code(reason: str | None) -> str | None:
    if not reason:
        return None
    r = reason.strip().lower()
    if r in REASON_HINTS:
        return r
    return next((code for code, rx in _REASON_WORDS if rx.search(r)), None)


def hints_of(signals: Iterable[Signal]) -> list[dict[str, Any]]:
    """Подсказки фильтров по причинам «не подходит» (по одной на код, по убыванию частоты)."""
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for s in signals:
        code = reason_code(s.reason) if s.event == "dismiss" else None
        if code is None or s.candidate in seen:
            continue
        seen.add(s.candidate)
        counts[code] = counts.get(code, 0) + 1
    out = []
    for code, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        kind, text = REASON_HINTS[code]
        out.append({"kind": kind, "reason": code, "text": text, "count": n})
    return out


def chips(weights: Mapping[str, float], cfg: TuningConfig) -> list[dict[str, Any]]:
    """Чипсы «Учли: …» — признаки, чей вес вырос больше чем на `chip_min_change`."""
    out = []
    for k in FEATURES:
        w0 = cfg.w0.get(k, 0.0)
        if not w0 or k not in weights:
            continue
        change = weights[k] / w0 - 1
        if change > cfg.chip_min_change:
            out.append({"feature": k, "text": f"Учли: {CHIP_TEXT[k]}", "change": round(change, 4)})
    return sorted(out, key=lambda c: (-c["change"], c["feature"]))


def build(
    signals: Sequence[Signal],
    features: Mapping[str, Mapping[str, float]],
    cfg: TuningConfig,
    *,
    embeddings: Mapping[str, Sequence[float] | None] | None = None,
    query: Sequence[float] | None = None,
) -> Tuning:
    """Подстройка по сигналам сессии (в хронологическом порядке)."""
    n = count_signals(signals, cfg)
    labels = labels_of(signals, cfg)
    active = n >= cfg.min_signals
    if not active:
        return Tuning(n, False, dict(cfg.w0), labels, None, hints_of(signals))
    order = list(dict.fromkeys(s.candidate for s in signals))
    weights = learn_weights(labels, features, order, cfg)
    q = None
    if embeddings:
        pos = [embeddings[c] for c, y in labels.items() if y > 0 and embeddings.get(c) is not None]
        neg = [embeddings[c] for c, y in labels.items() if y < 0 and embeddings.get(c) is not None]
        q = rocchio(query, pos, neg, cfg)  # type: ignore[arg-type]
    return Tuning(n, True, weights, labels, q, hints_of(signals))


def semantic(q: Sequence[float] | None, emb: Sequence[float] | None, cfg: TuningConfig) -> float:
    """`clip((cos(q', emb) − 0.30) / 0.55, 0, 1)`; нет вектора — 0."""
    if q is None or emb is None or not len(q) or not len(emb):
        return 0.0
    return min(1.0, max(0.0, (cosine(q, emb) - cfg.semantic_floor) / cfg.semantic_span))


def tuned_base(
    x: Mapping[str, float], t: Tuning, emb: Sequence[float] | None, cfg: TuningConfig
) -> float:
    """`Σ w'_k·x_k`; при векторе Роккио `semantic` пересчитывается по `q'`."""
    xs = dict(x)
    if t.query is not None:
        xs["semantic"] = semantic(t.query, emb, cfg)
    return sum(t.weights[k] * float(xs.get(k, 0.0)) for k in t.weights)


def ndcg_at(ranked: Sequence[str], rel: Mapping[str, float], k: int = 10) -> float:
    """nDCG@k (для оценки подстройки на симуляции, matching.md §10)."""

    def dcg(gains: Sequence[float]) -> float:
        return sum(g / math.log2(i + 2) for i, g in enumerate(gains[:k]))

    ideal = dcg(sorted(rel.values(), reverse=True))
    return dcg([rel.get(c, 0.0) for c in ranked]) / ideal if ideal else 0.0
