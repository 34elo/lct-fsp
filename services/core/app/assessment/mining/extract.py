"""Разбор открытого проекта: функции-кандидаты и тесты как данные.

Файлы проекта только читаются как текст и разбираются `ast.parse`. Модули не импортируются,
тесты не запускаются. Тестовый случай — литералы из доктеста (`>>> f(1, 2)` → `3`) или из
`assert f(…) == …` / `self.assertEqual(f(…), …)` в тестовых файлах: аргументы и ожидание берёт
`ast.literal_eval`, который вычисляет только литералы.
"""

from __future__ import annotations

import ast
import doctest
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.assessment.mining.sandbox import Limit, Raised, Unsupported, _check_value, validate

MAX_FILE_BYTES = 300_000
MIN_LINES = 3
MAX_LINES = 30
_SKIP_DIRS = {".git", "venv", ".venv", "node_modules", "build", "dist", "docs", "__pycache__"}
_ASSERT_EQ = {"assertEqual", "assertEquals", "assertListEqual", "assertTupleEqual",
              "assertDictEqual", "assertAlmostEqual"}  # fmt: skip
_ASSERT_BOOL = {"assertTrue": True, "assertFalse": False}


@dataclass(frozen=True)
class Case:
    """Тестовый случай: вызов с литералами и ожидание. `truthy` — `assert f(…)` / `assertTrue`."""

    args: tuple[Any, ...]
    expected: Any
    origin: str
    kwargs: tuple[tuple[str, Any], ...] = ()
    truthy: bool = False

    def call_text(self, name: str) -> str:
        parts = [repr(a) for a in self.args] + [f"{k}={v!r}" for k, v in self.kwargs]
        return f"{name}({', '.join(parts)})"

    def expected_text(self) -> str:
        if self.truthy:
            return "истинное значение" if self.expected else "ложное значение"
        return repr(self.expected)


@dataclass
class Func:
    """Функция-кандидат: код без строки документации, строки листинга с 1."""

    module: str  # путь от корня проекта
    name: str
    lines: list[str]
    doc: str
    cases: list[Case] = field(default_factory=list)

    @property
    def source(self) -> str:
        return "\n".join(self.lines) + "\n"

    def tree(self) -> ast.FunctionDef:
        return parse_function(self.source)


def parse_function(source: str) -> ast.FunctionDef:
    mod = ast.parse(source)
    if len(mod.body) != 1 or not isinstance(mod.body[0], ast.FunctionDef):
        raise Unsupported("ожидалась одна функция")
    return mod.body[0]


