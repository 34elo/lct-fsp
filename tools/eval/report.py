"""Отчёт стенда оценки: markdown + JSON в `reports/eval/` (evaluation.md §5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LABELS = {
    "bm25": "BM25 по резюме (база)",
    "bm25_filtered": "BM25 + фильтры грейда и зарплаты",
    "ours": "Наш подбор",
    "ours_no_github": "Наш подбор без GitHub",
    "ours_no_tests": "Наш подбор без тестов",
    "ours_no_fsp": "Наш подбор без ФСП",
}


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:+.1f} %"


def to_markdown(result: dict[str, Any], meta: dict[str, Any]) -> str:
    m = result["matching"]
    lines = [
        "# Валидация подбора (E27-2)",
        "",
        f"Синтетический рынок: seed {meta['seed']}, хеш параметров `{meta['params_hash']}`; "
        f"кандидатов {m['candidates']} (приукрашивают {m['embellished_candidates']}), "
        f"потребностей {m['needs']}.",
        "",
        f"| Метод | precision@{m['k']} | nDCG@{m['k']} | приукрашенных в топ-{m['k']} |",
        "|---|---|---|---|",
    ]
    for name, row in m["table"].items():
        cells = f"{row['p10']:.3f} | {row['ndcg10']:.3f} | {row['embellished10']:.3f}"
        lines.append(f"| {LABELS[name]} | {cells} |")
    lift = m["lift"]
    lines += [
        "",
        f"Прирост nDCG@{m['k']}: к BM25 {_pct(lift['ndcg10']['vs_bm25'])}, "
        f"к BM25 с фильтрами {_pct(lift['ndcg10']['vs_bm25_filtered'])} (цель: +20 % к BM25 — "
        f"{'достигнута' if m['meets_target'] else 'не достигнута'}).",
        f"Прирост precision@{m['k']}: к BM25 {_pct(lift['p10']['vs_bm25'])}, "
        f"к BM25 с фильтрами {_pct(lift['p10']['vs_bm25_filtered'])}.",
        f"Вклад ФСП (Δ nDCG@{m['k']}): {m['fsp_delta_ndcg10']:+.3f}.",
        f"Категории потребности (E23-4): настоящая роль среди предложенных — "
        f"{m['category_hit'] * 100:.0f} % потребностей.",
        "",
        "Ограничения: рынок синтетический; уверенность в навыках для подбора считается упрощённой "
        "моделью доказательств (резюме, GitHub без подделок, тест, ФСП), а не полным графом core.",
        "",
    ]
    return "\n".join(lines)


def write_report(result: dict[str, Any], meta: dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, **result}
    (out / "eval.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "eval.md").write_text(to_markdown(result, meta), encoding="utf-8")
