"""Песочница генерации (E30-3): интерпретатор подмножества Python поверх AST.

Код открытых проектов **не исполняется** интерпретатором CPython: ни `exec`, ни `eval`, ни
импорта модуля. Тело одной функции обходится здесь по белому списку узлов, как вычислитель
`expr.py`, только шире: присваивания, `if`/`for`/`while`, списки, словари, срезы, включения,
рекурсия в саму себя. Значения — только встроенные типы из литералов тестов, вызовы — только
встроенные функции и методы из белого списка. Нет атрибутов, кроме методов из списка, нет
импортов, `global`, `lambda`, `try`, `with`, `yield`, классов, доступа к `__dunder__`.

Ограничения от «бомб»: число шагов, глубина рекурсии, длина последовательностей, размер чисел.
Нарушение белого списка — `Unsupported` (функция не годится для майнинга), превышение лимита —
`Limit`; исключение внутри интерпретируемого кода — результат `Raised(<имя типа>)`.
"""

from __future__ import annotations

import ast
import copy
import math
import operator
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

MAX_STEPS = 50_000
MAX_DEPTH = 40
MAX_SEQ = 10_000
MAX_INT_BITS = 256
MAX_POW = 64


class Unsupported(ValueError):
    """Конструкция вне белого списка: функция не берётся в майнинг."""


class Limit(RuntimeError):
    """Превышен лимит песочницы (шаги, глубина, размер)."""


@dataclass(frozen=True)
class Raised:
    """Интерпретируемый код бросил исключение — это результат, а не ошибка песочницы."""

    name: str

    def __repr__(self) -> str:
        return f"raises {self.name}"


class _Return(Exception):
    def __init__(self, value: Any) -> None:
        self.value = value


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


class _UserError(Exception):
    def __init__(self, name: str) -> None:
        self.name = name


VALUE_TYPES = (int, float, str, bool, type(None), list, tuple, dict, set, range)
_ERRORS = (ArithmeticError, LookupError, ValueError, TypeError, AttributeError)
_RAISABLE = {
    "ValueError",
    "TypeError",
    "IndexError",
    "KeyError",
    "ZeroDivisionError",
    "ArithmeticError",
    "Exception",
}


def _range(*a: int) -> range:
    r = range(*a)
    if len(r) > MAX_SEQ:
        raise Limit("range слишком длинный")
    return r


def _sorted(it: Any, *, reverse: bool = False) -> list:
    return sorted(it, reverse=bool(reverse))


def _pow(a: Any, b: Any, *m: Any) -> Any:
    if isinstance(b, int) and abs(b) > MAX_POW and not m:
        raise Limit("степень слишком большая")
    return pow(a, b, *m)


BUILTINS: dict[str, Callable[..., Any]] = {
    "len": len,
    "range": _range,
    "min": min,
    "max": max,
    "abs": abs,
    "sum": sum,
    "sorted": _sorted,
    "reversed": lambda x: list(reversed(x)),
    "enumerate": lambda x, start=0: list(enumerate(x, start)),
    "zip": lambda *xs: list(zip(*xs, strict=False)),
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "list": list,
    "tuple": tuple,
    "set": set,
    "dict": dict,
    "any": any,
    "all": all,
    "round": round,
    "divmod": divmod,
    "ord": ord,
    "chr": chr,
    "pow": _pow,
    "isinstance": isinstance,
}
# Типы для isinstance — имена из BUILTINS тоже значения (int, str, …)
_TYPE_NAMES = {"int": int, "float": float, "str": str, "bool": bool, "list": list,
               "tuple": tuple, "set": set, "dict": dict}  # fmt: skip

METHODS: dict[type, frozenset[str]] = {
    list: frozenset("append pop insert extend index count copy reverse sort remove clear".split()),
    str: frozenset(
        "lower upper strip lstrip rstrip split join replace startswith endswith find rfind "
        "count index isdigit isalpha isalnum isspace isupper islower title capitalize "
        "zfill swapcase".split()
    ),
    dict: frozenset("get keys values items setdefault pop copy update".split()),
    set: frozenset("add discard remove union intersection difference copy pop".split()),
    tuple: frozenset("index count".split()),
}

_BIN: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: _pow,
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
    ast.BitXor: operator.xor,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
}
_CMP: dict[type, Callable[[Any, Any], bool]] = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}
_UNARY: dict[type, Callable[[Any], Any]] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Not: operator.not_,
    ast.Invert: operator.invert,
}


