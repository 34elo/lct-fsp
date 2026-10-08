"""E27-1: валидация теста на синтетике — воспроизводимость и здравый смысл метрик."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from app.assessment.config import load_config

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.eval_assessment import sim  # noqa: E402
from tools.eval_assessment.__main__ import main  # noqa: E402

SMALL = sim.SimConfig(candidates=60, full_candidates=20, leak_candidates=60, llm_runs=2)


@pytest.fixture(scope="module")
def report():
    return sim.run(SMALL)


def test_reproducible(report):
    assert sim.run(SMALL) == report


def test_metrics_sane(report):
    m = report["metrics"]
    assert 0.5 <= m["grade_accuracy"] <= 1
    assert m["grade_accuracy_within1"] >= m["grade_accuracy"]
    assert m["theta_r_adaptive"] > 0.6
    assert load_config().min_items <= m["mean_items"] <= load_config().max_items
    assert 0 < m["max_exposure"] <= 1
    assert set(report["status"]) == set(sim.TARGETS)
    assert set(report["llm"]) == {"junior", "middle", "senior"}


def test_cohen_kappa():
    assert sim.cohen_kappa(["junior", "middle"], ["junior", "middle"]) == 1.0
    # po = 0.5, pe = 0.5 → κ = 0
    assert sim.cohen_kappa(["junior", "middle"], ["junior", "junior"]) == 0.0


def test_true_grade():
    cfg = load_config()
    assert sim.true_grade(-1.5, cfg) == "none"
    assert sim.true_grade(-1.0, cfg) == "junior"
    assert sim.true_grade(0.5, cfg) == "middle"
    assert sim.true_grade(2.0, cfg) == "senior"


def test_cli_writes_report(tmp_path):
    args = ["--out", str(tmp_path), "--candidates", "20", "--full-candidates", "5"]
    args += ["--leak-candidates", "20", "--llm-runs", "1"]
    assert main(args) == 0
    rep = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert rep["seed"] == 42
    assert "Точность грейда" in (tmp_path / "report.md").read_text(encoding="utf-8")
