"""Метрики банка и подбора, которым нужен код core (без БД): JSON в stdout.

Запускается подпроцессом из `services/core` (`uv run python <путь>/core_probe.py --seeds N`),
чтобы импортировать `app.*` в окружении core. Только чтение кода core, без побочных эффектов.

- `coverage` — семейств на ячейку «профессия MVP × тип навыка × грейд»:
  навык семейства входит в профессию, уровень в окне грейда (`selection.level_ok`), тип с ненулевой
  долей в плане грейда (`plan_shares`).
- `uniqueness` — доля различных вариантов (`stem`, `options`) на `seeds` сидов, по всему банку.
- `fairness` — impact ratio «без ФСП / с ФСП» при равном T (`matching.strength.fsp_impact_ratio`)
  на синтетическом пуле с весами из `scoring.yaml`.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "services" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

MVP_PROFESSIONS = ("backend", "frontend", "ml", "ai_engineer")  # профессии с полным банком заданий


def coverage() -> dict[str, Any]:
    from app.assessment import selection as sel
    from app.assessment.config import load_config
    from app.assessment.families import REGISTRY
    from app.taxonomy.loader import load_taxonomy
    from fsp_contracts.assessment import TestGrade

    cfg = load_config()
    roles = {r.slug: r for r in load_taxonomy(ROOT / "data" / "taxonomy").roles}
    cells: dict[str, int] = {}
    empty: list[str] = []
    for prof in MVP_PROFESSIONS:
        role = roles.get(prof)
        skills = {s for s, w in (role.skills if role else {}).items() if w > 0}
        for grade in TestGrade:
            for stype, share in sel.type_shares(grade, cfg).items():
                if share <= 0:
                    continue
                n = sum(
                    1
                    for f in REGISTRY.values()
                    if f.skill in skills
                    and str(f.skill_type) == stype
                    and sel.level_ok(f.level, grade, cfg)
                )
                key = f"{prof}/{stype}/{grade.value}"
                cells[key] = n
                if n == 0:
                    empty.append(key)
    return {"cells": len(cells), "empty": len(empty), "empty_cells": empty}


def uniqueness(n_seeds: int) -> dict[str, Any]:
    from app.assessment.families import REGISTRY
    from app.assessment.families.check import build, seeds

    seed_list = seeds(n_seeds)
    total = unique = 0
    worst: list[tuple[float, str]] = []
    for fam in sorted(REGISTRY.values(), key=lambda f: f.slug):
        seen = set()
        for s in seed_list:
            it = build(fam, s)
            seen.add(repr((it.stem, it.options)))
        total += len(seed_list)
        unique += len(seen)
        worst.append((len(seen) / len(seed_list), fam.slug))
    worst.sort()
    return {
        "share": round(unique / total, 4) if total else None,
        "seeds": n_seeds,
        "families": len(worst),
        "lowest": [{"family": s, "share": round(v, 4)} for v, s in worst[:5]],
    }


def fairness(seed: int, n: int = 3000) -> dict[str, Any]:
    from app.matching.strength import StrengthConfig, StrengthInput, fsp_impact_ratio, strength

    cfg = StrengthConfig.load()
    rnd = random.Random(seed)
    pool = []
    for _ in range(n):
        t = rnd.random()
        has = rnd.random() < 0.33
        res = strength(
            StrengthInput(
                t,
                fsp=rnd.uniform(0.3, 0.9) if has else 0.0,
                skills=rnd.random(),
                days_since_test=rnd.uniform(0, 365),
                completeness=rnd.uniform(0.4, 1.0),
            ),
            cfg,
        )
        pool.append((t, has, res.value))
    return {"impact_ratio": fsp_impact_ratio(pool, top_share=0.5), "pool": n}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args(argv)
    out = {"coverage": coverage(), "uniqueness": uniqueness(a.seeds), "fairness": fairness(a.seed)}
    sys.stdout.write(json.dumps(out, ensure_ascii=True, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