_VIEWS = (type({}.keys()), type({}.values()), type({}.items()))


def _check_value(v: Any) -> Any:
    if isinstance(v, _VIEWS):
        v = list(v)  # представления словаря — как список (порядок вставки сохраняется)
    if isinstance(v, bool | float | type(None)):
        return v
    if isinstance(v, int):
        if v.bit_length() > MAX_INT_BITS:
            raise Limit("число слишком большое")
        return v
    if isinstance(v, str | list | tuple | dict | set | range):
        if len(v) > MAX_SEQ:
            raise Limit("последовательность слишком длинная")
        return v
    raise Unsupported(f"значение типа {type(v).__name__}")


def _guard_mul(a: Any, b: Any) -> None:
    for seq, k in ((a, b), (b, a)):
        if isinstance(seq, str | list | tuple) and isinstance(k, int) and len(seq) * k > MAX_SEQ:
            raise Limit("повторение последовательности слишком длинное")
    if isinstance(a, int) and isinstance(b, int) and a.bit_length() + b.bit_length() > MAX_INT_BITS:
        raise Limit("произведение слишком большое")


def _guard_shift(a: Any, b: Any) -> None:
    if isinstance(b, int) and b > MAX_INT_BITS:
        raise Limit("сдвиг слишком большой")


def _guard_method(obj: Any, attr: str, args: list[Any]) -> None:
    """Методы, которые могут раздуть строку до проверки результата."""
    if attr == "zfill" and args and isinstance(args[0], int) and args[0] > MAX_SEQ:
        raise Limit("zfill слишком длинный")
    if attr == "replace" and len(args) >= 2 and isinstance(args[1], str):
        if len(obj) * (len(args[1]) + 1) > MAX_SEQ * 4:
            raise Limit("replace слишком длинный")
    if attr == "join" and args:
        try:
            total = sum(len(x) for x in args[0]) + len(obj) * len(args[0])
        except TypeError:
            return
        if total > MAX_SEQ * 4:
            raise Limit("join слишком длинный")


