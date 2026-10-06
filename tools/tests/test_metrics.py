"""E31-3: сборщик отчёта `make metrics` — светофор, деградация, детерминизм."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.metrics import __main__ as cli  # noqa: E402
from tools.metrics.report import (  # noqa: E402
    GREEN,
    INFO,
    NONE,
    RED,
    YELLOW,
    build_report,
    light,
    render_md,
)

ASSESSMENT = {
    "grade_accuracy_outside_indifference": 0.942,
    "kappa": 0.52,
    "mean_items": 13.1,
    "max_share": 0.105,
    "theta_r_full": 0.87,
    "calib_rmse_30": 0.37,
    "calib_rmse_100": 0.306,
    "median_rpb": 0.41,
    "max_exposure": 0.26,
    "leak_answers_to_quarantine": 80,
    "leak_false_upgrade": 0.24,
    "integrity_fpr": 0.003,
    "integrity_tpr": 0.81,
}
MATCHING = {"lift": {"ndcg10": {"vs_bm25": 0.13}, "p10": {"vs_bm25": 1.0}}, "category_hit": 1.0}


def status(rep: dict, rid: str) -> str:
    return next(r["status"] for r in rep["rows"] if r["id"] == rid)


@pytest.mark.parametrize(
    ("value", "op", "target", "expected"),
    [
        (0.92, ">=", 0.9, GREEN),
        (0.9, ">=", 0.9, GREEN),
        (0.75, ">=", 0.9, YELLOW),
        (0.5, ">=", 0.9, RED),
        (14, "<=", 14, GREEN),
        (16, "<=", 14, YELLOW),
        (30, "<=", 14, RED),
        (0.5, None, None, INFO),
        (None, ">=", 0.9, NONE),
    ],
)
def test_light(value, op, target, expected):
    assert light(value, op, target) == expected


def test_report_lights_and_unmeasured():
    comp = {
        "assessment": {"ok": True, "data": ASSESSMENT},
        "matching": {"ok": True, "data": MATCHING},
        "families": {"ok": True, "data": {"pass_rate": 1.0}},
        "load": {"ok": False, "reason": "нет стенда"},
    }
    rep = build_report(42, comp)
    assert status(rep, "grade_acc_outside") == GREEN
    assert status(rep, "kappa") == INFO  # справочная метрика без цели (ADR-030)
    assert status(rep, "max_share") == YELLOW  # 0.105 против ≤ 0.10
    assert status(rep, "ndcg_lift") == RED  # 13 % против +20 %
    assert status(rep, "families_pass") == GREEN
    assert status(rep, "p95_search") == NONE
    # то, чего нельзя измерить без стенда, никогда не зелёное
    for rid in ("resume_f1", "fairness", "ram_lite", "p95_assessment", "bank_coverage"):
        assert status(rep, rid) == NONE
    assert sum(rep["summary"].values()) == len(rep["rows"])


def test_missing_component_is_unmeasured_not_green():
    rep = build_report(1, {})
    assert {r["status"] for r in rep["rows"]} <= {NONE, INFO}
    assert rep["summary"][GREEN] == rep["summary"][RED] == 0
    assert "не измерено" in render_md(rep)


def test_deterministic_and_pipe_escaped():
    comp = {"assessment": {"ok": True, "data": ASSESSMENT}}
    a, b = build_report(42, comp), build_report(42, comp)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    md = render_md(a)
    assert md == render_md(b)
    assert "|θ − cut|" not in md.replace("\\|θ − cut\\|", "")


def test_collectors_degrade_without_tools(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_run", lambda cmd, cwd=cli.ROOT: (127, "нет такой команды"))
    monkeypatch.setattr(cli, "ROOT", tmp_path)  # нет reports/load
    for name in ("assessment", "matching", "families", "load"):
        c = cli.COLLECTORS[name](42, tmp_path / "parts")
        assert c["ok"] is False
        assert c["reason"]


def test_load_collector_reads_p95(monkeypatch, tmp_path):
    d = tmp_path / "reports" / "load"
    d.mkdir(parents=True)
    (d / "load_stats.csv").write_text(
        "Name,Request Count,Failure Count,95%\nsearch,10,0,640\nmatches,5,0,900\nme,0,0,0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    c = cli.collect_load(42, tmp_path)
    assert c == {"ok": True, "data": {"search": 640.0, "matches": 900.0}}


def test_main_writes_reports_with_all_skipped(tmp_path):
    out = tmp_path / "m"
    assert (
        cli.main(
            [
                "--out",
                str(out),
                "--skip",
                "assessment",
                "--skip",
                "matching",
                "--skip",
                "families",
                "--skip",
                "load",
            ]
        )
        == 0
    )
    rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert rep["summary"]["green"] == 0
    assert (out / "report.md").read_text(encoding="utf-8").startswith("# Офлайн-метрики")