def py_files(root: Path) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root)
        if any(part in _SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_FILE_BYTES:
            continue
        out.append(p)
    return out


def is_test_file(rel: Path) -> bool:
    n = rel.name
    in_tests = any(part in {"tests", "test", "testing"} for part in rel.parts[:-1])
    return in_tests or n.startswith("test_") or n.endswith("_test.py") or n == "conftest.py"


def _read_tree(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return None


def _strip(fn: ast.FunctionDef, src_lines: list[str]) -> tuple[list[str], str] | None:
    """Строки функции без строки документации и пустых строк; первая строка docstring."""
    lines = src_lines[fn.lineno - 1 : fn.end_lineno]
    doc = ast.get_docstring(fn) or ""
    skip: set[int] = set()
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            if len(body) == 1:
                return None  # только строка документации
            skip = set(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    kept = [
        ln.rstrip()
        for i, ln in enumerate(lines, fn.lineno)
        if i not in skip and ln.strip() and not ln.strip().startswith("#")
    ]
    if any("\t" in ln for ln in kept):
        return None
    summary = next((s.strip() for s in doc.strip().splitlines() if s.strip()), "")
    return kept, summary[:200]


def _literal(node: ast.expr) -> Any:
    v = ast.literal_eval(node)
    _check_value(v)
    return v


def _literal_call(node: ast.expr, names: set[str]) -> tuple[str, tuple, tuple] | None:
    """`f(1, [2])` → ("f", (1, [2]), ()) при литеральных аргументах; иначе None."""
    if not isinstance(node, ast.Call):
        return None
    f = node.func
    name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
    if name is None or name not in names:
        return None
    try:
        args = tuple(_literal(a) for a in node.args)
        kwargs = tuple((k.arg, _literal(k.value)) for k in node.keywords if k.arg)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError, Limit, Unsupported):
        return None
    if len(kwargs) != len(node.keywords):
        return None
    return name, args, kwargs


_EXC_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\b")


def doctest_cases(name: str, doc: str, origin: str) -> list[Case]:
    """Доктесты как данные: `DocTestParser` только разбирает текст, ничего не исполняет."""
    out: list[Case] = []
    try:
        examples = doctest.DocTestParser().get_examples(doc)
    except ValueError:
        return out
    for ex in examples:
        try:
            node = ast.parse(ex.source.strip(), mode="eval").body
        except SyntaxError:
            continue
        call = _literal_call(node, {name})
        if call is None or not isinstance(node.func, ast.Name):  # type: ignore[attr-defined]
            continue
        _, args, kwargs = call
        if ex.exc_msg is not None:
            m = _EXC_LINE.match(ex.exc_msg.strip())
            if m:
                out.append(Case(args, Raised(m.group(1)), origin, kwargs))
            continue
        try:
            want = ast.literal_eval(ex.want.strip())
            _check_value(want)
        except (
            ValueError,
            TypeError,
            SyntaxError,
            MemoryError,
            RecursionError,
            Limit,
            Unsupported,
        ):
            continue
        out.append(Case(args, want, origin, kwargs))
    return out


def _imports(tree: ast.Module) -> dict[str, str]:
    """Имя в тестовом файле → модуль (`from a.b import f` → f: a.b; `import a.b as m` → m: a.b)."""
    out: dict[str, str] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            for a in n.names:
                out[a.asname or a.name] = n.module
        elif isinstance(n, ast.Import):
            for a in n.names:
                out[a.asname or a.name] = a.name
    return out


def assert_cases(
    tree: ast.Module, names: set[str], origin: str
) -> list[tuple[str, str | None, Case]]:
    """(имя функции, модуль-подсказка из импортов, случай) из `assert` и `assertEqual`."""
    imports = _imports(tree)
    out: list[tuple[str, str | None, Case]] = []

    def hint(call: ast.Call, name: str) -> str | None:
        f = call.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            return imports.get(f.value.id)
        return imports.get(name)

    def add(call_node: ast.expr, expected: Any, line: int, *, truthy: bool = False) -> None:
        got = _literal_call(call_node, names)
        if got is None:
            return
        name, args, kwargs = got
        out.append(
            (name, hint(call_node, name), Case(args, expected, f"{origin}:{line}", kwargs, truthy))  # type: ignore[arg-type]
        )

    for n in ast.walk(tree):
        if isinstance(n, ast.Assert):
            t = n.test
            if isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.Eq):
                for call_node, other in ((t.left, t.comparators[0]), (t.comparators[0], t.left)):
                    if isinstance(call_node, ast.Call):
                        try:
                            add(call_node, _literal(other), n.lineno)
                        except (
                            ValueError,
                            TypeError,
                            SyntaxError,
                            MemoryError,
                            Limit,
                            Unsupported,
                        ):
                            pass
                        break
            elif isinstance(t, ast.Call):
                add(t, True, n.lineno, truthy=True)
            elif isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not):
                add(t.operand, False, n.lineno, truthy=True)
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            meth = n.func.attr
            if meth in _ASSERT_EQ and len(n.args) >= 2:
                a, b = n.args[0], n.args[1]
                call_node, other = (a, b) if isinstance(a, ast.Call) else (b, a)
                try:
                    add(call_node, _literal(other), n.lineno)
                except (ValueError, TypeError, SyntaxError, MemoryError, Limit, Unsupported):
                    pass
            elif meth in _ASSERT_BOOL and n.args:
                add(n.args[0], _ASSERT_BOOL[meth], n.lineno, truthy=True)
    return out


def _module_name(rel: Path) -> str:
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _matches(module: str, hint: str) -> bool:
    """Модуль функции совпадает с импортом теста (в том числе реэкспорт из пакета)."""
    return module == hint or module.endswith("." + hint) or module.startswith(hint + ".")


def scan(root: Path, include: list[str] | None = None) -> tuple[list[Func], int]:
    """Функции проекта с тестовыми случаями. Возвращает (кандидаты, всего функций просмотрено)."""
    funcs: list[Func] = []
    seen = 0
    tests: list[tuple[Path, ast.Module]] = []
    for path in py_files(root):
        rel = path.relative_to(root)
        tree = _read_tree(path)
        if tree is None:
            continue
        if is_test_file(rel):
            tests.append((rel, tree))
            continue
        if include and not any(str(rel).startswith(p) for p in include):
            continue
        src_lines = path.read_text(encoding="utf-8").splitlines()
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            seen += 1
            if node.name.startswith("_") or node.end_lineno is None:
                continue
            stripped = _strip(node, src_lines)
            if stripped is None:
                continue
            lines, summary = stripped
            if not MIN_LINES <= len(lines) <= MAX_LINES:
                continue
            f = Func(module=str(rel), name=node.name, lines=lines, doc=summary)
            try:
                validate(f.tree())
            except (Unsupported, SyntaxError):
                continue
            f.cases = doctest_cases(node.name, ast.get_docstring(node) or "", f"{rel}:doctest")
            funcs.append(f)

    by_name: dict[str, list[Func]] = defaultdict(list)
    for f in funcs:
        by_name[f.name].append(f)
    names = set(by_name)
    for rel, tree in tests:
        for name, mod_hint, case in assert_cases(tree, names, str(rel)):
            owners = by_name[name]
            if mod_hint:
                owners = [
                    f for f in owners if _matches(_module_name(Path(f.module)), mod_hint)
                ] or (owners if len(owners) == 1 else [])
            if len(owners) == 1:
                owners[0].cases.append(case)
    return funcs, seen
