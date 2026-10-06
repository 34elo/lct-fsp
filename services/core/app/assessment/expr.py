"""Безопасный вычислитель выражений для заданий конструктора (assessment.md §4).

`eval` не используется: выражение разбирается `ast.parse(mode="eval")`, и обходятся только
разрешённые узлы — числа, имена переменных, арифметика, сравнения, `a if c else b` и функции
из белого списка. Атрибуты, индексы, лямбды, строки, вызовы чего-то кроме белого списка — ошибка.
Ограничения от «бомб»: длина выражения, глубина дерева, показатель степени, размер чисел.
"""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable, Mapping

MAX_LEN = 300
MAX_DEPTH = 32
MAX_POW = 64
MAX_ABS = 1e15

Number = int | float


class ExprError(ValueError):
    """Выражение недопустимо или не вычисляется (деление на ноль, слишком большое число)."""


def _round(x: Number, nd: Number = 0) -> Number:
    return round(x, int(nd))


FUNCS: dict[str, Callable[..., Number]] = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": _round,
    "floor": math.floor,
    "ceil": math.ceil,
    "sqrt": math.sqrt,
    "exp": math.exp,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
}
CONSTS: dict[str, float] = {"pi": math.pi, "e": math.e}

_BIN: dict[type, Callable[[Number, Number], Number]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_CMP: dict[type, Callable[[Number, Number], bool]] = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}


def _check(v: object) -> Number:
    if isinstance(v, bool):
        return int(v)
    if not isinstance(v, int | float):
        raise ExprError("результат не число")
    if isinstance(v, float) and not math.isfinite(v):
        raise ExprError("результат не конечен")
    if abs(v) > MAX_ABS:
        raise ExprError("слишком большое число")
    return v


def parse(src: str) -> ast.Expression:
    if not isinstance(src, str) or not src.strip():
        raise ExprError("пустое выражение")
    if len(src) > MAX_LEN:
        raise ExprError(f"выражение длиннее {MAX_LEN} символов")
    try:
        tree = ast.parse(src.strip(), mode="eval")
    except SyntaxError as e:
        raise ExprError(f"синтаксис: {e.msg}") from e
    _validate(tree)
    return tree


_ALLOWED = (
    ast.Expression, ast.Name, ast.Load, ast.UnaryOp, ast.USub, ast.UAdd, ast.Not, ast.BinOp,
    ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.IfExp, *_BIN, *_CMP,
)  # fmt: skip


def _validate(tree: ast.Expression) -> None:
    """Только разрешённые узлы — проверка формы без вычисления (при сохранении спецификации)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            v = node.value
            if not isinstance(v, int | float) or isinstance(v, bool):
                raise ExprError("допустимы только числа")
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCS or node.keywords:
                raise ExprError("недопустимый вызов функции")
        elif not isinstance(node, _ALLOWED):
            raise ExprError(f"недопустимая конструкция: {type(node).__name__}")


def names(src: str) -> set[str]:
    """Имена переменных выражения (без функций и констант)."""
    out: set[str] = set()
    for node in ast.walk(parse(src)):
        if isinstance(node, ast.Name) and node.id not in FUNCS and node.id not in CONSTS:
            out.add(node.id)
    return out


def evaluate(src: str, env: Mapping[str, Number] | None = None) -> Number:
    """Значение выражения над числовыми переменными `env`."""
    env = env or {}
    return _eval(parse(src).body, env, 0)


def _eval(node: ast.AST, env: Mapping[str, Number], depth: int) -> Number:
    if depth > MAX_DEPTH:
        raise ExprError("слишком глубокое выражение")
    d = depth + 1
    match node:
        case ast.Constant(value=v) if isinstance(v, int | float) and not isinstance(v, bool):
            return _check(v)
        case ast.Name(id=name):
            if name in env:
                v = env[name]
                if isinstance(v, str):
                    raise ExprError(f"переменная {name} не число")
                return _check(v)
            if name in CONSTS:
                return CONSTS[name]
            raise ExprError(f"неизвестная переменная {name}")
        case ast.UnaryOp(op=ast.USub(), operand=x):
            return _check(-_eval(x, env, d))
        case ast.UnaryOp(op=ast.UAdd(), operand=x):
            return _eval(x, env, d)
        case ast.UnaryOp(op=ast.Not(), operand=x):
            return int(not _eval(x, env, d))
        case ast.BinOp(left=lhs, op=op, right=rhs) if type(op) in _BIN:
            a, b = _eval(lhs, env, d), _eval(rhs, env, d)
            if isinstance(op, ast.Pow) and (abs(b) > MAX_POW or (a == 0 and b < 0)):
                raise ExprError("недопустимая степень")
            try:
                return _check(_BIN[type(op)](a, b))
            except (ZeroDivisionError, OverflowError) as e:
                raise ExprError(f"не вычисляется: {e}") from e
        case ast.BoolOp(op=op, values=vals):
            res = [_eval(v, env, d) for v in vals]
            return int(all(res)) if isinstance(op, ast.And) else int(any(res))
        case ast.Compare(left=lhs, ops=ops, comparators=rhs) if all(type(o) in _CMP for o in ops):
            cur = _eval(lhs, env, d)
            for o, c in zip(ops, rhs, strict=True):
                nxt = _eval(c, env, d)
                if not _CMP[type(o)](cur, nxt):
                    return 0
                cur = nxt
            return 1
        case ast.IfExp(test=t, body=yes, orelse=no):
            return _eval(yes, env, d) if _eval(t, env, d) else _eval(no, env, d)
        case ast.Call(func=ast.Name(id=fn), args=args, keywords=[]) if fn in FUNCS:
            if not 1 <= len(args) <= 8:
                raise ExprError(f"{fn}: неверное число аргументов")
            vals = [_eval(a, env, d) for a in args]
            try:
                return _check(FUNCS[fn](*vals))
            except (ValueError, TypeError, OverflowError, ZeroDivisionError) as e:
                raise ExprError(f"{fn}: {e}") from e
    raise ExprError(f"недопустимая конструкция: {type(node).__name__}")
