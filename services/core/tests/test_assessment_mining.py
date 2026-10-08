"""E30-3: майнинг мутаций открытого кода — песочница, мутанты, банк, семейства, импорт."""

import ast
import io
import json
import tarfile
from pathlib import Path
from random import Random

import pytest
from app.assessment.attempts import build_item, family_of
from app.assessment.config import load_config
from app.assessment.families.check import check_family, seeds
from app.assessment.mining import mutate
from app.assessment.mining.__main__ import main as cli
from app.assessment.mining.bank import Project, mine
from app.assessment.mining.extract import Case, parse_function, scan
from app.assessment.mining.family import MinedFamily
from app.assessment.mining.importer import family_of as mined_family
from app.assessment.mining.importer import import_bank
from app.assessment.mining.sandbox import Interpreter, Limit, Raised, Unsupported, run, same
from app.assessment.mining.sources import (
    SOURCES,
    SourceError,
    detect_license,
    fetch,
    load_sources,
    unpack,
)
from app.assessment.models import FamilyRow
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from fsp_platform.db import session_scope
from sqlalchemy import select

CFG = load_config()
DEMO = Path(__file__).resolve().parent / "fixtures" / "mutmine" / "demo"
TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"
PROJECT = Project("demo", "local", "fixture", "MIT")


def fn(src: str) -> ast.FunctionDef:
    return parse_function(src)


@pytest.fixture(scope="module")
def bank() -> dict:
    return mine(DEMO, PROJECT)


# --- песочница --------------------------------------------------------------------------------


def test_sandbox_runs_python_subset():
    src = (
        "def f(xs, k=2):\n"
        "    out = []\n"
        "    for i, x in enumerate(xs):\n"
        "        if x % k == 0 and i > 0:\n"
        "            out.append(x * 10)\n"
        "    d = {str(x): x for x in xs if x > 1}\n"
        "    s = ''.join(sorted(d.keys(), reverse=True))\n"
        "    return out, s, xs[1:3], len([y for y in range(5) if y != 2])\n"
    )
    assert run(fn(src), [[1, 2, 3, 4]]) == ([20, 40], "432", [2, 3], 4)
    rec = "def fact(n):\n    if n <= 1:\n        return 1\n    return n * fact(n - 1)\n"
    assert run(fn(rec), [6]) == 720
    err = "def g(x):\n    if x < 0:\n        raise ValueError('neg')\n    return [1][x]\n"
    assert run(fn(err), [-1]) == Raised("ValueError")
    assert run(fn(err), [5]) == Raised("IndexError")


def test_sandbox_does_not_mutate_test_literals():
    src = "def f(xs):\n    xs.append(1)\n    return len(xs)\n"
    interp, arg = Interpreter(fn(src)), [0]
    assert interp.call([arg]) == 2 and interp.call([arg]) == 2 and arg == [0]


@pytest.mark.parametrize(
    "body",
    [
        "import os\n    return 1",
        "return open('x').read()",
        "return x.__class__",
        "return __import__('os')",
        "return eval('1')",
        "return getattr(x, 'real')",
        "return (lambda: 1)()",
        "global y\n    return 1",
        "def h():\n        return 1\n    return h()",
        "with x:\n        return 1",
        "try:\n        return 1\n    except Exception:\n        return 2",
        "return x.system('id')",
        "yield 1",
    ],
)
def test_sandbox_rejects_unsafe(body):
    with pytest.raises(Unsupported):
        Interpreter(fn(f"def f(x):\n    {body}\n"))


@pytest.mark.parametrize(
    ("body", "arg"),
    [
        ("while True:\n        x += 1\n    return x", 0),
        ("return [0] * (10 ** x)", 9),
        ("return 9 ** 9 ** x", 9),
        ("return 'a' * x", 10**8),
        ("return f(x + 1)", 0),
        ("return list(range(x))", 10**9),
        ("return 1 << x", 10**6),
        ("return 'ab'.zfill(x)", 10**9),
        ("return ('%' + str(x) + 'd') % 1", 10**9),
        ("return ('%.' + str(x) + 'f') % 1.5", 10**9),
        ("return '%*d' % (x, 1)", 10**9),
        ("return ('%(a)' + str(x) + 'd') % {'a': 1}", 10**9),
        ("return round(1, -x)", 10**8),
    ],
)
def test_sandbox_limits(body, arg):
    with pytest.raises(Limit):
        Interpreter(fn(f"def f(x):\n    {body}\n")).call([arg])


