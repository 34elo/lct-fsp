"""Операторы мутаций (E30-3): одна правка в одной строке тела функции.

Правка делается по позициям узлов AST в тексте строки, поэтому листинг остаётся в авторском
оформлении, а ключ — номер изменённой строки — известен по построению. Мутант обязан
разбираться и проходить белый список песочницы; эквивалентных отсекает проверка тестами.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from app.assessment.mining.extract import parse_function
from app.assessment.mining.sandbox import Unsupported, validate

_CMP_SWAP = {"<": "<=", "<=": "<", ">": ">=", ">=": ">", "==": "!=", "!=": "==",
             "in": "not in", "not in": "in", "is": "is not", "is not": "is"}  # fmt: skip
_CMP_FLIP = {"<": ">", ">": "<", "<=": ">=", ">=": "<="}
_BIN_SWAP = {"+": "-", "-": "+", "*": "+", "//": "/", "/": "//", "%": "//", "**": "*"}
_AUG_SWAP = {"+=": "-=", "-=": "+=", "*=": "+=", "//=": "/=", "/=": "//="}
_BOOL_SWAP = {"and": "or", "or": "and"}
_CALL_SWAP = {"min": "max", "max": "min"}


@dataclass(frozen=True)
class Mutant:
    line: int  # номер строки листинга, с 1
    text: str  # строка после правки
    op: str  # оператор мутации


def _gap(line: str, a: ast.AST, b: ast.AST) -> tuple[int, int] | None:
    """Позиции текста между двумя узлами на одной строке."""
    if a.end_lineno != a.lineno or b.lineno != a.lineno:  # type: ignore[attr-defined]
        return None
    s, e = a.end_col_offset, b.col_offset  # type: ignore[attr-defined]
    return (s, e) if s is not None and e is not None and s <= e <= len(line) else None


def _swap_token(line: str, span: tuple[int, int], table: dict[str, str]) -> list[tuple[str, str]]:
    """Заменить оператор между операндами; скобки и пробелы вокруг остаются как были."""
    s, e = span
    m = re.fullmatch(r"([\s()]*)(.+?)([\s()]*)", line[s:e])
    if m is None:
        return []
    tok = " ".join(m.group(2).split())
    if tok not in table:
        return []
    new = m.group(1) + table[tok] + m.group(3)
    return [(line[:s] + new + line[e:], tok)]


def _edits(line: str, node: ast.AST) -> list[tuple[str, str]]:  # noqa: C901, PLR0912
    """(новая строка, оператор) для узла, целиком лежащего в этой строке."""
    out: list[tuple[str, str]] = []
    match node:
        case ast.Compare(left=left, ops=[_], comparators=[right]):
            span = _gap(line, left, right)
            if span:
                out += [(t, "cmp_boundary") for t, _ in _swap_token(line, span, _CMP_SWAP)]
                out += [(t, "cmp_flip") for t, _ in _swap_token(line, span, _CMP_FLIP)]
        case ast.BinOp(left=left, right=right):
            span = _gap(line, left, right)
            if span:
                out += [(t, "arith") for t, _ in _swap_token(line, span, _BIN_SWAP)]
        case ast.AugAssign(target=t, value=v):
            span = _gap(line, t, v)
            if span:
                out += [(x, "arith") for x, _ in _swap_token(line, span, _AUG_SWAP)]
        case ast.BoolOp(values=[a, b]):
            span = _gap(line, a, b)
            if span:
                out += [(t, "logic") for t, _ in _swap_token(line, span, _BOOL_SWAP)]
        case ast.UnaryOp(op=ast.Not(), operand=v) if v.lineno == node.lineno:
            s, e = node.col_offset, v.col_offset
            if line[s:e].strip() == "not":
                out.append((line[:s] + line[e:], "negate"))
        case ast.Constant(value=bool() as b) if node.end_lineno == node.lineno:
            s, e = node.col_offset, node.end_col_offset
            if line[s:e] == str(b):
                out.append((line[:s] + str(not b) + line[e:], "constant"))
        case ast.Constant(value=int() as k) if node.end_lineno == node.lineno:
            s, e = node.col_offset, node.end_col_offset
            if line[s:e] == str(k) and abs(k) <= 10_000:
                out.append((line[:s] + str(k + 1) + line[e:], "constant"))
                if k > 0:
                    out.append((line[:s] + str(k - 1) + line[e:], "constant"))
        case ast.Call(func=ast.Name(id=name) as f) if name in _CALL_SWAP:
            if f.end_lineno == f.lineno and line[f.col_offset : f.end_col_offset] == name:
                s, e = f.col_offset, f.end_col_offset
                out.append((line[:s] + _CALL_SWAP[name] + line[e:], "call_swap"))
        case ast.Call(func=ast.Name(id="range"), args=args) if args:
            last = args[-1]
            if last.lineno == last.end_lineno == node.lineno:
                s, e = last.col_offset, last.end_col_offset
                seg = line[s:e]
                out.append((line[:s] + f"{seg} - 1" + line[e:], "off_by_one"))
                out.append((line[:s] + f"{seg} + 1" + line[e:], "off_by_one"))
    return out


def mutants(lines: list[str]) -> list[Mutant]:
    """Все годные мутанты функции: тело (не заголовок), одна строка, разбор и белый список."""
    source = "\n".join(lines) + "\n"
    fn = parse_function(source)
    first_body = fn.body[0].lineno
    seen: set[tuple[int, str]] = set()
    out: list[Mutant] = []
    for node in ast.walk(fn):
        ln = getattr(node, "lineno", None)
        if ln is None or ln < first_body:
            continue
        line = lines[ln - 1]
        for text, op in _edits(line, node):
            if text == line or (ln, text) in seen:
                continue
            seen.add((ln, text))
            new = list(lines)
            new[ln - 1] = text
            try:
                validate(parse_function("\n".join(new) + "\n"))
            except (SyntaxError, Unsupported):
                continue
            out.append(Mutant(ln, text, op))
    return out


def apply(lines: list[str], m: Mutant) -> list[str]:
    new = list(lines)
    new[m.line - 1] = m.text
    return new
