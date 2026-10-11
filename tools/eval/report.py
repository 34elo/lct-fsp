"""Отчёт стенда оценки: markdown + JSON в `reports/eval/`."""

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


SECTION_LABELS = {
    "person": "ФИО, телефон, почта, город",
    "summary": "«Обо мне»",
    "experience": "Опыт: компания, должность, даты",
    "education": "Образование: вуз, год, специальность",
    "skills": "Навыки (полнота)",
}


def _resumes_md(r: dict[str, Any]) -> list[str]:
    verdict = "достигнута" if r["meets_target"] else "не достигнута"
    lines = [
        "# Разбор резюме hh.ru",
        "",
        f"Набор: {r['n_resumes']} обезличенных резюме (PDF и DOCX, вымышленные люди), "
        "`data/eval/resumes/hh/`; правиловая ветка ml без LLM.",
        "",
        f"Полнота полей: **{r['completeness']:.3f}** ({r['matched']} из {r['total']}); цель "
        f"≥ {r['target']} — {verdict}. Точность навыков (справочно): "
        f"{r['skills_precision']:.3f}.",
        "",
        "| Раздел | Полнота |",
        "|---|---|",
    ]
    for key, label in SECTION_LABELS.items():
        value = r["by_section"].get(key)
        lines.append(f"| {label} | {'—' if value is None else f'{value:.3f}'} |")
    lines += ["", "| Файл | Полнота | Не найдено |", "|---|---|---|"]
    for f in r["files"]:
        lines.append(f"| {f['file']} | {f['completeness']:.3f} | {', '.join(f['missed']) or '—'} |")
    lines.append("")
    return lines


def to_markdown(result: dict[str, Any], meta: dict[str, Any]) -> str:
    m = result["matching"]
    lines = [
        "# Валидация подбора",
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
        f"Категории потребности: настоящая роль среди предложенных — "
        f"{m['category_hit'] * 100:.0f} % потребностей.",
        "",
        "Ограничения: рынок синтетический; уверенность в навыках для подбора считается упрощённой "
        "моделью доказательств (резюме, GitHub без подделок, тест, ФСП), а не полным графом core.",
        "",
    ]
    if "resumes" in result:
        lines += _resumes_md(result["resumes"])
    return "\n".join(lines)


def write_report(result: dict[str, Any], meta: dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, **result}
    (out / "eval.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "eval.md").write_text(to_markdown(result, meta), encoding="utf-8")
