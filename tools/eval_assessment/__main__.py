"""`python -m tools.eval_assessment` (make eval-assessment): валидация теста на синтетике.

Пишет `<out>/report.json` и `<out>/report.md`. Один и тот же `--seed` даёт тот же отчёт.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import fields
from pathlib import Path
from typing import Any

from .sim import TARGETS, SimConfig, run

ROOT = Path(__file__).resolve().parents[2]

LABELS = {
    "grade_accuracy": "Точность грейда (честные, путь 1)",
    "grade_accuracy_within1": "Грейд ±1",
    "grade_accuracy_outside_indifference": "Точность вне зоны безразличия |θ − cut| ≥ δ",
    "grade_accuracy_margin_05": "Точность при |θ − cut| ≥ 0.5 (фиксированный отступ)",
    "grade_overgrade": "Завышенный грейд (честные, путь 1)",
    "sprt_decision_accuracy": "Точность решения попытки (прошёл ↔ θ ≥ cut)",
    "kappa": "Повторяемость κ (два пути, разные варианты)",
    "mean_items": "Длина основного этапа, заданий",
    "mean_items_with_bonus": "Длина с бонусным этапом",
    "max_share": "Доля дошедших до максимума",
    "theta_r_adaptive": "r(θ̂, θ) адаптивного теста",
    "theta_r_full": "r(θ̂, θ) на полной длине",
    "calib_rmse_30": "RMSE(b̂ − b) после 30 ответов",
    "calib_rmse_100": "RMSE(b̂ − b) после 100 ответов",
    "median_rpb": "Медиана r_pb по семействам (n ≥ 30)",
    "max_exposure": "Максимальная экспозиция семейства",
    "integrity_tpr": "Детектор честности: TPR (списывающие)",
    "integrity_fpr": "Детектор честности: FPR (честные)",
    "cheater_overgrade": "Списывающие с завышенным грейдом",
    "leak_false_upgrade": "Утечка: ложные повышения у «знающих»",
    "leak_baseline_upgrade": "Утечка: завышение у остальных (фон)",
    "leak_excess_upgrade": "Утечка: прирост завышения у «знающих» над фоном",
    "leak_answers_to_quarantine": "Утечка: медиана ответов до карантина",
    "leak_quarantined_share": "Утечка: доля утёкших семейств в карантине",
    "leak_median_answers_after": "Утечка: медиана ответов на семейство после утечки",
    "leak_false_quarantine": "Утечка: карантин неутёкших семейств",
    "quarantined_main": "Карантин в фазе main (семейств)",
    "ai_solvable_share": "Доля семейств, решаемых ИИ (ai_solvable ≥ 0.5)",
}
MARK = {"ok": "✅", "fail": "❌", "n/a": "—"}


def render_md(rep: dict[str, Any]) -> str:
    m, st = rep["metrics"], rep["status"]
    lines = [
        "# Валидация теста на синтетике",
        "",
        f"`make eval-assessment` · seed {rep['seed']} · семейств {rep['bank']['families']} "
        f"(якорей {rep['bank']['anchors']}) · попыток {rep['counts']['attempts_total']}",
        "",
        "| Метрика | Значение | Цель | |",
        "|---|---|---|---|",
    ]
    for key, label in LABELS.items():
        target = TARGETS.get(key)
        t = f"{target[0].replace('>=', '≥').replace('<=', '≤')} {target[1]}" if target else "отчёт"
        lines.append(f"| {label} | {m.get(key)} | {t} | {MARK[st[key]] if key in st else ''} |")
    lines += [
        "",
        "## LLM как кандидат",
        "",
        "| Заявленный грейд | Выданные грейды | Помечен «требует подтверждения» |",
        "|---|---|---|",
    ]
    for g, v in rep["llm"].items():
        lines.append(f"| {g} | {v['granted']} | {v['flagged_share']} |")
    lines += [
        "",
        "LLM симулирована: верный ответ с вероятностью `ai_solvable` семейства, "
        "время ≈ 0.1 медианы. "
        "Прогон настоящей модели — make assessment-llm-bank.",
        "",
        "## Параметры",
        "",
        "```json",
        json.dumps(rep["config"], ensure_ascii=False, indent=1),
        "```",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "eval-assessment")
    for f in fields(SimConfig):
        ap.add_argument(f"--{f.name.replace('_', '-')}", type=type(f.default), default=f.default)
    args = ap.parse_args(argv)
    sc = SimConfig(**{f.name: getattr(args, f.name) for f in fields(SimConfig)})
    rep = run(sc)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
    )
    md = render_md(rep)
    (args.out / "report.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
