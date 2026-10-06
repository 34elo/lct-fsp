"""Семейства-спецификации из конструктора (assessment.md §4, E30-1): интерпретаторы по `kind`.

Спецификация — JSON формы конструктора (`families.spec`). Варианты получаются из сида:
- `params` — переменные: диапазон `{min, max, step}` или список `values`;
- `derived` — вычисляемые переменные: выражения безопасного вычислителя (`expr.py`), по порядку;
- шаблоны текста: `{{имя}}` — переменная или имя из мира (`company`, `service`, `service2`,
  `entity`, `table`, `metric`), `{{= выражение}}` — значение выражения. Одинарные фигурные скобки
  остаются как есть (код в `find_bug`).

Ключ по `kind`: `exact` / `estimate` — выражение `answer`; `choice` — `correct` (индекс в порядке
автора, варианты перемешиваются); `find_bug` — `bug_lines` (с 1); `order` — шаги автора в верном
порядке; `sjt` — `score` у действий (больше — эффективнее); `open` — `rubric` (в θ не идёт).
Код из спецификации не исполняется никогда.
"""

from __future__ import annotations

import math
import re
from random import Random
from typing import TYPE_CHECKING, Any

from fsp_contracts.assessment import SkillType
from pydantic import BaseModel, Field, field_validator, model_validator

from app.assessment import expr
from app.assessment.families.base import SCORERS, Item, Kind

if TYPE_CHECKING:
    from app.assessment.world import World

NAME = r"[a-z_][a-z0-9_]{0,30}"
_VAR = re.compile(r"\{\{\s*(" + NAME + r")\s*\}\}")
_EXPR = re.compile(r"\{\{=\s*(.+?)\s*\}\}")
WORLD_NAMES = ("company", "service", "service2", "entity", "table", "metric")
MAX_RANGE_VALUES = 100_000


class SpecError(ValueError):
    """Спецификация не порождает корректный вариант."""


class Param(BaseModel):
    min: float | None = None
    max: float | None = None
    step: float | None = None
    values: list[float | str] | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def _shape(self) -> Param:
        if self.values is not None:
            if self.min is not None or self.max is not None:
                raise ValueError("либо values, либо min/max")
            return self
        if self.min is None or self.max is None or self.min > self.max:
            raise ValueError("нужны min ≤ max или values")
        step = self.step if self.step is not None else 1.0
        if step <= 0 or (self.max - self.min) / step > MAX_RANGE_VALUES:
            raise ValueError("шаг должен быть > 0 и давать не больше 100000 значений")
        return self

    def draw(self, rng: Random) -> float | int | str:
        if self.values is not None:
            return _num(rng.choice(self.values))
        step = self.step if self.step is not None else 1.0
        k = rng.randint(0, int(math.floor((self.max - self.min) / step + 1e-9)))  # type: ignore[operator]
        return _num(round(self.min + k * step, 10))  # type: ignore[operator]


