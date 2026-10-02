#!/usr/bin/env python3
"""Создать сервис из шаблона: python tools/new_service.py <name> [--dest services]."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

TEMPLATE = Path(__file__).parent / "service-template"


def create(name: str, dest: Path) -> Path:
    if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
        raise ValueError("имя: латиница в нижнем регистре, цифры и дефис")
    target = dest / name
    if target.exists():
        raise FileExistsError(target)
    shutil.copytree(TEMPLATE, target, ignore=shutil.ignore_patterns("__pycache__"))
    for path in sorted(target.rglob("*")):
        if path.is_file():
            path.write_text(path.read_text().replace("__NAME__", name))
            if path.suffix == ".tmpl":
                path.rename(path.with_suffix(""))
    return target


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("name")
    p.add_argument("--dest", default=str(Path(__file__).parent.parent / "services"))
    args = p.parse_args()
    print(create(args.name, Path(args.dest)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
