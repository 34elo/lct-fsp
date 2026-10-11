"""Переранжирование: множители и MMR на примерах из документации."""

import pytest
from app.matching.rerank import RerankConfig, mmr, multiplier

CFG = RerankConfig.load()


def test_config_from_scoring_yaml():
    assert (CFG.top_k, CFG.mmr_lambda) == (20, 0.8)
    assert (CFG.max_unanswered, CFG.overload_penalty) == (3, 0.9)
    assert (CFG.max_shown, CFG.shown_decay) == (5, 0.95)
    assert (CFG.active_boost, CFG.fresh_boost, CFG.fresh_days) == (1.03, 1.01, 7)


def m(**kw):
    base = {"unanswered": 0, "shown": 0, "active": False, "updated_days": 30.0, "cfg": CFG}
    return multiplier(**{**base, **kw})


def test_multipliers():
    assert m() == 1.0
    assert m(unanswered=2) == 1.0
    assert m(unanswered=3) == 0.9
    assert m(shown=4) == 1.0
    assert m(shown=5) == 0.95
    assert m(active=True) == 1.03
    assert m(updated_days=7) == 1.01
    assert m(updated_days=8) == 1.0
    assert m(updated_days=None) == 1.0
    assert m(unanswered=3, shown=5, active=True, updated_days=1) == pytest.approx(
        0.9 * 0.95 * 1.03 * 1.01
    )


def test_mmr_demotes_near_duplicate():
    # a и b почти одинаковы; c чуть слабее, но другой. λ=0.8: b(0.85-0.2·1=0.48) < c(0.8·0.8=0.64)
    items = [("a", 0.9, (1, 0)), ("b", 0.85, (1, 0.01)), ("c", 0.8, (0, 1))]
    out = mmr(items, lambda x: x[1], lambda x: x[2], CFG)
    assert [x[0] for x in out] == ["a", "c", "b"]


def test_mmr_without_embeddings_keeps_order():
    items = [("a", 0.9, None), ("b", 0.8, None), ("c", 0.7, None)]
    assert [x[0] for x in mmr(items, lambda x: x[1], lambda x: x[2], CFG)] == ["a", "b", "c"]


def test_mmr_only_top_k():
    cfg = RerankConfig(top_k=2)
    items = [("a", 0.9, (1, 0)), ("b", 0.85, (1, 0)), ("c", 0.8, (0, 1))]
    # c вне топ-2 — остаётся на месте, b не переезжает за него
    assert [x[0] for x in mmr(items, lambda x: x[1], lambda x: x[2], cfg)] == ["a", "b", "c"]