class SjtAction(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    score: float | None = None  # оценка эффективности; None — ключ даст черновик LLM


class FamilySpec(BaseModel):
    """Форма конструктора. Поля ключа необязательны: без них нужен черновик LLM (E30-1)."""

    title: str = Field(min_length=3, max_length=120)
    kind: Kind
    skill: str = Field(min_length=1, max_length=80)
    level: int = Field(ge=1, le=5)
    time_limit_s: int = Field(default=120, ge=20, le=1800)
    stem: str = Field(min_length=10, max_length=4000)
    params: dict[str, Param] = Field(default_factory=dict, max_length=10)
    derived: dict[str, str] = Field(default_factory=dict, max_length=10)
    answer: str | None = Field(default=None, max_length=expr.MAX_LEN)  # exact, estimate
    precision: int = Field(default=2, ge=0, le=6)  # exact: округление ответа
    options: list[str] | None = Field(default=None, min_length=2, max_length=8)  # choice
    correct: int | None = Field(default=None, ge=0)  # choice
    lines: list[str] | None = Field(default=None, min_length=2, max_length=60)  # find_bug
    bug_lines: list[int] | None = Field(default=None, min_length=1, max_length=10)
    steps: list[str] | None = Field(default=None, min_length=3, max_length=10)  # order
    actions: list[SjtAction] | None = Field(default=None, min_length=3, max_length=8)  # sjt
    rubric: list[str] | None = Field(default=None, min_length=1, max_length=10)  # open

    @field_validator("params", "derived")
    @classmethod
    def _names(cls, v: dict) -> dict:
        for k in v:
            if not re.fullmatch(NAME, k) or k in WORLD_NAMES or k in expr.FUNCS:
                raise ValueError(f"недопустимое имя переменной {k!r}")
        return v

    @model_validator(mode="after")
    def _by_kind(self) -> FamilySpec:
        need = {
            Kind.exact: "answer",
            Kind.estimate: "answer",
            Kind.choice: "options",
            Kind.find_bug: "lines",
            Kind.order: "steps",
            Kind.sjt: "actions",
        }.get(self.kind)
        if need and getattr(self, need) is None:
            raise ValueError(f"для kind={self.kind.value} нужно поле {need}")
        if self.kind == Kind.choice and self.correct is not None:
            if self.correct >= len(self.options or []):
                raise ValueError("correct вне вариантов")
        if self.kind == Kind.find_bug and self.bug_lines is not None:
            n = len(self.lines or [])
            if any(not 1 <= x <= n for x in self.bug_lines):
                raise ValueError("bug_lines вне строк кода")
        for name, src in self.derived.items():
            try:
                expr.parse(src)
            except expr.ExprError as e:
                raise ValueError(f"derived.{name}: {e}") from e
        if self.answer is not None:
            try:
                expr.parse(self.answer)
            except expr.ExprError as e:
                raise ValueError(f"answer: {e}") from e
        return self

    def missing_key(self) -> list[str]:
        """Каких частей ключа нет (их может дать только черновик LLM)."""
        if self.kind == Kind.choice and self.correct is None:
            return ["correct"]
        if self.kind == Kind.find_bug and self.bug_lines is None:
            return ["bug_lines"]
        if self.kind == Kind.sjt and any(a.score is None for a in self.actions or []):
            return ["actions.score"]
        if self.kind == Kind.open and not self.rubric:
            return ["rubric"]
        return []


def _num(v: Any) -> Any:
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _fmt(v: Any) -> str:
    v = _num(v)
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def variables(spec: FamilySpec, rng: Random, world: World) -> dict[str, Any]:
    env: dict[str, Any] = {
        "company": world.company,
        "service": world.services[0],
        "service2": world.services[1],
        "entity": world.entities[0],
        "table": world.tables[0],
        "metric": world.metrics[0],
    }
    for name, p in spec.params.items():
        env[name] = p.draw(rng)
    nums = {k: v for k, v in env.items() if not isinstance(v, str)}
    for name, src in spec.derived.items():
        try:
            nums[name] = env[name] = _num(expr.evaluate(src, nums))
        except expr.ExprError as e:
            raise SpecError(f"derived.{name}: {e}") from e
    return env


def render(tpl: str, env: dict[str, Any]) -> str:
    nums = {k: v for k, v in env.items() if not isinstance(v, str)}

    def _e(m: re.Match) -> str:
        try:
            return _fmt(expr.evaluate(m.group(1), nums))
        except expr.ExprError as e:
            raise SpecError(f"шаблон {{{{= {m.group(1)}}}}}: {e}") from e

    def _v(m: re.Match) -> str:
        if m.group(1) not in env:
            raise SpecError(f"неизвестная переменная {{{{{m.group(1)}}}}}")
        return _fmt(env[m.group(1)])

    return _VAR.sub(_v, _EXPR.sub(_e, tpl))


def score_open(rubric: list[str], answer: Any) -> float:
    """Доля выполненных пунктов рубрики: `answer` — отметки `[bool, …]` или `{"marks": [...]}`."""
    marks = answer.get("marks") if isinstance(answer, dict) else answer
    if not isinstance(marks, list) or not rubric:
        return 0.0
    got = sum(1 for m in marks[: len(rubric)] if m is True)
    return got / len(rubric)


class SpecFamily:
    """Семейство поверх спецификации; реализует протокол `Family`."""

    def __init__(
        self,
        spec: FamilySpec,
        *,
        slug: str,
        skill_type: SkillType | str,
        anchor: bool = False,
    ) -> None:
        self.spec = spec
        self.slug = slug
        self.kind = spec.kind
        self.skill = spec.skill
        self.skill_type = SkillType(skill_type)
        self.level = spec.level
        self.anchor = anchor
        self.knob_bounds: dict[str, tuple[float, float]] = {}

    @classmethod
    def from_row(cls, row: Any) -> SpecFamily:
        """Из строки `families` (`source = spec`): спецификация с действующим ключом."""
        return cls(
            FamilySpec.model_validate((row.spec or {})["form"]),
            slug=row.slug,
            skill_type=row.skill_type,
            anchor=bool(row.anchor),
        )

    def generate(self, rng: Random, world: World) -> Item:
        s = self.spec
        if s.missing_key():
            raise SpecError(f"нет ключа: {', '.join(s.missing_key())}")
        env = variables(s, rng, world)
        stem = render(s.stem, env)
        base = {"kind": s.kind, "time_limit_s": s.time_limit_s}
        nums = {k: v for k, v in env.items() if not isinstance(v, str)}
        match s.kind:
            case Kind.exact | Kind.estimate:
                try:
                    key = expr.evaluate(s.answer or "", nums)
                except expr.ExprError as e:
                    raise SpecError(f"answer: {e}") from e
                key = _num(round(key, s.precision)) if s.kind == Kind.exact else key
                return Item(stem=stem, key=key, **base)
            case Kind.choice:
                opts = [render(o, env) for o in s.options or []]
                order = rng.sample(range(len(opts)), k=len(opts))
                return Item(
                    stem=stem, options=[opts[i] for i in order], key=order.index(s.correct), **base
                )
            case Kind.find_bug:
                code = [render(ln, env) for ln in s.lines or []]
                listing = "\n".join(f"{i:>2} | {ln}" for i, ln in enumerate(code, 1))
                return Item(stem=f"{stem}\n\n{listing}", key=sorted(set(s.bug_lines or [])), **base)
            case Kind.order:
                steps = [render(t, env) for t in s.steps or []]
                shown = rng.sample(range(len(steps)), k=len(steps))
                key = [shown.index(i) for i in range(len(steps))]
                return Item(stem=stem, options=[steps[i] for i in shown], key=key, **base)
            case Kind.sjt:
                acts = [(render(a.text, env), float(a.score or 0.0)) for a in s.actions or []]
                shown = rng.sample(acts, k=len(acts))
                key = sorted(range(len(shown)), key=lambda i: -shown[i][1])
                return Item(
                    stem=stem,
                    options=[t for t, _ in shown],
                    key=key,
                    meta={"ratings": [r for _, r in shown]},
                    **base,
                )
            case Kind.open:
                return Item(stem=stem, key=list(s.rubric or []), **base)
        raise SpecError(f"неизвестный kind {s.kind}")  # pragma: no cover

    def score(self, item: Item, answer: Any) -> float:
        if item.kind == Kind.open:
            return score_open(item.key, answer)
        return SCORERS[item.kind](item.key, answer)
