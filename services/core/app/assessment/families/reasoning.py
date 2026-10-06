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


FAMILIES = [ServiceGraphRootCause(), UnitEconomics(), FunnelRevenue(), LlmCostEstimate()]
