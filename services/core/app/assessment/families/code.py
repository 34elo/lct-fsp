"""Кодовые семейства на чтение кода (E22-6): трассировка JS, структуры данных, мутации Python.

Ключ вычисляется на Python напрямую. Для Python-фрагментов `meta["exec"]` (или пара
`exec_ok` / `exec_bug` у мутаций) — код, который исполняет только `make families-check`,
чтобы сверить решатель с исполнением. Код кандидатов не исполняется никогда.
"""

from __future__ import annotations

from random import Random

from fsp_contracts.assessment import SkillType

from app.assessment.families.base import BaseFamily, Item, Kind
from app.assessment.world import World


def _camel(entity: str, suffix: str) -> str:
    head, *rest = entity.split("_")
    return head + "".join(p.title() for p in rest) + suffix


class JsTrace(BaseFamily):
    """Трассировка JS: сортировка по умолчанию (строковая) и сложение со строкой. Ответ — вывод."""

    slug = "js_trace"
    kind = Kind.exact
    skill = "javascript"
    skill_type = SkillType.hard
    level = 2
    knob_bounds = {"n_values": (3, 5)}

    def generate(self, rng: Random, world: World) -> Item:
        var = _camel(world.entities[1], "Ids")
        if rng.random() < 0.5:
            # [].sort() без компаратора сравнивает строки: 100 < 25 < 7
            values = [rng.randint(2, 9), rng.randint(20, 99), rng.randint(100, 199)]
            values += rng.sample(range(10, 99), k=rng.randint(0, 2))
            rng.shuffle(values)
            pos = rng.choice([0, len(values) - 1])
            code = (
                f"const {var} = [{', '.join(map(str, values))}];\n"
                f"{var}.sort();\n"
                f"console.log({var}[{pos}]);"
            )
            key = int(sorted(map(str, values))[pos])
            n = len(values)
        else:
            a, b = rng.randint(2, 40), rng.randint(2, 40)
            if rng.random() < 0.5:
                expr, key = f'"" + {var}A + {var}B', f"{a}{b}"
            else:
                expr, key = f'{var}A + {var}B + ""', str(a + b)
            code = f"const {var}A = {a};\nconst {var}B = {b};\nconsole.log({expr});"
            n = 3
        return Item(
            kind=self.kind,
            stem=f"Что выведет фрагмент из сервиса {world.services[2]}?\n\n{code}",
            key=key,
            time_limit_s=90,
            meta={"knobs": {"n_values": n}},
        )


class StackQueueTrace(BaseFamily):
    """Стек или очередь: какое значение вернёт последнее извлечение. Ответ — число."""

    slug = "stack_queue_trace"
    kind = Kind.exact
    skill = "data_structures"
    skill_type = SkillType.fundamental
    level = 2
    knob_bounds = {"n_ops": (6, 10)}

    def generate(self, rng: Random, world: World) -> Item:
        queue = rng.random() < 0.5
        name = "q" if queue else "s"
        n_ops = rng.randint(6, 10)
        buf: list[int] = []
        lines = (
            ["from collections import deque", f"{name} = deque()"] if queue else [f"{name} = []"]
        )
        last = None
        for i in range(n_ops):
            # последняя операция — извлечение; до неё структура не опустошается
            pop = i == n_ops - 1 or (len(buf) >= 2 and rng.random() < 0.4)
            if pop:
                last = buf.pop(0) if queue else buf.pop()
                lines.append(f"last = {name}.popleft()" if queue else f"last = {name}.pop()")
            else:
                v = rng.randint(1, 99)
                buf.append(v)
                lines.append(f"{name}.append({v})")
        lines.append("print(last)")
        code = "\n".join(lines)
        what = "очередью (deque)" if queue else "стеком (list)"
        return Item(
            kind=self.kind,
            stem=(
                f"Сервис {world.services[0]} обрабатывает id сущностей {world.entities[0]} "
                f"{what}. Что выведет код?\n\n{code}"
            ),
            key=last,
            time_limit_s=90,
            meta={"exec": code, "knobs": {"n_ops": n_ops}},
        )


# Мутации: (номер строки 1-based, заменённая строка). Пример входа подобран так, что каждый
# мутант даёт другой результат — `make families-check` проверяет это исполнением.
_FIND_BUG = [
    {
        "spec": "возвращает, сколько элементов items строго больше limit",
        "code": [
            "def count_{e}(items, limit):",
            "    total = 0",
            "    for i in range(len(items)):",
            "        if items[i] > limit:",
            "            total += 1",
            "    return total",
        ],
        "mutants": [
            (2, "    total = 1"),
            (3, "    for i in range(1, len(items)):"),
            (4, "        if items[i] >= limit:"),
            (5, "            total += items[i]"),
        ],
        "call": "count_{e}",
    },
    {
        "spec": "возвращает наибольший элемент непустого списка values",
        "code": [
            "def max_{e}(values):",
            "    best = values[0]",
            "    for v in values[1:]:",
            "        if v > best:",
            "            best = v",
            "    return best",
        ],
        "mutants": [
            (2, "    best = 0"),
            (3, "    for v in values[2:]:"),
            (4, "        if v < best:"),
            (5, "            best = v + 1"),
        ],
        "call": "max_{e}",
    },
]


def _count_args(rng: Random) -> tuple[list[int], int]:
    limit = rng.randint(3, 9)
    first = limit + rng.randint(1, 5)  # первый элемент больше limit — убивает range(1, …)
    rest = [limit, limit - rng.randint(1, 2), limit + rng.randint(1, 5), rng.randint(0, 2)]
    rng.shuffle(rest)
    return [first, *rest], limit


def _max_args(rng: Random) -> tuple[list[int]]:
    # все отрицательные (убивает best = 0), максимум на позиции 1 (убивает values[2:])
    top = -rng.randint(1, 5)
    rest = [top - rng.randint(1, 9) for _ in range(3)]
    return ([rest[0], top, rest[1], rest[2]],)


class PyFindBug(BaseFamily):
    """Мутация функции на Python: найти строку дефекта. Ответ — список номеров строк."""

    slug = "py_find_bug"
    kind = Kind.find_bug
    skill = "python"
    skill_type = SkillType.hard
    level = 3

    def generate(self, rng: Random, world: World) -> Item:
        t_idx = rng.randrange(len(_FIND_BUG))
        t = _FIND_BUG[t_idx]
        e = world.entities[2]
        ok_lines = [ln.format(e=e) for ln in t["code"]]
        line_no, mutated = rng.choice(t["mutants"])
        bug_lines = list(ok_lines)
        bug_lines[line_no - 1] = mutated
        args = _count_args(rng) if t_idx == 0 else _max_args(rng)
        call = f"print({t['call'].format(e=e)}({', '.join(map(repr, args))}))"
        listing = "\n".join(f"{i:>2} | {ln}" for i, ln in enumerate(bug_lines, 1))
        return Item(
            kind=self.kind,
            stem=(
                f"Функция из сервиса {world.services[1]} {t['spec']}, но в одной строке ошибка. "
                f"Укажите номер строки с дефектом.\n\n{listing}"
            ),
            key=[line_no],
            time_limit_s=150,
            meta={
                "exec_ok": "\n".join(ok_lines) + "\n" + call,
                "exec_bug": "\n".join(bug_lines) + "\n" + call,
            },
        )


FAMILIES = [JsTrace(), StackQueueTrace(), PyFindBug()]
