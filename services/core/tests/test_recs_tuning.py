"""Подстройка в сессии (E17-4): формулы Роккио и весов, чипсы, подсказки, симуляция nDCG@10."""

import math
import random

import pytest
from app.recommendations.tuning import (
    FEATURES,
    Signal,
    TuningConfig,
    build,
    chips,
    count_signals,
    hints_of,
    labels_of,
    learn_weights,
    ndcg_at,
    reason_code,
    rocchio,
    tuned_base,
)

CFG = TuningConfig.load()


def test_config_from_scoring_yaml():
    assert CFG.w0["skills"] == 0.45 and CFG.w0["fsp"] == 0.10 and CFG.w0["captain"] == 0.03
    assert CFG.signal_weights == {"open": 1, "dwell": 1, "shortlist": 3, "offer": 5, "dismiss": -3}
    assert (CFG.min_signals, CFG.alpha, CFG.beta) == (3, 0.3, 0.15)
    assert set(CFG.w0) == set(FEATURES)


def test_rocchio_formula_from_docs():
    # q' = norm(q + 0.3·mean(emb⁺) − 0.15·mean(emb⁻))
    q = [1.0, 0.0]
    out = rocchio(q, [[0.0, 1.0], [0.0, 1.0]], [[1.0, 0.0]], CFG)
    raw = [1 - 0.15, 0.3]
    n = math.hypot(*raw)
    assert out == pytest.approx([raw[0] / n, raw[1] / n])
    assert rocchio(q, [], [], CFG) is None
    assert rocchio(None, [[3.0, 4.0]], [], CFG) == pytest.approx([0.6, 0.8])


def test_labels_signal_weights_and_dedup():
    sig = [
        Signal("a", "open"), Signal("a", "open"), Signal("a", "shortlist"),
        Signal("b", "dismiss"), Signal("c", "open"), Signal("c", "dismiss", "дорого"),
        Signal("d", "open"), Signal("d", "dwell"), Signal("x", "unknown"),
    ]  # fmt: skip
    # повтор реакции (повторная доставка) не меняет результат
    assert labels_of(sig, CFG) == {"a": 4, "b": -3, "c": -2, "d": 2}
    assert count_signals(sig, CFG) == 7
    assert labels_of(sig + sig, CFG) == labels_of(sig, CFG)


def test_weights_bounded_and_normalized():
    feats = {
        f"c{i}": {k: (1.0 if (k == "fsp") == (i < 5) else 0.0) for k in FEATURES} for i in range(10)
    }
    labels = {f"c{i}": (30.0 if i < 5 else -30.0) for i in range(10)}
    w = learn_weights(labels, feats, list(labels), CFG)
    assert sum(w.values()) == pytest.approx(sum(CFG.w0.values()), abs=1e-4)
    assert w["fsp"] > CFG.w0["fsp"]
    for k in FEATURES:  # каждый вес в [0.5·w₀, 1.5·w₀]
        assert 0.5 * CFG.w0[k] - 1e-6 <= w[k] <= 1.5 * CFG.w0[k] + 1e-6


def test_no_tuning_below_three_signals():
    t = build([Signal("a", "shortlist"), Signal("b", "dismiss")], {}, CFG)
    assert t.active is False and t.weights == dict(CFG.w0) and t.query is None


def test_chips_on_growth_over_25_percent():
    w = dict(CFG.w0)
    w["fsp"] = CFG.w0["fsp"] * 1.3
    w["captain"] = CFG.w0["captain"] * 1.2
    out = chips(w, CFG)
    assert [c["feature"] for c in out] == ["fsp"]
    assert out[0]["text"] == "Учли: чаще выбираете кандидатов с подтверждением ФСП"


def test_reason_hints():
    assert reason_code("Не тот стек") == "stack"
    assert reason_code("дорого") == "salary"
    assert reason_code("salary") == "salary"
    assert reason_code("просто не нравится") is None
    h = hints_of([
        Signal("a", "dismiss", "дорого"), Signal("b", "dismiss", "не тот стек"),
        Signal("c", "dismiss", "Дорого!"), Signal("a", "dismiss", "дорого"),
    ])  # fmt: skip
    assert [(x["kind"], x["count"]) for x in h] == [("raise_budget", 2), ("make_skill_required", 1)]


# --- симуляция: работодатель со скрытым предпочтением (matching.md §10) ------------------


def _market(seed: int):
    rnd = random.Random(seed)
    feats, embs, rel = {}, {}, {}
    for i in range(80):
        cid = f"c{i:02d}"
        liked = rnd.random() < 0.3  # скрытое предпочтение: капитаны с подтверждением ФСП
        x = {
            "skills": rnd.uniform(0.4, 1.0),
            "semantic": 0.0,  # у вакансии нет вектора
            "grade": rnd.choice([0.5, 1.0]),
            "salary": rnd.uniform(0.0, 1.0),
            "fsp": rnd.uniform(0.6, 1.0) if liked else rnd.uniform(0.0, 0.4),
            "captain": 1.0 if liked or rnd.random() < 0.2 else 0.0,
            "github": float(rnd.random() < 0.5),
            "active": float(rnd.random() < 0.5),
        }
        center = [1.0, 0.2, 0.0, 0.0] if liked else [0.0, 0.2, 1.0, 0.0]
        embs[cid] = [c + rnd.gauss(0, 0.3) for c in center]
        feats[cid] = x
        rel[cid] = 1.0 if liked else 0.0
    return feats, embs, rel


def _rank(feats, embs, t):
    return sorted(feats, key=lambda c: (-tuned_base(feats[c], t, embs[c], CFG), c))


@pytest.mark.parametrize("seed", range(5))
def test_simulation_ndcg_grows_after_five_actions(seed):
    feats, embs, rel = _market(seed)
    t = build([], feats, CFG, embeddings=embs)
    before = ndcg_at(_rank(feats, embs, t), rel)
    signals: list[Signal] = []
    acted: set[str] = set()
    for _ in range(5):  # работодатель реагирует на верхнего ещё не оценённого кандидата
        top = next(c for c in _rank(feats, embs, t) if c not in acted)
        acted.add(top)
        signals.append(Signal(top, "shortlist" if rel[top] else "dismiss"))
        t = build(signals, feats, CFG, embeddings=embs)
    after = ndcg_at(_rank(feats, embs, t), rel)
    assert t.active and len(signals) == 5
    assert after > before


@pytest.mark.parametrize("seed", range(8))
def test_simulation_weights_only_ndcg_grows(seed):
    """Без векторов (Роккио не работает) рост даёт только подстройка весов."""
    feats, embs, rel = _market(seed)
    embs = dict.fromkeys(embs)
    t = build([], feats, CFG, embeddings=embs)
    before = ndcg_at(_rank(feats, embs, t), rel)
    signals: list[Signal] = []
    acted: set[str] = set()
    for _ in range(5):
        top = next(c for c in _rank(feats, embs, t) if c not in acted)
        acted.add(top)
        signals.append(Signal(top, "shortlist" if rel[top] else "dismiss"))
        t = build(signals, feats, CFG, embeddings=embs)
    assert t.query is None
    assert ndcg_at(_rank(feats, embs, t), rel) > before