def test_same_compares_floats_and_types():
    assert same(0.1 + 0.2, 0.3) and same([1, (2.0,)], [1, (2.0,)])
    assert not same([1], (1,)) and not same("1", 1) and same(Raised("KeyError"), Raised("KeyError"))


# --- извлечение и мутанты ---------------------------------------------------------------------


def test_scan_reads_doctests_and_test_files_without_running():
    funcs, seen = scan(DEMO)
    by = {f.name: f for f in funcs}
    assert seen >= 10
    assert {"cwd_of", "dunder", "shell"}.isdisjoint(by)  # import, dunder, os.system отброшены
    assert not (DEMO / "pkg" / "PWNED").exists()  # модуль с побочным эффектом не исполнялся
    assert Case((), None, "").call_text("f") == "f()"
    mv = by["max_value"]
    assert Raised("ValueError") in [c.expected for c in mv.cases]
    assert all('"""' not in ln for ln in mv.lines)  # строка документации вырезана из листинга
    bs = {c.call_text("binary_search"): c.expected for c in by["binary_search"].cases}
    assert bs["binary_search([1, 3, 5, 7, 9], 7)"] == 3  # assert из tests/cases_mathx.py
    pal = by["is_palindrome"].cases
    assert any(c.truthy and c.expected is True for c in pal)  # assertTrue
    assert any(not c.truthy and c.expected is False for c in pal)  # assertEqual(…, False)


def test_mutants_change_one_body_line_and_stay_valid():
    lines = next(f for f in scan(DEMO)[0] if f.name == "binary_search").lines
    ms = mutate.mutants(lines)
    assert len(ms) >= 10
    ops = {m.op for m in ms}
    assert {"cmp_boundary", "cmp_flip", "arith", "constant"} <= ops
    for m in ms:
        assert m.line >= 2 and m.text != lines[m.line - 1]  # заголовок не трогаем
        new = mutate.apply(lines, m)
        assert sum(a != b for a, b in zip(new, lines, strict=True)) == 1
        Interpreter(parse_function("\n".join(new) + "\n"))  # белый список держится


# --- банк -------------------------------------------------------------------------------------


def test_bank_every_mutant_is_proven_by_a_test(bank):
    st = bank["stats"]
    assert st["families"] >= 5 and st["mutants_killed"] > 0
    assert st["mutants_survived"] > 0  # эквивалентные или непокрытые мутанты отсеяны
    assert 0 < st["killed_share_used"] <= 1
    assert bank["project"]["license"] == "MIT" and bank["skill"] == "python"
    funcs = {f.name: f for f in scan(DEMO)[0]}
    for fam in bank["families"]:
        f = funcs[fam["function"]]
        cases = [c for c in f.cases if c.call_text(f.name) in {x["call"] for x in fam["cases"]}]
        orig = Interpreter(f.tree())
        plain = [c for c in cases if not c.truthy]
        assert all(same(orig.call(c.args, dict(c.kwargs)), c.expected) for c in plain)
        assert 1 <= len(fam["mutants"]) <= 8 and 2 <= fam["level"] <= 4
        for m in fam["mutants"]:
            mut = Interpreter(parse_function("\n".join(mutate.apply(f.lines, _m(m))) + "\n"))
            kill = next(c for c in cases if c.call_text(f.name) == m["kill"]["call"])
            try:
                got = mut.call(kill.args, dict(kill.kwargs))
                got = bool(got) if kill.truthy and not isinstance(got, Raised) else got
            except Limit:
                got = Raised("Timeout")
            assert not same(got, kill.expected), (fam["function"], m)
    hang = next(f for f in bank["families"] if f["function"] == "forever")
    assert any(m["kill"]["got"] == "raises Timeout" for m in hang["mutants"])


def _m(m: dict) -> mutate.Mutant:
    return mutate.Mutant(m["line"], m["text"], m["op"])


def test_bank_is_deterministic(bank):
    assert json.dumps(mine(DEMO, PROJECT), sort_keys=True) == json.dumps(bank, sort_keys=True)


# --- семейство --------------------------------------------------------------------------------


