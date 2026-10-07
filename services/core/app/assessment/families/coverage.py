"""Покрытие банка «профессия × грейд × тип навыка» (E36-2, ADR-027 п. 1): `make bank-coverage`.

Ячейка — число кодовых семейств, у которых навык входит в профессию (`roles.yaml`, вес > 0),
тип навыка совпадает и уровень попадает в окно грейда (`selection.level_ok`). Считаются только
типы с ненулевой долей в плане грейда (`plan_shares`), как и в `tools/metrics/core_probe.py`.

Обязательны без пустых ячеек видимые профессии (`profession: true`, `active` не `false`): Backend,
Frontend и AI Engineer. Скрытые профессии в отчёте для справки, их пустые ячейки не ошибка.
`make families-check` вызывает `errors()` и падает на пустой обязательной ячейке.

Отчёт — `reports/bank/coverage.{json,md}`. Только чтение кода и справочника.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from fsp_contracts.assessment import TEST_GRADE_ORDER, SkillType

from app.assessment import selection as sel
from app.assessment.config import AssessmentConfig, load_config
from app.assessment.families import REGISTRY
from app.assessment.families.base import Family

ROOT = Path(__file__).resolve().parents[5]
TAXONOMY = ROOT / "data" / "taxonomy"
OUT_DIR = ROOT / "reports" / "bank"


@dataclass(frozen=True)
class Profession:
    slug: str
    title: str
    active: bool
    skills: frozenset[str]


def professions(taxonomy_dir: Path = TAXONOMY) -> list[Profession]:
    """Профессии теста из справочника (видимые первыми, затем скрытые; внутри — как в файле)."""
    from app.taxonomy.loader import load_taxonomy

    out = [
        Profession(r.slug, r.name, r.active, frozenset(s for s, w in r.skills.items() if w > 0))
        for r in load_taxonomy(taxonomy_dir).roles
        if r.profession
    ]
    return sorted(out, key=lambda p: not p.active)


def compute(profs: Iterable[Profession], families: Iterable[Family], cfg: AssessmentConfig) -> dict:
    """`{professions: [{slug, title, active, cells: {grade: {type: [семейства]}}}], empty: [...]}`.

    `empty` — пустые ячейки видимых профессий в виде `backend/senior/soft`.
    """
    fams = sorted(families, key=lambda f: f.slug)
    rows, empty = [], []
    for p in profs:
        cells: dict[str, dict[str, list[str]]] = {}
        for grade in TEST_GRADE_ORDER:
            shares = sel.type_shares(grade, cfg)
            row: dict[str, list[str]] = {}
            for t in SkillType:
                if shares.get(t.value, 0) <= 0:
                    continue
                row[t.value] = [
                    f.slug
                    for f in fams
                    if f.skill in p.skills
                    and SkillType(f.skill_type) == t
                    and sel.level_ok(f.level, grade, cfg)
                ]
                if p.active and not row[t.value]:
                    empty.append(f"{p.slug}/{grade.value}/{t.value}")
            cells[grade.value] = row
        rows.append({"slug": p.slug, "title": p.title, "active": p.active, "cells": cells})
    return {"professions": rows, "empty": empty}


def errors(taxonomy_dir: Path = TAXONOMY, cfg: AssessmentConfig | None = None) -> list[str]:
    """Пустые обязательные ячейки — для `families-check`."""
    rep = compute(professions(taxonomy_dir), REGISTRY.values(), cfg or load_config())
    return [f"покрытие: пустая ячейка {c} (профессия/грейд/тип навыка)" for c in rep["empty"]]


def to_markdown(rep: dict) -> str:
    types = [t.value for t in SkillType]
    lines = [
        "# Покрытие банка: профессия × грейд × тип навыка",
        "",
        "Число кодовых семейств в ячейке (E36-2, ADR-027 п. 1). "
        "Скрытые профессии — для справки, их пустые ячейки не ошибка.",
        "",
        "| Профессия | Грейд | " + " | ".join(types) + " |",
        "|---|---|" + "---|" * len(types),
    ]
    for p in rep["professions"]:
        name = p["slug"] if p["active"] else f"{p['slug']} (скрыта)"
        for grade, row in p["cells"].items():
            vals = [str(len(row[t])) if t in row else "—" for t in types]
            lines.append(f"| {name} | {grade} | " + " | ".join(vals) + " |")
    lines += ["", f"Пустых обязательных ячеек: {len(rep['empty'])}"]
    lines += [f"- {c}" for c in rep["empty"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--taxonomy", type=Path, default=TAXONOMY)
    p.add_argument("--out", type=Path, default=OUT_DIR)
    args = p.parse_args(argv)
    rep = compute(professions(args.taxonomy), REGISTRY.values(), load_config())
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "coverage.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    md = to_markdown(rep)
    (args.out / "coverage.md").write_text(md, encoding="utf-8")
    sys.stdout.write(md)
    return 1 if rep["empty"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
