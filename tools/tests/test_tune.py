"""Настройка весов подбора (E36-6): сетка, согласие с `make eval`, правило принятия, отчёт."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("eval_tune", ROOT / "tools/eval/tune.py")
tune = importlib.util.module_from_spec(spec)
sys.modules["eval_tune"] = tune
spec.loader.exec_module(tune)

mt = tune.mt


@pytest.fixture(scope="module")
def market():
    return mt.synth.generate_market(seed=11, n_candidates=150, n_vacancies=30)


def test_grid_sums_and_floor():
    ws = list(tune.grid())
    assert len(ws) == 455  # 16 шагов по 0.05 на 4 компонента, каждый ≥ 1 шага: C(15, 3)
    for w in ws:
        assert sum(w.values()) == pytest.approx(1 - tune.SEMANTIC)
        assert min(w.values()) >= tune.FLOOR - 1e-9
    assert dict(tune.BEFORE.match) in ws


def test_before_weights_reproduce_make_eval(market):
    """Веса «до» в режиме match дают ровно числа `ours` из стенда E27-2."""
    needs = tune.collect(market, required_mult=tune.BEFORE.required_mult, max_needs=10)
    ours = mt.run_matching(market, max_needs=10)["table"]["ours"]
    got = tune.evaluate(needs, tune.BEFORE.match)
    assert got == {"p10": ours["p10"], "ndcg10": ours["ndcg10"]}


def test_strength_needs_test(market):
    no_test = next(c for c in market.candidates if not c["observed"]["tests"])
    assert tune.strength_of(no_test, ["python"], tune.st.StrengthConfig()) is None


def test_search_not_worse_than_before_on_train(market):
    needs = {rq: tune.collect(market, required_mult=rq, max_needs=6) for rq in tune.REQ_GRID}
    best = tune.search(needs)

    def score(w):
        b = tune.both(needs[w.required_mult], w)
        return (b["match"]["ndcg10"] + b["rank"]["ndcg10"]) / 2

    assert score(best) >= score(tune.BEFORE) - 1e-6


def test_improves_requires_all_four():
    before = {"match": {"p10": 0.3, "ndcg10": 0.4}, "rank": {"p10": 0.3, "ndcg10": 0.4}}
    up = {"match": {"p10": 0.31, "ndcg10": 0.41}, "rank": {"p10": 0.31, "ndcg10": 0.41}}
    assert tune.improves(up, before)
    mixed = {**up, "match": {"p10": 0.31, "ndcg10": 0.399}}
    assert not tune.improves(mixed, before)


def test_paired_ci_example():
    mean, ci = tune.paired_ci([1.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 0.0])
    assert mean == 0.5
    assert ci == pytest.approx(round(1.96 * (1 / 3) ** 0.5 / 2, 4))


def test_run_deterministic_and_report(tmp_path):
    r1 = tune.run(120, 15, 4)
    r2 = tune.run(120, 15, 4)
    assert r1 == r2
    assert set(r1["table"]) == {"before", "current", "tuned"}
    assert r1["markets"]["dev"]["seed"] != r1["markets"]["test"]["seed"]
    tune.main(
        ["--candidates", "120", "--vacancies", "15", "--max-needs", "4", "--out", str(tmp_path)]
    )
    data = json.loads((tmp_path / "tune.json").read_text(encoding="utf-8"))
    assert data == json.loads(json.dumps(r1))
    md = (tmp_path / "tune.md").read_text(encoding="utf-8")
    assert "holdout" in md and "BM25" in md