def test_mined_family_passes_autocheck_and_scores(bank):
    for entry in bank["families"]:
        fam = mined_family(entry, bank, skill_type="hard")
        assert check_family(fam, seeds(100)) == []
        item = fam.generate(Random(7), None)  # type: ignore[arg-type]
        assert item == fam.generate(Random(7), None)  # type: ignore[arg-type]
        assert "exec" not in item.meta and "exec_bug" not in item.meta  # чужой код не исполняем
        line = item.key[0]
        assert fam.score(item, [line]) == 1.0 and fam.score(item, [line % 2 + 1 + line]) == 0.0
        assert "demo" in item.stem and "MIT" in item.stem and f"{line:>2} | " in item.stem
        variants = {tuple(fam.generate(Random(s), None).key) for s in range(40)}  # type: ignore[arg-type]
        assert len(variants) == len({m["line"] for m in entry["mutants"]})


# --- источники --------------------------------------------------------------------------------


def test_sources_config_and_license():
    srcs = load_sources(SOURCES)
    assert {"thealgorithms", "keon_algorithms"} <= set(srcs)
    assert all(s.project.license in ("MIT", "Apache-2.0") for s in srcs.values())
    assert detect_license(DEMO) == "MIT"


def test_sources_reject_bad_license(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("sources:\n  - {name: x, repo: a/b, ref: v1, license: GPL-3.0}\n")
    with pytest.raises(SourceError):
        load_sources(p)
    (tmp_path / "LICENSE").write_text("GNU GENERAL PUBLIC LICENSE Version 3")
    assert detect_license(tmp_path) is None


def test_fetch_needs_env(monkeypatch):
    monkeypatch.delenv("MUTMINE_GITHUB", raising=False)
    with pytest.raises(SourceError):
        fetch(load_sources(SOURCES)["thealgorithms"])


def test_unpack_keeps_only_safe_python(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in [
            ("repo-sha/LICENSE", b"MIT"),
            ("repo-sha/pkg/a.py", b"x = 1\n"),
            ("repo-sha/../escape.py", b"bad"),
            ("repo-sha/run.sh", b"rm -rf /"),
        ]:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo("repo-sha/pkg/link.py")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        tar.addfile(link)
    dest = tmp_path / "out"
    assert unpack(buf.getvalue(), dest) == 2
    got = sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())
    assert got == ["LICENSE", "pkg/a.py"] and not (tmp_path / "escape.py").exists()


def test_cli_mine_and_check(tmp_path, capsys):
    out = tmp_path / "demo.json"
    srcs = tmp_path / "s.yaml"
    srcs.write_text("sources:\n  - {name: demo, repo: local/demo, ref: v1, license: MIT}\n")
    args = ["mine", "--source", "demo", "--dir", str(DEMO), "--out", str(out)]
    assert cli([*args, "--sources", str(srcs)]) == 0
    assert json.loads(out.read_text())["stats"]["families"] >= 5
    assert cli(["check", str(out), "--seeds", "20"]) == 0
    assert "OK" in capsys.readouterr().out


# --- импорт в банк ----------------------------------------------------------------------------


@pytest.fixture
async def taxonomy_loaded(factory):
    async with session_scope(factory) as s:
        await tax.sync(s, load_taxonomy(TAXONOMY))


async def test_import_is_idempotent_and_rebuilds_items(factory, taxonomy_loaded, bank):
    async with session_scope(factory) as s:
        res = await import_bank(s, bank, CFG)
    assert res["created"] == len(bank["families"]) and not res["failed_check"]
    async with session_scope(factory) as s:
        again = await import_bank(s, bank, CFG, to_pilot=True)
        assert again["unchanged"] == len(bank["families"]) and not again["created"]
        rows = (await s.scalars(select(FamilyRow).where(FamilyRow.source == "mutation"))).all()
        assert len(rows) == len(bank["families"])
        row = rows[0]
        assert row.status == "draft" and row.kind == "find_bug" and row.key_status == "approved"
        assert row.b == CFG.prior_b(row.level) and row.skill_type == "hard"
        fam = family_of(row)
        assert isinstance(fam, MinedFamily)
        item = build_item(fam, 12345, None)
        assert item.key == build_item(fam, 12345, "fintech").key  # мир не меняет ключ


async def test_import_to_pilot(factory, taxonomy_loaded, bank):
    small = {**bank, "families": bank["families"][:2]}
    async with session_scope(factory) as s:
        await import_bank(s, small, CFG, to_pilot=True)
    async with session_scope(factory) as s:
        rows = (await s.scalars(select(FamilyRow).where(FamilyRow.source == "mutation"))).all()
        assert {r.status for r in rows} == {"pilot"} and len(rows) == 2
