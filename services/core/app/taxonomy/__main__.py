"""`python -m app.taxonomy` (make taxonomy-load): загрузить data/taxonomy и правила ФСП в БД."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from fsp_platform.db import make_engine, make_session_factory, session_scope

from app.config import Settings
from app.taxonomy import service
from app.taxonomy.loader import TaxonomyError, load_taxonomy

ROOT = Path(__file__).resolve().parents[4]


async def run(directory: Path, rules: Path) -> int:
    try:
        data = load_taxonomy(directory, rules)
    except TaxonomyError as exc:
        print(f"Ошибка справочника: {exc}", file=sys.stderr)
        return 1
    engine = make_engine(Settings().database_url)
    try:
        async with session_scope(make_session_factory(engine)) as session:
            res = await service.sync(session, data)
    finally:
        await engine.dispose()
    state = "обновлён" if res.bumped else "без изменений"
    print(
        f"taxonomy v{res.version}: {state}, навыков {len(data.skills)}, "
        f"затронуто {len(res.changed_skill_ids)}"
    )
    for label, items in (
        ("правила ФСП без навыка в ядре", res.skipped_rule_skills),
        ("синонимы заняты не сидом", res.skipped_aliases),
    ):
        if items:
            print(f"пропущено, {label}: {', '.join(items)}", file=sys.stderr)
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", type=Path, default=ROOT / "data" / "taxonomy")
    p.add_argument("--rules", type=Path, default=ROOT / "data" / "fsp" / "discipline_rules.yaml")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args.dir, args.rules)))


if __name__ == "__main__":
    main()