class Interpreter:
    """Одна функция верхнего уровня; вызывается `call(args)`."""

    def __init__(self, fn: ast.FunctionDef) -> None:
        validate(fn)
        self.fn = fn
        self.steps = 0
        self.depth = 0

    # --- вызов ---------------------------------------------------------------------------------

    def call(self, args: Sequence[Any], kwargs: dict[str, Any] | None = None) -> Any:
        """Результат функции или `Raised`; `Limit` / `Unsupported` пробрасываются.

        Аргументы копируются: мутирующая функция не портит литералы теста для следующего вызова.
        """
        self.steps = 0
        self.depth = 0
        try:
            return self._invoke(copy.deepcopy(list(args)), copy.deepcopy(kwargs or {}))
        except _UserError as e:
            return Raised(e.name)
        except (Limit, Unsupported):
            raise
        except _ERRORS as e:  # страховка: ошибка встроенной функции вне `_safe`
            return Raised(type(e).__name__)
        except RecursionError as e:
            raise Limit("рекурсия слишком глубокая") from e

    def _invoke(self, args: list[Any], kwargs: dict[str, Any]) -> Any:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise Limit("рекурсия слишком глубокая")
        try:
            env = self._bind(args, kwargs)
            try:
                self._block(self.fn.body, env)
            except _Return as r:
                return r.value
            return None
        finally:
            self.depth -= 1

    def _bind(self, args: list[Any], kwargs: dict[str, Any]) -> dict[str, Any]:
        a = self.fn.args
        names = [p.arg for p in a.args]
        if len(args) > len(names):
            raise _UserError("TypeError")
        env: dict[str, Any] = dict(zip(names, args, strict=False))
        defaults = a.defaults
        for name, d in zip(names[len(names) - len(defaults) :], defaults, strict=True):
            env.setdefault(name, self._expr(d, {}))
        for k, v in kwargs.items():
            if k not in names:
                raise _UserError("TypeError")
            env[k] = v
        if any(n not in env for n in names):
            raise _UserError("TypeError")
        return env

    def _tick(self) -> None:
        self.steps += 1
        if self.steps > MAX_STEPS:
            raise Limit("слишком много шагов")

    # --- операторы -----------------------------------------------------------------------------

    def _block(self, body: list[ast.stmt], env: dict[str, Any]) -> None:
        for st in body:
            self._stmt(st, env)

    def _stmt(self, st: ast.stmt, env: dict[str, Any]) -> None:  # noqa: C901, PLR0912
        self._tick()
        match st:
            case ast.Expr(value=ast.Constant(value=str())):
                return  # строка документации
            case ast.Expr(value=v):
                self._expr(v, env)
            case ast.Assign(targets=targets, value=v):
                val = self._expr(v, env)
                for t in targets:
                    self._assign(t, val, env)
            case ast.AnnAssign(target=t, value=v) if v is not None:
                self._assign(t, self._expr(v, env), env)
            case ast.AugAssign(target=t, op=op, value=v):
                cur = self._expr(_load(t), env)
                self._assign(t, self._binop(op, cur, self._expr(v, env)), env)
            case ast.If(test=test, body=body, orelse=orelse):
                self._block(body if self._expr(test, env) else orelse, env)
            case ast.For(target=t, iter=it, body=body, orelse=orelse):
                seq = self._expr(it, env)
                broke = False
                for x in self._safe(list, seq):
                    self._tick()
                    self._assign(t, x, env)
                    try:
                        self._block(body, env)
                    except _Break:
                        broke = True
                        break
                    except _Continue:
                        continue
                if not broke:
                    self._block(orelse, env)
            case ast.While(test=test, body=body, orelse=orelse):
                broke = False
                while self._expr(test, env):
                    self._tick()
                    try:
                        self._block(body, env)
                    except _Break:
                        broke = True
                        break
                    except _Continue:
                        continue
                if not broke:
                    self._block(orelse, env)
            case ast.Return(value=v):
                raise _Return(self._expr(v, env) if v is not None else None)
            case ast.Break():
                raise _Break
            case ast.Continue():
                raise _Continue
            case ast.Pass():
                return
            case ast.Raise(exc=exc):
                raise _UserError(_raised_name(exc))
            case ast.Assert(test=test):
                if not self._expr(test, env):
                    raise _UserError("AssertionError")
            case _:
                raise Unsupported(type(st).__name__)

    def _assign(self, t: ast.expr, val: Any, env: dict[str, Any]) -> None:
        match t:
            case ast.Name(id=name):
                env[name] = val
            case ast.Tuple(elts=elts) | ast.List(elts=elts):
                vals = self._safe(list, val)
                if len(vals) != len(elts):
                    raise _UserError("ValueError")
                for e, v in zip(elts, vals, strict=True):
                    self._assign(e, v, env)
            case ast.Subscript(value=obj, slice=sl):
                target = self._expr(obj, env)
                if not isinstance(target, list | dict):
                    raise _UserError("TypeError")
                key = self._slice(sl, env)
                try:
                    target[key] = val
                except _ERRORS as e:
                    raise _UserError(type(e).__name__) from None
                _check_value(target)
            case _:
                raise Unsupported(f"присваивание в {type(t).__name__}")

    # --- выражения -----------------------------------------------------------------------------

    def _expr(self, node: ast.expr, env: dict[str, Any]) -> Any:  # noqa: C901, PLR0911, PLR0912
        self._tick()
        match node:
            case ast.Constant(value=v):
                return _check_value(v)
            case ast.Name(id=name):
                if name in env:
                    return env[name]
                if name in _TYPE_NAMES:
                    return _TYPE_NAMES[name]
                raise _UserError("NameError")
            case ast.BinOp(left=a, op=op, right=b):
                return self._binop(op, self._expr(a, env), self._expr(b, env))
            case ast.UnaryOp(op=op, operand=v):
                return self._safe(_UNARY[type(op)], self._expr(v, env))
            case ast.BoolOp(op=op, values=values):
                res: Any = None
                for v in values:
                    res = self._expr(v, env)
                    if isinstance(op, ast.And) and not res:
                        return res
                    if isinstance(op, ast.Or) and res:
                        return res
                return res
            case ast.Compare(left=left, ops=ops, comparators=comps):
                a = self._expr(left, env)
                for op, c in zip(ops, comps, strict=True):
                    b = self._expr(c, env)
                    if not self._safe(_CMP[type(op)], a, b):
                        return False
                    a = b
                return True
            case ast.IfExp(test=test, body=body, orelse=orelse):
                return self._expr(body if self._expr(test, env) else orelse, env)
            case ast.Subscript(value=obj, slice=sl):
                target = self._expr(obj, env)
                key = self._slice(sl, env)
                return self._safe(operator.getitem, target, key)
            case ast.List(elts=elts):
                return _check_value([self._expr(e, env) for e in elts])
            case ast.Tuple(elts=elts):
                return tuple(self._expr(e, env) for e in elts)
            case ast.Set(elts=elts):
                return self._safe(set, [self._expr(e, env) for e in elts])
            case ast.Dict(keys=keys, values=values):
                if any(k is None for k in keys):
                    raise Unsupported("распаковка словаря")
                return self._safe(
                    dict,
                    [
                        (self._expr(k, env), self._expr(v, env))
                        for k, v in zip(keys, values, strict=True)
                    ],  # type: ignore[arg-type]
                )
            case (
                ast.ListComp(elt=elt, generators=gens) | ast.GeneratorExp(elt=elt, generators=gens)
            ):
                return _check_value(self._comp(elt, None, gens, env))
            case ast.SetComp(elt=elt, generators=gens):
                return self._safe(set, self._comp(elt, None, gens, env))
            case ast.DictComp(key=k, value=v, generators=gens):
                return self._safe(dict, self._comp(k, v, gens, env))
            case ast.JoinedStr(values=parts):
                return _check_value("".join(self._fstr(p, env) for p in parts))
            case ast.Call():
                return self._call(node, env)
            case _:
                raise Unsupported(type(node).__name__)

    def _fstr(self, part: ast.expr, env: dict[str, Any]) -> str:
        if isinstance(part, ast.Constant):
            return str(part.value)
        if (
            isinstance(part, ast.FormattedValue)
            and part.format_spec is None
            and part.conversion == -1
        ):
            return str(self._expr(part.value, env))
        raise Unsupported("f-строка с форматом")

    def _comp(
        self,
        elt: ast.expr,
        val: ast.expr | None,
        gens: list[ast.comprehension],
        env: dict[str, Any],
    ) -> list[Any]:
        out: list[Any] = []
        local = dict(env)  # переменные включения не текут наружу

        def walk(i: int) -> None:
            if i == len(gens):
                item = self._expr(elt, local)
                out.append((item, self._expr(val, local)) if val is not None else item)
                if len(out) > MAX_SEQ:
                    raise Limit("включение слишком длинное")
                return
            g = gens[i]
            if g.is_async:
                raise Unsupported("async")
            for x in self._safe(list, self._expr(g.iter, local)):
                self._tick()
                self._assign(g.target, x, local)
                if all(self._expr(c, local) for c in g.ifs):
                    walk(i + 1)

        walk(0)
        return out

    def _slice(self, sl: ast.expr, env: dict[str, Any]) -> Any:
        if isinstance(sl, ast.Slice):
            parts = (sl.lower, sl.upper, sl.step)
            return slice(*(self._expr(p, env) if p is not None else None for p in parts))
        return self._expr(sl, env)

    def _binop(self, op: ast.operator, a: Any, b: Any) -> Any:
        if isinstance(op, ast.Mult):
            _guard_mul(a, b)
        if isinstance(op, ast.LShift):
            _guard_shift(a, b)
        fn = _BIN.get(type(op))
        if fn is None:
            raise Unsupported(type(op).__name__)
        return self._safe(fn, a, b)

    def _safe(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            return _check_value(fn(*args, **kwargs))
        except (Limit, Unsupported, _UserError):
            raise
        except _ERRORS as e:
            raise _UserError(type(e).__name__) from None

    def _call(self, node: ast.Call, env: dict[str, Any]) -> Any:
        if any(isinstance(a, ast.Starred) for a in node.args):
            raise Unsupported("*args")
        if any(k.arg is None for k in node.keywords):
            raise Unsupported("**kwargs")
        args = [self._expr(a, env) for a in node.args]
        kwargs = {k.arg: self._expr(k.value, env) for k in node.keywords if k.arg}
        f = node.func
        if isinstance(f, ast.Name):
            if f.id == self.fn.name and f.id not in env:
                return self._invoke(args, kwargs)
            if f.id in BUILTINS and f.id not in env:
                if kwargs and set(kwargs) - {"reverse", "start", "default"}:
                    raise Unsupported(f"именованные аргументы {f.id}")
                return self._safe(BUILTINS[f.id], *args, **kwargs)
            raise Unsupported(f"вызов {f.id}")
        if isinstance(f, ast.Attribute):
            obj = self._expr(f.value, env)
            allowed = METHODS.get(type(obj), frozenset())
            if f.attr not in allowed:
                raise Unsupported(f"метод {type(obj).__name__}.{f.attr}")
            if kwargs and set(kwargs) != {"reverse"}:
                raise Unsupported("именованные аргументы метода")
            _guard_method(obj, f.attr, args)
            res = self._safe(getattr(obj, f.attr), *args, **kwargs)
            _check_value(obj)  # append/extend могли раздуть объект
            return res
        raise Unsupported("вызов выражения")


def _load(t: ast.expr) -> ast.expr:
    """Цель присваивания `x += …` как выражение чтения."""
    if isinstance(t, ast.Name):
        return ast.Name(id=t.id, ctx=ast.Load())
    if isinstance(t, ast.Subscript):
        return ast.Subscript(value=t.value, slice=t.slice, ctx=ast.Load())
    raise Unsupported(f"+= в {type(t).__name__}")


def _raised_name(exc: ast.expr | None) -> str:
    match exc:
        case ast.Call(func=ast.Name(id=name)) | ast.Name(id=name) if name in _RAISABLE:
            return name
    raise Unsupported("raise вне белого списка")


_ALLOWED_NODES: tuple[type, ...] = (
    ast.FunctionDef, ast.arguments, ast.arg, ast.Expr, ast.Assign, ast.AnnAssign, ast.AugAssign,
    ast.If, ast.For, ast.While, ast.Return, ast.Break, ast.Continue, ast.Pass, ast.Raise,
    ast.Assert, ast.Constant, ast.Name, ast.Load, ast.Store, ast.BinOp, ast.UnaryOp, ast.BoolOp,
    ast.Compare, ast.IfExp, ast.Subscript, ast.Slice, ast.List, ast.Tuple, ast.Set, ast.Dict,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.comprehension, ast.Call,
    ast.keyword, ast.Attribute, ast.JoinedStr, ast.FormattedValue, ast.operator, ast.unaryop,
    ast.boolop, ast.cmpop,
)  # fmt: skip


def validate(fn: ast.FunctionDef) -> None:
    """Статическая проверка белого списка до любого обхода: иначе `Unsupported`."""
    a = fn.args
    if fn.decorator_list or a.vararg or a.kwarg or a.kwonlyargs or a.posonlyargs:
        raise Unsupported("сигнатура вне белого списка")
    for n in ast.walk(fn):
        if not isinstance(n, _ALLOWED_NODES):
            raise Unsupported(type(n).__name__)
        if n is not fn and isinstance(n, ast.FunctionDef):
            raise Unsupported("вложенная функция")
        if isinstance(n, ast.Attribute):
            if n.attr.startswith("_") or not isinstance(n.ctx, ast.Load):
                raise Unsupported(f"атрибут {n.attr}")
            if not any(n.attr in ms for ms in METHODS.values()):
                raise Unsupported(f"атрибут {n.attr}")
        if isinstance(n, ast.Name) and n.id.startswith("__"):
            raise Unsupported(f"имя {n.id}")
        if isinstance(n, ast.Call):
            f = n.func
            known = (
                f.id in BUILTINS or f.id in _RAISABLE or f.id == fn.name
                if isinstance(f, ast.Name)
                else True
            )
            if not known:
                raise Unsupported(f"вызов {getattr(f, 'id', '?')}")
            if not isinstance(f, ast.Name | ast.Attribute):
                raise Unsupported("вызов выражения")


def same(a: Any, b: Any) -> bool:
    """Сравнение результатов: числа с плавающей точкой — с допуском."""
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    if isinstance(a, list | tuple) and isinstance(b, list | tuple):
        return type(a) is type(b) and len(a) == len(b) and all(map(same, a, b))
    try:
        return bool(a == b) and (type(a) is type(b) or isinstance(a, int) and isinstance(b, int))
    except Exception:  # noqa: BLE001 - сравнение экзотики не должно ронять майнинг
        return False


def run(fn: ast.FunctionDef, args: Sequence[Any]) -> Any:
    """Удобная обёртка: новый интерпретатор, один вызов."""
    return Interpreter(fn).call(args)
