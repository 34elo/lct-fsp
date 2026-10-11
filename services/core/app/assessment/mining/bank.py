"""Майнинг семейств `find_bug`: функция → мутанты → убитые тестами → запись банка.

Конвейер для одного проекта:
1. `extract.scan` — функции из белого списка песочницы и их тесты (доктесты, `assert`);
2. оригинал в песочнице проходит тесты (случаи, где не проходит, отбрасываются);
3. `mutate.mutants` — правки в одной строке; мутант годен, если хотя бы один тест его убивает
   (другой результат, исключение или превышение лимита — «тест завис»);
4. семейство = функция с 1–8 убитыми мутантами; вариант по сиду — один из них, ключ — его строка.

Банк — JSON (`data/questions/mutations/<проект>.json`) с атрибуцией, лицензией и статистикой
для метрики «доля убитых мутантов, ставших годными семействами».
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.assessment.mining import mutate
from app.assessment.mining.extract import Case, Func, parse_function, scan
from app.assessment.mining.sandbox import Interpreter, Limit, Raised, Unsupported, same

SCHEMA = 1
MIN_CASES = 2
MAX_CASES = 12
MAX_MUTANTS = 8
MAX_PER_LINE = 2
MAX_REPR = 120


@dataclass(frozen=True)
class Project:
    name: str
    repo: str  # owner/name на GitHub или «local»
    ref: str
    license: str  # MIT | Apache-2.0
    url: str = ""


def _outcome(interp: Interpreter, case: Case) -> Any:
    """Результат вызова в песочнице; `Limit` — как «тест завис» (мутант убит)."""
    try:
        res = interp.call(case.args, dict(case.kwargs))
    except Limit:
        return Raised("Timeout")
    if case.truthy and not isinstance(res, Raised):
        return bool(res)
    return res


def passes(res: Any, case: Case) -> bool:
    return same(res, case.expected)


def _short(v: Any) -> str:
    r = v if isinstance(v, str) else repr(v)
    return r if len(r) <= MAX_REPR else r[: MAX_REPR - 1] + "…"


def _level(n_lines: int) -> int:
    return 2 if n_lines <= 8 else 3 if n_lines <= 16 else 4


def _slug(project: str, module: str, name: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "_", Path(module).with_suffix("").as_posix().lower()).strip("_")
    h = hashlib.sha1(f"{project}:{module}:{name}".encode()).hexdigest()[:6]
    base = f"m-{project}-{stem[-30:]}-{name.lower()}"[:72]
    return f"{base}-{h}"


def mine_function(f: Func) -> tuple[dict | None, Counter]:
    """Запись семейства или None; счётчики мутантов (всего, убито, эквивалентных, неисполнимых)."""
    stats: Counter = Counter()
    try:
        orig = Interpreter(f.tree())
    except (Unsupported, SyntaxError):
        stats["rejected_unsupported"] += 1
        return None, stats
    cases: list[Case] = []
    for c in f.cases:
        try:
            if passes(_outcome(orig, c), c):
                cases.append(c)
        except Unsupported:
            stats["rejected_unsupported"] += 1
            return None, stats
    # Уникальные случаи, не больше MAX_CASES: сначала короткие (их проще показать кандидату)
    uniq: dict[str, Case] = {}
    for c in sorted(cases, key=lambda c: len(c.call_text(f.name))):
        uniq.setdefault(c.call_text(f.name), c)
    cases = list(uniq.values())[:MAX_CASES]
    if len(cases) < MIN_CASES:
        stats["rejected_few_tests"] += 1
        return None, stats

    killed: list[dict] = []
    per_line: Counter = Counter()
    for m in mutate.mutants(f.lines):
        stats["mutants"] += 1
        try:
            interp = Interpreter(parse_function("\n".join(mutate.apply(f.lines, m)) + "\n"))
            kill = None
            for c in cases:
                got = _outcome(interp, c)
                if not passes(got, c):
                    kill = (c, got)
                    break
        except (Unsupported, SyntaxError):
            stats["mutants_unsupported"] += 1
            continue
        if kill is None:
            stats["mutants_survived"] += 1  # эквивалентный или тестов не хватило
            continue
        stats["mutants_killed"] += 1
        if per_line[m.line] >= MAX_PER_LINE:
            continue
        per_line[m.line] += 1
        c, got = kill
        killed.append(
            {
                "line": m.line,
                "text": m.text,
                "op": m.op,
                "kill": {
                    "call": _short(c.call_text(f.name)),
                    "expected": _short(c.expected_text()),
                    "got": _short(repr(got)),
                    "origin": c.origin,
                },
            }
        )
    if not killed:
        stats["rejected_no_killed"] += 1
        return None, stats
    # Разнообразие: по одному на строку, затем вторые — детерминированно
    lines_seen: set[int] = set()
    first, second = [], []
    for k in killed:
        (second if k["line"] in lines_seen else first).append(k)
        lines_seen.add(k["line"])
    chosen = (first + second)[:MAX_MUTANTS]
    stats["mutants_used"] += len(chosen)
    return {
        "module": f.module,
        "function": f.name,
        "doc": f.doc,
        "lines": f.lines,
        "level": _level(len(f.lines)),
        "cases": [
            {
                "call": _short(c.call_text(f.name)),
                "expected": _short(c.expected_text()),
                "origin": c.origin,
            }
            for c in cases
        ],
        "mutants": sorted(chosen, key=lambda k: (k["line"], k["text"])),
    }, stats


def mine(root: Path, project: Project, include: list[str] | None = None) -> dict:
    """Банк проекта: семейства и статистика. Ничего из проекта не импортируется и не запускается."""
    funcs, seen = scan(root, include)
    total: Counter = Counter(functions_seen=seen, functions_candidates=len(funcs))
    families = []
    for f in funcs:
        fam, st = mine_function(f)
        total.update(st)
        if fam is not None:
            fam["slug"] = _slug(project.name, f.module, f.name)
            families.append(fam)
    slugs = Counter(fam["slug"] for fam in families)
    families = [fam for fam in families if slugs[fam["slug"]] == 1]
    total["families"] = len(families)
    killed = total["mutants_killed"]
    total_dict = dict(sorted(total.items()))
    total_dict["killed_share_used"] = round(total["mutants_used"] / killed, 3) if killed else 0.0
    return {
        "schema": SCHEMA,
        "project": {
            "name": project.name,
            "repo": project.repo,
            "ref": project.ref,
            "license": project.license,
            "url": project.url,
        },
        "skill": "python",
        "skill_type": "hard",
        "stats": total_dict,
        "families": sorted(families, key=lambda x: x["slug"]),
    }
