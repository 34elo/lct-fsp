"""Стенд оценки подбора (E27-2): метрики на примерах, честность входов, воспроизводимость."""

import copy
import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/eval"))
spec = importlib.util.spec_from_file_location("eval_run", ROOT / "tools/eval/run.py")
run_mod = importlib.util.module_from_spec(spec)
sys.modules["eval_run"] = run_mod
spec.loader.exec_module(run_mod)

from bm25 import BM25, tokenize  # noqa: E402
from report import to_markdown, write_report  # noqa: E402
from runners import matching as mt  # noqa: E402


@pytest.fixture(scope="module")
def market():
    return mt.synth.generate_market(seed=11, n_candidates=150, n_vacancies=30)


def test_bm25_prefers_matching_document():
    docs = [tokenize(t) for t in ("python django postgres", "java spring", "python python flask")]
    s = BM25(docs).scores(tokenize("python django"))
    assert s[0] > s[2] > s[1] == 0.0


def test_precision_and_ndcg_examples():
    rel = {"a": 2, "b": 1, "c": 0}
    assert mt.precision_at_k(["a", "x", "b"] + ["y"] * 7, rel) == pytest.approx(0.2)
    ideal = ["a", "b"]
    assert mt.ndcg_at_k(ideal, rel) == pytest.approx(1.0)
    swapped = mt.ndcg_at_k(["b", "a"], rel)
    expected = (1 / math.log2(2) + 2 / math.log2(3)) / (2 / math.log2(2) + 1 / math.log2(3))
    assert swapped == pytest.approx(expected)
    assert mt.ndcg_at_k(["x", "y"], rel) == 0.0
    assert mt.embellished_share(["a", "b", "c", "d"], {"a", "d"}) == pytest.approx(0.5)


def test_evidence_conf_resume_only_is_weak_and_fake_repo_ignored():
    obs = {
        "resume": {"skills": ["python", "go"]},
        "github": [
            {"technologies": ["python"], "authorship_share": 0.8, "fake": True},
            {"technologies": ["go"], "authorship_share": 0.8, "fake": False},
        ],
        "tests": None,
        "fsp": None,
    }
    conf, sources, _ = mt.evidence_conf(obs)
    assert conf["python"] == mt.CLAIM_CONF and sources["python"] == ("resume",)
    assert conf["go"] > conf["python"] and "github" in sources["go"]
    no_gh, _, _ = mt.evidence_conf(obs, github=False)
    assert no_gh["go"] == mt.CLAIM_CONF


def test_views_do_not_use_truth(market):
    c = copy.deepcopy(market.candidates[0])
    a = mt.candidate_view(c)
    del c["truth"]  # подбор видит только observed
    b = mt.candidate_view(c)
    assert a == b


def test_run_deterministic_and_complete(market):
    r1 = mt.run_matching(market, max_needs=10)
    r2 = mt.run_matching(market, max_needs=10)
    assert r1 == r2
    assert set(r1["table"]) == set(mt.METHODS)
    assert r1["needs"] == 10
    for row in r1["table"].values():
        assert 0.0 <= row["p10"] <= 1.0 and 0.0 <= row["ndcg10"] <= 1.0
    assert 0.0 <= r1["category_hit"] <= 1.0


def test_report_written(market, tmp_path):
    result = {"matching": mt.run_matching(market, max_needs=5)}
    meta = market.meta()
    write_report(result, meta, tmp_path)
    data = json.loads((tmp_path / "eval.json").read_text(encoding="utf-8"))
    assert data["matching"]["needs"] == 5 and data["meta"]["seed"] == 11
    md = (tmp_path / "eval.md").read_text(encoding="utf-8")
    assert md == to_markdown(result, meta)
    assert "precision@10" in md and "BM25" in md
