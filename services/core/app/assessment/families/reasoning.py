"""Семейства на мышление и бизнес (E22-6): выбор из графа сервисов, бизнес-расчёты, оценка затрат.

Имена и масштаб берутся из `World`; числа подобраны так, чтобы ответ считался в уме без дробей.
"""

from __future__ import annotations

from random import Random

from fsp_contracts.assessment import SkillType

from app.assessment.families.base import BaseFamily, Item, Kind
from app.assessment.world import World


def _rub(v: int) -> str:
    return f"{v:_}".replace("_", " ") + " ₽"


class ServiceGraphRootCause(BaseFamily):
    """Граф вызовов сервисов и алерты: какой сервис — первопричина. Ответ — индекс варианта.

    Сломан один сервис; алертят он и все, кто зависит от него транзитивно. Первопричина —
    единственный алертящий сервис, у которого все зависимости здоровы, поэтому ключ однозначен.
    """

    slug = "service_graph_root_cause"
    kind = Kind.choice
    skill = "root_cause_analysis"
    skill_type = SkillType.thinking
    level = 3
    knob_bounds = {"n_services": (5, 5), "n_failing": (2, 5)}

    def generate(self, rng: Random, world: World) -> Item:
        names = list(world.services)
        n = len(names)
        calls: dict[int, set[int]] = {i: set() for i in range(n)}  # вызывающий → вызываемые
        for i in range(1, n):
            calls[rng.randrange(i)].add(i)  # у каждого сервиса, кроме входного, есть вызывающий
        for _ in range(rng.randint(1, 2)):
            a, b = sorted(rng.sample(range(n), 2))
            calls[a].add(b)  # рёбра только «вперёд» — граф ацикличен
        broken = rng.randrange(1, n)
        failing = {broken}
        changed = True
        while changed:
            changed = False
            for a in range(n):
                if a not in failing and calls[a] & failing:
                    failing.add(a)
                    changed = True
        deps = "\n".join(
            f"- {names[a]} → {', '.join(names[b] for b in sorted(calls[a]))}"
            for a in range(n)
            if calls[a]
        )
        alerts = [names[i] for i in sorted(failing)]
        rng.shuffle(alerts)
        options = rng.sample(names, k=n)
        return Item(
            kind=self.kind,
            stem=(
                f"{world.company}: сервисы вызывают друг друга так (A → B: A зависит от B):\n"
                f"{deps}\n\nАлертят ошибками: {', '.join(alerts)}. Остальные здоровы. "
                "Какой сервис, скорее всего, первопричина?"
            ),
            options=options,
            key=options.index(names[broken]),
            time_limit_s=150,
            meta={"knobs": {"n_services": n, "n_failing": len(failing)}},
        )


class UnitEconomics(BaseFamily):
    """Юнит-экономика: окупаемость CAC или LTV. Ответ — число."""

    slug = "unit_economics_calc"
    kind = Kind.exact
    skill = "unit_economics"
    skill_type = SkillType.business
    level = 3

    def generate(self, rng: Random, world: World) -> Item:
        arpu = rng.choice([500, 800, 1000, 1200, 1500, 2000])
        margin = rng.choice([20, 25, 40, 50])
        contrib = arpu * margin // 100  # arpu кратен 100 → целое
        head = (
            f"{world.company}: средний доход с клиента — {_rub(arpu)} "
            f"в месяц, маржинальность — {margin} %."
        )
        if rng.random() < 0.5:
            months = rng.randint(3, 18)
            cac = contrib * months
            stem = (
                f"{head} Привлечение клиента (CAC) стоит {_rub(cac)}. "
                "За сколько месяцев оно окупится?"
            )
            key = months
        else:
            churn = rng.choice([2, 4, 5, 10, 20])
            key = contrib * 100 // churn  # contrib·100 делится на 20 → целое
            stem = (
                f"{head} Каждый месяц уходит {churn} % клиентов. "
                "Чему равен LTV по марже (в рублях)?"
            )
        return Item(kind=self.kind, stem=stem, key=key, time_limit_s=150)


class FunnelRevenue(BaseFamily):
    """Воронка: посетители → корзина → заказ → выручка. Ответ — число (₽)."""

    slug = "funnel_revenue"
    kind = Kind.exact
    skill = "business_metrics"
    skill_type = SkillType.business
    level = 2

    def generate(self, rng: Random, world: World) -> Item:
        visitors = 10_000 * rng.randint(1, 9)
        c1 = rng.choice([10, 20, 25, 40])
        c2 = rng.choice([10, 20, 25, 50])
        aov = rng.choice([1500, 2000, 3500, 4000])
        orders = visitors * c1 * c2 // 10_000
        return Item(
            kind=self.kind,
            stem=(
                f"{world.company}: за неделю сервис {world.services[0]} посетили "
                f"{visitors:_} человек".replace("_", " ")
                + f". До целевого действия доходят {c1} %, из них оплачивают {c2} %. "
                f"Средний чек — {_rub(aov)}. Какова выручка за неделю (₽)?"
            ),
            key=orders * aov,
            time_limit_s=120,
        )


