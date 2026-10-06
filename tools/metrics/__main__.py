"""`python -m tools.metrics` (make metrics): офлайн-метрики → reports/metrics/report.{json,md}.

Чужие инструменты вызываются как есть (подпроцессами), их отчёты кладутся в `<out>/parts/`.
Недоступный компонент даёт «не измерено», а не падение. Один и тот же `--seed` даёт тот же отчёт.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .report import build_report, render_md

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_S = 900
Comp = dict[str, Any]


def _run(cmd: list[str], cwd: Path = ROOT) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT_S, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, f"{type(e).__name__}: {e}"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _fail(msg: str) -> Comp:
    return {"ok": False, "reason": " ".join(msg.strip().splitlines()[-1:])[:200] or "ошибка"}


def collect_assessment(seed: int, parts: Path) -> Comp:
    out = parts / "eval-assessment"
    rc, log = _run(
        [sys.executable, "-m", "tools.eval_assessment", "--seed", str(seed), "--out", str(out)]
    )
    f = out / "report.json"
    if rc != 0 or not f.exists():
        return _fail(f"eval-assessment: код {rc}; {log}")
    return {"ok": True, "data": json.loads(f.read_text(encoding="utf-8"))["metrics"]}


def collect_matching(seed: int, parts: Path) -> Comp:
    out = parts / "eval"
    rc, log = _run([sys.executable, "tools/eval/run.py", "--split", "test", "--out", str(out)])
    f = out / "eval.json"
    if rc != 0 or not f.exists():
        return _fail(f"eval: код {rc}; {log}")
    return {"ok": True, "data": json.loads(f.read_text(encoding="utf-8"))["matching"]}


def collect_families(seed: int, parts: Path) -> Comp:
    rc, log = _run(
        ["uv", "run", "python", "-m", "app.assessment.families.check", "--seeds", "1000"],
        cwd=ROOT / "services" / "core",
    )
    m = re.search(r"families-check: семейств (\d+)", log)
    if not m:
        return _fail(f"families-check: код {rc}; {log}")
    total = int(m.group(1))
    # Каждая ошибка начинается с «FAIL »; доля семейств без ошибок оценивается снизу по их числу
    fails = len(re.findall(r"^FAIL ", log, flags=re.M))
    rate = 1.0 if rc == 0 else max(0.0, round(1 - fails / max(total, 1), 4))
    return {"ok": True, "data": {"families": total, "pass_rate": rate}}


def collect_load(seed: int, parts: Path) -> Comp:
    f = ROOT / "reports" / "load" / "load_stats.csv"
    if not f.exists():
        return {
            "ok": False,
            "reason": "нет reports/load/load_stats.csv (нужен `make up`, `make seed`, `make load`)",
        }
    with f.open(encoding="utf-8", newline="") as fh:
        rows = {r["Name"]: r for r in csv.DictReader(fh)}
    data: dict[str, float] = {}
    for name in ("search", "matches"):
        r = rows.get(name)
        if r and int(r["Request Count"]) > 0:
            data[name] = float(r["95%"])
    if not data:
        return {"ok": False, "reason": "в load_stats.csv нет строк search/matches"}
    return {"ok": True, "data": data}


COLLECTORS: dict[str, Callable[[int, Path], Comp]] = {
    "assessment": collect_assessment,
    "matching": collect_matching,
    "families": collect_families,
    "load": collect_load,
}


def run(seed: int, out: Path, skip: set[str]) -> dict[str, Any]:
    parts = out / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    comp: dict[str, Comp] = {}
    for name, fn in COLLECTORS.items():
        comp[name] = (
            {"ok": False, "reason": "пропущен (--skip)"} if name in skip else fn(seed, parts)
        )
        print(
            f"[metrics] {name}: {'ok' if comp[name]['ok'] else comp[name]['reason']}",
            file=sys.stderr,
        )
    return build_report(seed, comp)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "metrics")
    ap.add_argument("--skip", action="append", default=[], choices=sorted(COLLECTORS))
    a = ap.parse_args(argv)
    rep = run(a.seed, a.out, set(a.skip))
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "report.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    md = render_md(rep)
    (a.out / "report.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
