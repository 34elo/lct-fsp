"""CLI майнинга мутаций.

    python -m app.assessment.mining mine --source thealgorithms       # GitHub, MUTMINE_GITHUB=1
    python -m app.assessment.mining mine --source NAME --dir PATH     # локальная копия
    python -m app.assessment.mining check data/questions/mutations/*.json  # автопроверка
    python -m app.assessment.mining import data/questions/mutations/*.json [--pilot]

Код проекта только читается: песочница обходит AST одной функции, `exec` не используется.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.assessment.mining.bank import Project, mine
from app.assessment.mining.sources import (
    BANK_DIR,
    SOURCES,
    SourceError,
    fetch,
    load_sources,
    require_license,
)


def _mine(args: argparse.Namespace) -> int:
    sources = load_sources(args.sources)
    if args.source not in sources:
        print(f"нет источника {args.source} в {args.sources}", file=sys.stderr)
        return 2
    src = sources[args.source]
    try:
        root = Path(args.dir) if args.dir else fetch(src)
        require_license(root, src.project.license)
    except SourceError as e:
        print(f"майнинг невозможен: {e}", file=sys.stderr)
        return 2
    project = src.project
    if args.dir and args.ref:
        project = Project(project.name, project.repo, args.ref, project.license, project.url)
    bank = mine(root, project, src.include)
    out = Path(args.out) if args.out else BANK_DIR / f"{project.name}.json"
    out.write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    st = bank["stats"]
    print(
        f"{project.name}: семейств {st['families']}, мутантов {st.get('mutants', 0)}, "
        f"убито {st.get('mutants_killed', 0)}, в семьях {st.get('mutants_used', 0)} → {out}"
    )
    return 0


def _check(args: argparse.Namespace) -> int:
    from app.assessment.families.check import check_family, seeds
    from app.assessment.mining.importer import family_of

    errs = 0
    total = 0
    for path in args.files:
        bank = json.loads(Path(path).read_text(encoding="utf-8"))
        for entry in bank["families"]:
            total += 1
            for e in check_family(
                family_of(entry, bank, skill_type=bank["skill_type"]), seeds(args.seeds)
            ):
                errs += 1
                print(f"FAIL {e}", file=sys.stderr)
    print(f"mutations-check: семейств {total} — {'OK' if not errs else f'ошибок: {errs}'}")
    return 1 if errs else 0


async def _import(banks: list[tuple[str, dict]], to_pilot: bool) -> int:
    from fsp_platform.db import make_engine, make_session_factory, session_scope

    from app.assessment.config import load_config
    from app.assessment.mining.importer import import_bank
    from app.config import Settings

    engine = make_engine(Settings().database_url)
    try:
        async with session_scope(make_session_factory(engine)) as session:
            for path, bank in banks:
                res = await import_bank(session, bank, load_config(), to_pilot=to_pilot)
                print(f"{path}: {dict(res)}")
    finally:
        await engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Майнинг мутаций открытого кода → семейства find_bug")
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mine")
    m.add_argument("--source", required=True)
    m.add_argument("--dir", help="локальная копия проекта вместо загрузки с GitHub")
    m.add_argument("--ref", help="ревизия локальной копии для атрибуции")
    m.add_argument("--out")
    m.add_argument("--sources", type=Path, default=SOURCES)
    c = sub.add_parser("check")
    c.add_argument("files", nargs="+")
    c.add_argument("--seeds", type=int, default=200)
    i = sub.add_parser("import")
    i.add_argument("files", nargs="+")
    i.add_argument("--pilot", action="store_true", help="прошедшие автопроверку — сразу в pilot")
    args = p.parse_args(argv)
    if args.cmd == "mine":
        return _mine(args)
    if args.cmd == "check":
        return _check(args)
    banks = [(f, json.loads(Path(f).read_text(encoding="utf-8"))) for f in args.files]
    return asyncio.run(_import(banks, args.pilot))


if __name__ == "__main__":
    raise SystemExit(main())
