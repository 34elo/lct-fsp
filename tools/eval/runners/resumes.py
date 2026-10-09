"""Разбор резюме hh.ru (E39-19): полнота полей на обезличенном наборе `data/eval/resumes/hh/`.

Набор — 10 вымышленных резюме в раскладке выгрузки hh.ru (PDF и DOCX) и эталон `gold.json`
(генератор — `tools/eval/gen_hh_resumes.py`). Разбор — правиловая ветка ml без LLM
(`LLM_ENABLED=false`): текст из файла → `extract_rules` → `assemble`.

Поле засчитано, если разобранное значение совпало с эталоном: ФИО, телефон, почта, город, начало
«Обо мне»; для каждой записи опыта (по порядку) — компания, должность, начало, конец; для каждой
записи образования — вуз, год, специальность; для каждого навыка из эталона — найден ли он.
Полнота = засчитано / всего по эталону (цель ≥ 0.8). Точность навыков — справочно.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
HH_DIR = ROOT / "data" / "eval" / "resumes" / "hh"
TAXONOMY = ROOT / "data" / "taxonomy" / "skills.yaml"
TARGET = 0.8
TODAY = date(2026, 10, 1)
SECTIONS = ("person", "summary", "experience", "education", "skills")


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold().replace("ё", "е")


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _score(gold: dict, parsed: Any) -> tuple[dict[str, list[int]], dict[str, list[str]]]:
    """`{раздел: [засчитано, всего]}` и пропущенные поля `{раздел: [«поле»]}`."""
    got: dict[str, list[int]] = {s: [0, 0] for s in SECTIONS}
    miss: dict[str, list[str]] = {s: [] for s in SECTIONS}

    def check(section: str, label: str, ok: bool) -> None:
        got[section][1] += 1
        got[section][0] += ok
        if not ok:
            miss[section].append(label)

    p = parsed.person
    check("person", "full_name", _norm(p.full_name) == _norm(gold["full_name"]))
    check("person", "phone", _digits(p.phone) == _digits(gold["phone"]))
    check("person", "email", _norm(p.email) == _norm(gold["email"]))
    check("person", "city", _norm(p.city) == _norm(gold["city"]))
    if gold.get("summary"):
        want = _norm(gold["summary"])[:50]
        check("summary", "summary", _norm(parsed.summary).startswith(want))

    for i, g in enumerate(gold["experience"]):
        e = parsed.experience[i] if i < len(parsed.experience) else None
        for key in ("company", "title", "start", "end"):
            have = getattr(e, key, None) if e else None
            ok = (have == g[key]) if key in ("start", "end") else _norm(have) == _norm(g[key])
            check("experience", f"experience[{i}].{key}", e is not None and ok)

    for i, g in enumerate(gold["education"]):
        e = parsed.education[i] if i < len(parsed.education) else None
        check(
            "education",
            f"education[{i}].institution",
            bool(e) and _norm(e.institution) == _norm(g["institution"]),
        )
        check("education", f"education[{i}].year_end", bool(e) and e.year_end == g["year_end"])
        check("education", f"education[{i}].field", bool(e) and _norm(e.field) == _norm(g["field"]))

    found = {s.slug for s in parsed.skills}
    for slug in g_skills(gold):
        check("skills", f"skill:{slug}", slug in found)
    return got, miss


def g_skills(gold: dict) -> list[str]:
    return list(gold["skills"])


def run_resumes(directory: Path = HH_DIR) -> dict[str, Any]:
    for p in (ROOT / "services/ml", ROOT / "packages/contracts"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import yaml
    from fsp_ml import resume_parser
    from fsp_ml.resume_text import extract_text
    from fsp_ml.taxonomy import TaxonomyIndex

    skills = yaml.safe_load(TAXONOMY.read_text(encoding="utf-8"))["skills"]
    index = TaxonomyIndex.from_snapshot({"version": 1, "skills": skills})
    items = json.loads((directory / "gold.json").read_text(encoding="utf-8"))["resumes"]

    totals = {s: [0, 0] for s in SECTIONS}
    files = []
    precision = [0, 0]
    for gold in items:
        text = extract_text((directory / gold["file"]).read_bytes())
        out = resume_parser.extract_rules(text, index)
        parsed = resume_parser.assemble(
            text, out, index, version=resume_parser.RULES_VERSION, today=TODAY
        )
        got, miss = _score(gold, parsed)
        for s in SECTIONS:
            totals[s][0] += got[s][0]
            totals[s][1] += got[s][1]
        ok = sum(v[0] for v in got.values())
        n = sum(v[1] for v in got.values())
        precision[0] += len({s.slug for s in parsed.skills} & set(gold["skills"]))
        precision[1] += len(parsed.skills)
        files.append(
            {
                "file": gold["file"],
                "completeness": round(ok / n, 3) if n else None,
                "matched": ok,
                "total": n,
                "missed": [m for v in miss.values() for m in v],
            }
        )

    matched = sum(v[0] for v in totals.values())
    total = sum(v[1] for v in totals.values())
    completeness = matched / total if total else 0.0
    return {
        "files": files,
        "n_resumes": len(items),
        "by_section": {s: round(v[0] / v[1], 3) if v[1] else None for s, v in totals.items()},
        "completeness": round(completeness, 3),
        "matched": matched,
        "total": total,
        "skills_precision": round(precision[0] / precision[1], 3) if precision[1] else None,
        "target": TARGET,
        "meets_target": completeness >= TARGET,
    }
