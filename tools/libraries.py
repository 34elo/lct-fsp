"""Список библиотек с версиями из lock-файлов (uv.lock, pnpm-lock.yaml) → docs/libraries.md.

Только stdlib. Версии берём из lock-файлов; лицензии — из метаданных установленных пакетов
(`.venv/.../*.dist-info/METADATA`, `node_modules/.pnpm/**/package.json`), если окружение
установлено. Нет метаданных — «проверить».
Запуск: `python tools/libraries.py [--root .] [--out docs/libraries.md]`.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

UNKNOWN = "проверить"
_NAME_RE = re.compile(r'\{\s*name\s*=\s*"([^"]+)"')


@dataclass
class Lib:
    name: str
    version: str
    direct_in: set[str] = field(default_factory=set)  # где объявлена напрямую (пакет/воркспейс)
    license: str = UNKNOWN


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_uv_lock(text: str) -> tuple[dict[str, Lib], list[str]]:
    """Возвращает (внешние пакеты по нормализованному имени, имена членов воркспейса)."""
    libs: dict[str, Lib] = {}
    members: dict[str, set[str]] = {}
    for block in text.split("[[package]]")[1:]:
        name = re.search(r'^name = "([^"]+)"', block, re.M)
        version = re.search(r'^version = "([^"]+)"', block, re.M)
        source = re.search(r"^source = \{ ([a-z]+) =", block, re.M)
        if not name:
            continue
        kind = source.group(1) if source else ""
        if kind in ("editable", "virtual", "workspace"):
            head = block.split("[package.metadata]")[0]
            members[name.group(1)] = {_norm(n) for n in _NAME_RE.findall(head)}
        elif version:
            libs[_norm(name.group(1))] = Lib(name.group(1), version.group(1))
    for member, deps in members.items():
        for dep in deps:
            if dep in libs:
                libs[dep].direct_in.add(member)
    return libs, sorted(members)


def parse_pnpm_lock(text: str) -> dict[str, Lib]:
    """Пакеты из секции `packages:`; прямые зависимости — из `importers:`."""
    libs: dict[str, Lib] = {}
    section = ""
    importer = ""
    dep_name = ""
    direct: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        if re.match(r"^[a-zA-Z]+:", line):
            section = line.split(":")[0]
            continue
        if section == "importers":
            m = re.match(r"^  (\S.*):\s*(\{\})?$", line)
            if m:
                importer = m.group(1).strip("'")
                continue
            m = re.match(r"^      ('?[^\s'][^:]*'?):\s*$", line)
            if m:
                dep_name = m.group(1).strip("'")
                continue
            m = re.match(r"^        version: (\S+)", line)
            if m and dep_name and not m.group(1).startswith("link:"):
                direct.append((importer, dep_name, m.group(1).split("(")[0]))
        elif section == "packages":
            m = re.match(r"^  '?(@?[^'\s]+)@([^@'\s]+)'?:\s*$", line)
            if m:
                libs[f"{m.group(1)}@{m.group(2)}"] = Lib(m.group(1), m.group(2))
    for imp, name, ver in direct:
        lib = libs.get(f"{name}@{ver}")
        if lib:
            lib.direct_in.add(imp)
    return libs


def python_license(site: Path, lib: Lib) -> str:
    """Лицензия из METADATA установленного пакета (License-Expression → License → классификатор)."""
    for dist in site.glob("*.dist-info"):
        stem = dist.name[: -len(".dist-info")]
        pkg, _, ver = stem.rpartition("-")
        if _norm(pkg) != _norm(lib.name) or ver != lib.version:
            continue
        meta = dist / "METADATA"
        if not meta.is_file():
            break
        head = meta.read_text(encoding="utf-8", errors="replace").split("\n\n", 1)[0]
        expr = re.search(r"^License-Expression: (.+)$", head, re.M)
        if expr:
            return expr.group(1).strip()
        lic = re.search(r"^License: (.+)$", head, re.M)
        if lic and len(lic.group(1).strip()) <= 40:
            return lic.group(1).strip()
        cls = re.findall(r"^Classifier: License :: (?:OSI Approved :: )?(.+)$", head, re.M)
        if cls:
            return ", ".join(c.strip() for c in cls)
        break
    return UNKNOWN


def npm_license(pnpm_dir: Path, lib: Lib) -> str:
    """Лицензия из package.json пакета в node_modules/.pnpm (если установлен)."""
    enc = lib.name.replace("/", "+")
    for d in pnpm_dir.glob(f"{enc}@{lib.version}*"):
        pj = d / "node_modules" / lib.name / "package.json"
        if not pj.is_file():
            continue
        try:
            lic = json.loads(pj.read_text(encoding="utf-8")).get("license")
        except (OSError, ValueError):
            continue
        if isinstance(lic, dict):
            lic = lic.get("type")
        if isinstance(lic, str) and lic:
            return lic
    return UNKNOWN


def _esc(s: str) -> str:
    return s.replace("|", "\\|")


def _table(libs: list[Lib], with_where: bool) -> list[str]:
    head = "| Библиотека | Версия | Лицензия |" + (" Где объявлена |" if with_where else "")
    sep = "|---|---|---|" + ("---|" if with_where else "")
    rows = [head, sep]
    for lib in libs:
        row = f"| {_esc(lib.name)} | {lib.version} | {_esc(lib.license)} |"
        if with_where:
            row += f" {', '.join(sorted(lib.direct_in))} |"
        rows.append(row)
    return rows


def render(py: dict[str, Lib], members: list[str], npm: dict[str, Lib]) -> str:
    py_all = sorted(py.values(), key=lambda x: _norm(x.name))
    npm_all = sorted(npm.values(), key=lambda x: (x.name.lower(), x.version))
    py_dir = [x for x in py_all if x.direct_in]
    npm_dir = [x for x in npm_all if x.direct_in]
    out = [
        "# Библиотеки и версии",
        "",
        "> Сгенерировано `make libraries` (`tools/libraries.py`) из `uv.lock` и "
        "`pnpm-lock.yaml`. Руками не правим.",
        "> Лицензии взяты из метаданных установленных пакетов; «проверить» — метаданных нет "
        "(окружение не установлено или лицензия не указана).",
        "",
        f"Python 3.12: {len(py_all)} пакетов, из них объявлены напрямую {len(py_dir)} "
        f"(члены воркспейса: {', '.join(members)}).",
        f"JavaScript (pnpm): {len(npm_all)} пакетов, из них напрямую {len(npm_dir)}.",
        "",
        "## Python: прямые зависимости",
        "",
        *_table(py_dir, True),
        "",
        "## JavaScript: прямые зависимости",
        "",
        *_table(npm_dir, True),
        "",
        "## Python: все пакеты (включая транзитивные)",
        "",
        *_table(py_all, False),
        "",
        "## JavaScript: все пакеты (включая транзитивные)",
        "",
        *_table(npm_all, False),
        "",
    ]
    return "\n".join(out)


def build(root: Path) -> str:
    py, members = parse_uv_lock((root / "uv.lock").read_text(encoding="utf-8"))
    npm = parse_pnpm_lock((root / "pnpm-lock.yaml").read_text(encoding="utf-8"))
    sites = list((root / ".venv" / "lib").glob("python*/site-packages"))
    win = root / ".venv" / "Lib" / "site-packages"  # раскладка venv на Windows
    if not sites and win.is_dir():
        sites = [win]
    if sites:
        for lib in py.values():
            lib.license = python_license(sites[0], lib)
    pnpm_dir = root / "node_modules" / ".pnpm"
    if pnpm_dir.is_dir():
        for lib in npm.values():
            lib.license = npm_license(pnpm_dir, lib)
    return render(py, members, npm)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--out", type=Path, default=Path("docs/libraries.md"))
    args = ap.parse_args()
    text = build(args.root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"{args.out}: {len(text.splitlines())} строк")


if __name__ == "__main__":
    main()