class LlmCostEstimate(BaseFamily):
    """Оценка месячных затрат на LLM-запросы. Ответ — число (порядок)."""

    slug = "llm_cost_estimate"
    kind = Kind.estimate
    skill = "cost_awareness"
    skill_type = SkillType.business
    level = 2

    def generate(self, rng: Random, world: World) -> Item:
        per_day = 10 ** (world.scale - 2) * rng.choice([1, 2, 3, 5])
        tokens = rng.choice([500, 1000, 2000, 4000])
        price = rng.choice([0.1, 0.2, 0.5, 1.0])  # ₽ за 1000 токенов
        key = per_day * 30 * tokens / 1000 * price
        return Item(
            kind=self.kind,
            stem=(
                f"{world.company} добавляет в сервис {world.services[3]} ответы LLM: около "
                f"{per_day:_}".replace("_", " ")
                + f" запросов в сутки, на запрос уходит ~{tokens} токенов, 1000 токенов стоят "
                f"{price} ₽. Оцените затраты за 30 дней (₽, достаточно порядка)."
            ),
            key=key,
            time_limit_s=150,
        )


class CohortRevenue(BaseFamily):
    """Выручка месяца по когортам с удержанием (E36-2). Ответ — число (₽).

    Когорты трёх месяцев, удержание — доля от исходного размера когорты; платят только активные.
    """

    slug = "cohort_revenue"
    kind = Kind.exact
    skill = "business_metrics"
    skill_type = SkillType.business
    level = 4

    def generate(self, rng: Random, world: World) -> Item:
        sizes = [100 * rng.randint(5, 40) for _ in range(3)]  # кратны 100 → целые пользователи
        r2 = rng.choice([40, 50, 60, 70])
        r3 = r2 - rng.choice([10, 20, 30])
        arpu = rng.choice([200, 300, 450, 500, 990])
        active = [sizes[0] * r3 // 100, sizes[1] * r2 // 100, sizes[2]]
        code = (
            f"sizes = {sizes}  # новые пользователи: месяц 1, 2, 3\n"
            f"retention = [1.0, {r2 / 100}, {r3 / 100}]  # доля когорты на 1-й, 2-й, 3-й месяц\n"
            f"arpu = {arpu}\n"
            "active = sum(round(sizes[m] * retention[2 - m]) for m in range(3))\n"
            "print(active * arpu)"
        )
        return Item(
            kind=self.kind,
            stem=(
                f"{world.company}, сервис {world.services[0]}: новые пользователи по месяцам — "
                f"{sizes[0]}, {sizes[1]}, {sizes[2]}. Во второй месяц жизни остаётся {r2} % "
                f"когорты, в третий — {r3} % (от исходного размера). Активный пользователь "
                f"приносит {_rub(arpu)} в месяц. Какова выручка третьего месяца (₽)?"
            ),
            key=sum(active) * arpu,
            time_limit_s=210,
            meta={"exec": code},
        )


# Граничные случаи: (функция с {e}, вызов, верные входы, вход, на котором функция падает)
_EDGE: list[tuple[str, str, list[str], list[str]]] = [
    (
        "def avg_{e}(values):\n    return sum(values) / len(values)",
        "avg_{e}",
        ["[3, 5, 7]", "[0]", "[-2, 2]", "[1.5, 2.5]"],
        ["[]"],
    ),
    (
        "def first_word_{e}(text):\n    return text.split()[0]",
        "first_word_{e}",
        ["'hello world'", "'  padded  '", "'one'", "'a b c'"],
        ["'   '", "''"],
    ),
    (
        "def last_{e}(items, k):\n    return items[len(items) - k]",
        "last_{e}",
        ["[1, 2, 3], 1", "[1, 2, 3], 3", "[5], 1", "[4, 8], 2"],
        ["[1, 2, 3], 0"],
    ),
    (
        "def per_item_{e}(total, count):\n    return total // count",
        "per_item_{e}",
        ["10, 3", "0, 5", "-9, 2", "7, 7"],
        ["5, 0"],
    ),
]


class EdgeCaseInput(BaseFamily):
    """На каком входе функция упадёт: ровно один вариант — граничный случай (E36-2).

    Ответ — индекс варианта. `meta["exec"]` вызывает функцию на всех вариантах и печатает
    индекс единственного упавшего — так `families-check` доказывает однозначность ключа.
    """

    slug = "edge_case_input"
    kind = Kind.choice
    skill = "edge_case_thinking"
    skill_type = SkillType.thinking
    level = 2

    def generate(self, rng: Random, world: World) -> Item:
        src, call, good, bad = rng.choice(_EDGE)
        e = world.entities[1]
        fn = src.format(e=e)
        name = call.format(e=e)
        opts = [*rng.sample(good, k=3), rng.choice(bad)]
        rng.shuffle(opts)
        cases = ", ".join(f"({o},)" for o in opts)  # «[1, 2], 0,» и «[3],» — кортежи аргументов
        code = (
            f"{fn}\n"
            f"cases = [{cases}]\n"
            "failed = []\n"
            "for i, args in enumerate(cases):\n"
            "    try:\n"
            f"        {name}(*args)\n"
            "    except Exception:\n"
            "        failed.append(i)\n"
            "print(failed[0] if len(failed) == 1 else -1)"
        )
        return Item(
            kind=self.kind,
            stem=(
                f"Функция из сервиса {world.services[3]}. На каком входе она упадёт "
                f"с исключением?\n\n{fn}"
            ),
            options=[f"{name}({o})" for o in opts],
            key=next(i for i, o in enumerate(opts) if o in bad),
            time_limit_s=120,
            meta={"exec": code},
        )


FAMILIES = [
    ServiceGraphRootCause(),
    UnitEconomics(),
    FunnelRevenue(),
    LlmCostEstimate(),
    CohortRevenue(),
    EdgeCaseInput(),
]
