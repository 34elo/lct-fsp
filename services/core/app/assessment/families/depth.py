"""Семейства «узко и глубоко» (E36-2, ADR-027 п. 1): закрывают пустые ячейки покрытия
«профессия × грейд × тип навыка» у Backend, Frontend и AI Engineer (`make bank-coverage`).

- `lru_cache_trace` — фундамент (`data_structures`), L4: LRU-кеш, промахи или содержимое;
- `js_event_loop_order` — хард (`javascript`), L4: порядок вывода синхронного кода, микро- и
  макрозадач;
- `edge_case_input` — мышление (`edge_case_thinking`), L2: на каком входе функция упадёт;
- `rice_priority` — бизнес (`prioritization`), L4: какая фича первой по RICE;
- `sjt_ownership` — софт (`ownership`), L4: ситуации ведущего разработчика;
- `release_rollout_order` — опыт (`commercial_experience`), L3: порядок безопасного релиза.

Ключ вычисляется на Python. Где можно, `meta["exec"]` — код, который исполняет только
`make families-check`, чтобы сверить решатель с исполнением. Код кандидатов не исполняется.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from random import Random

from fsp_contracts.assessment import SkillType

from app.assessment.families.base import BaseFamily, Item, Kind
from app.assessment.families.behavior import Scenario, _Order, _Sjt
from app.assessment.world import World

# --- фундамент: LRU-кеш ---


def _lru(ops: list[int], cap: int, *, lru: bool = True) -> tuple[int, list[int]]:
    """Промахи и содержимое кеша (от давнего к свежему). `lru=False` — FIFO, для отсева."""
    cache: OrderedDict[int, bool] = OrderedDict()
    misses = 0
    for k in ops:
        if k in cache:
            if lru:
                cache.move_to_end(k)
            continue
        misses += 1
        cache[k] = True
        if len(cache) > cap:
            cache.popitem(last=False)
    return misses, list(cache)


class LruCacheTrace(BaseFamily):
    """LRU-кеш на `cap` записей и поток запросов: сколько промахов или что осталось в кеше.

    Поток подбирается так, чтобы ответ для LRU отличался от FIFO: без понимания «свежести»
    обращения ответ не угадать.
    """

    slug = "lru_cache_trace"
    kind = Kind.exact
    skill = "data_structures"
    skill_type = SkillType.fundamental
    level = 4
    knob_bounds = {"n_ops": (8, 12), "capacity": (2, 3)}

    def generate(self, rng: Random, world: World) -> Item:
        cap = rng.randint(2, 3)
        n_ops = rng.randint(8, 12)
        ask_misses = rng.random() < 0.5
        ops: list[int] = []
        for _ in range(50):  # детерминированно по rng; почти всегда хватает 1–3 попыток
            ops = [rng.randint(1, cap + 2) for _ in range(n_ops)]
            lru, fifo = _lru(ops, cap), _lru(ops, cap, lru=False)
            if lru[0 if ask_misses else 1] != fifo[0 if ask_misses else 1]:
                break
        misses, left = _lru(ops, cap)
        entity = world.entities[0]
        code = "\n".join(
            [
                "from collections import OrderedDict",
                "cache = OrderedDict()",
                "misses = 0",
                f"for key in {ops}:",
                "    if key in cache:",
                "        cache.move_to_end(key)",
                "    else:",
                "        misses += 1",
                "        cache[key] = True",
                f"        if len(cache) > {cap}:",
                "            cache.popitem(last=False)",
                "print(misses)" if ask_misses else "print(*cache)",
            ]
        )
        question = (
            "Сколько будет промахов?"
            if ask_misses
            else "Какие id останутся в кеше? Ответ — id через пробел, от давнего к свежему."
        )
        return Item(
            kind=self.kind,
            stem=(
                f"Сервис {world.services[0]} кеширует сущности «{entity}» в LRU-кеше на {cap} "
                "записи: при переполнении вытесняется та, к которой дольше всего не обращались. "
                f"Запросы по id идут так: {', '.join(map(str, ops))}. {question}\n\n{code}"
            ),
            key=misses if ask_misses else " ".join(map(str, left)),
            time_limit_s=180,
            meta={"exec": code, "knobs": {"n_ops": n_ops, "capacity": cap}},
        )


# --- хард: событийный цикл JS ---

_LABELS = "ABCDEFGHIJKL"  # до 6 операторов по 2 метки


def _event_loop(stmts: list[tuple[str, list[str]]]) -> list[str]:
    """Порядок вывода: синхронный код, затем микрозадачи до опустошения очереди, затем по одной
    макрозадаче (`setTimeout(…, 0)` в порядке постановки), после каждой — снова все микрозадачи."""
    out: list[str] = []
    micro: deque[list[str]] = (
        deque()
    )  # цепочка .then: следующий шаг встаёт в очередь после текущего
    macro: deque[list[str]] = deque()  # [метка таймера, метка микрозадачи внутри?]
    for kind, labels in stmts:
        if kind == "sync":
            out.append(labels[0])
        elif kind in ("micro", "chain"):
            micro.append(labels)
        else:
            macro.append(labels)

    def drain() -> None:
        while micro:
            head, *rest = micro.popleft()
            out.append(head)
            if rest:
                micro.append(rest)

    drain()
    while macro:
        head, *inner = macro.popleft()
        out.append(head)
        if inner:
            micro.append(inner)
        drain()
    return out


def _js(kind: str, labels: list[str]) -> str:
    log = 'console.log("{}")'.format
    if kind == "sync":
        return f"{log(labels[0])};"
    if kind == "micro":
        return f"queueMicrotask(() => {log(labels[0])});"
    if kind == "chain":
        then = "".join(f"\n  .then(() => {log(x)})" for x in labels)
        return f"Promise.resolve(){then};"
    if len(labels) == 1:
        return f"setTimeout(() => {log(labels[0])}, 0);"
    return (
        f"setTimeout(() => {{\n  {log(labels[0])};\n"
        f"  Promise.resolve().then(() => {log(labels[1])});\n}}, 0);"
    )


class JsEventLoopOrder(BaseFamily):
    """Синхронный код, `queueMicrotask`, цепочки `Promise.then`, `setTimeout(…, 0)`: в каком
    порядке появятся метки. Ответ — порядок вариантов (`order`), частичный балл за близость."""

    slug = "js_event_loop_order"
    kind = Kind.order
    skill = "javascript"
    skill_type = SkillType.hard
    level = 4
    knob_bounds = {"n_stmts": (4, 6)}

    def generate(self, rng: Random, world: World) -> Item:
        n = rng.randint(4, 6)
        kinds = ["sync", "timeout", rng.choice(["micro", "chain"])]
        kinds += [rng.choice(["sync", "micro", "chain", "timeout"]) for _ in range(n - 3)]
        rng.shuffle(kinds)
        labels = iter(_LABELS)
        stmts: list[tuple[str, list[str]]] = []
        for k in kinds:
            size = 2 if k == "chain" or (k == "timeout" and rng.random() < 0.5) else 1
            stmts.append((k, [next(labels) for _ in range(size)]))
        order = _event_loop(stmts)
        shown = sorted(order)  # метки в алфавитном порядке = порядок появления в коде
        code = "\n".join(_js(k, ls) for k, ls in stmts)
        return Item(
            kind=self.kind,
            stem=(
                f"Фрагмент из фронтенда сервиса {world.services[2]} выполняется в браузере. "
                f"Расставьте метки в порядке, в котором они появятся в консоли.\n\n{code}"
            ),
            options=shown,
            key=[shown.index(x) for x in order],
            time_limit_s=180,
            meta={"knobs": {"n_stmts": n}},
        )


# --- мышление: граничные случаи ---

# (код функции с {e}, имя функции с {e}, вход, на котором падает, безопасные входы)
_EDGE = [
    (
        "def avg_{e}(xs):\n    return sum(xs) / len(xs)",
        "avg_{e}",
        "[]",
        ["[0]", "[1, 2]", "[-3, 3]", "[5, 5, 5]"],
    ),
    (
        "def head_{e}(s):\n    return s.split()[0]",
        "head_{e}",
        '"   "',
        ['"a b"', '"x"', '" y"', '"z  "'],
    ),
    (
        "def pages_{e}(total, size):\n    return (total + size - 1) // size",
        "pages_{e}",
        "10, 0",
        ["0, 10", "10, 3", "1, 1", "7, 7"],
    ),
    (
        "def growth_{e}(old, new):\n    return (new - old) / old * 100",
        "growth_{e}",
        "0, 5",
        ["5, 0", "2, 3", "-1, 1", "4, 4"],
    ),
    (
        "def last_{e}(xs):\n    return xs[len(xs) - 1]",
        "last_{e}",
        "[]",
        ["[0]", "[1, 2]", "[None]", "[[]]"],
    ),
]


class EdgeCaseInput(BaseFamily):
    """Функция без проверок и четыре вызова: на каком из них она упадёт с исключением."""

    slug = "edge_case_input"
    kind = Kind.choice
    skill = "edge_case_thinking"
    skill_type = SkillType.thinking
    level = 2

    def generate(self, rng: Random, world: World) -> Item:
        code, fn, bad, good = rng.choice(_EDGE)
        e = world.entities[1]
        code, fn = code.format(e=e), fn.format(e=e)
        calls = [f"{fn}({a})" for a in [bad, *rng.sample(good, k=3)]]
        options = rng.sample(calls, k=len(calls))
        check = "\n".join(
            [
                code,
                f"for i, c in enumerate({options!r}):",
                "    try:",
                "        eval(c)",
                "    except Exception:",
                "        print(i)",
            ]
        )
        return Item(
            kind=self.kind,
            stem=(
                f"Функция из сервиса {world.services[3]} пришла на ревью без проверок входа. "
                f"На каком вызове она упадёт с исключением?\n\n{code}"
            ),
            options=options,
            key=options.index(calls[0]),
            time_limit_s=90,
            meta={"exec": check},
        )


# --- бизнес: приоритизация по RICE ---

_FEATURES = [
    "экспорт в Excel",
    "push-уведомления",
    "поиск с подсказками",
    "тёмная тема",
    "оплата в один клик",
    "реферальная программа",
    "онбординг-тур",
    "история изменений",
]
_IMPACT = [0.25, 0.5, 1, 2, 3]
_CONF = [50, 80, 100]


def _rice(reach: int, impact: float, conf: int, effort: int) -> float:
    return reach * impact * conf / 100 / effort


class RicePriority(BaseFamily):
    """Четыре фичи с охватом, влиянием, уверенностью и трудоёмкостью: какую делать первой по
    RICE = охват × влияние × уверенность / трудоёмкость. Лидер с запасом ≥ 15 % и не совпадает
    с лидером по охвату — ловушка «самая массовая»."""

    slug = "rice_priority"
    kind = Kind.choice
    skill = "prioritization"
    skill_type = SkillType.business
    level = 4

    def generate(self, rng: Random, world: World) -> Item:
        names = rng.sample(_FEATURES, k=4)
        rows: list[tuple[int, float, int, int]] = []
        for _ in range(200):  # детерминированно по rng
            rows = [
                (
                    rng.randrange(500, 20_001, 500),
                    rng.choice(_IMPACT),
                    rng.choice(_CONF),
                    rng.randint(1, 8),
                )
                for _ in names
            ]
            scores = [_rice(*r) for r in rows]
            top = sorted(scores, reverse=True)
            best = scores.index(top[0])
            by_reach = max(range(4), key=lambda i: rows[i][0])
            if top[0] >= 1.15 * top[1] and best != by_reach:
                break
        scores = [_rice(*r) for r in rows]
        best = scores.index(max(scores))
        table = "\n".join(
            f"- {n}: охват {r:_} польз./квартал, влияние {i:g}, уверенность {c} %, "
            f"трудоёмкость {e} чел.-мес.".replace("_", " ")
            for n, (r, i, c, e) in zip(names, rows, strict=True)
        )
        check = "\n".join(
            [
                f"rows = {rows!r}",
                "s = [r * i * c / 100 / e for r, i, c, e in rows]",
                "print(s.index(max(s)))",
            ]
        )
        return Item(
            kind=self.kind,
            stem=(
                f"Команда сервиса {world.services[1]} в компании «{world.company}» выбирает, "
                f"что делать в следующем квартале. Какую фичу взять первой по RICE "
                f"(охват × влияние × уверенность / трудоёмкость)?\n\n{table}"
            ),
            options=names,
            key=best,
            time_limit_s=180,
            meta={"exec": check},
        )


# --- софт: ответственность за результат ---

_OWNERSHIP: list[Scenario] = [
    (
        "Вы ведущий разработчик сервиса {svc}. За день до релиза выяснилось, что интеграция, "
        "которую делали вы, ломает отчёты соседней команды. Ваш руководитель в отпуске.",
        [
            (
                "Сообщить соседней команде и заказчику релиза о проблеме, предложить варианты "
                "(выпустить без интеграции за флагом или сдвинуть срок) и довести выбранный "
                "до конца",
                4,
            ),
            ("Выключить интеграцию флагом и выпустить релиз, а соседям написать после", 3),
            ("Дождаться руководителя: решение о сроке — не ваше", 2),
            ("Выпустить как есть: отчёты — зона соседней команды", 1),
        ],
    ),
    (
        "Задача «ускорить выдачу в {svc}» висит на вас третью неделю: вы упёрлись в медленную "
        "базу, которую сопровождает другая команда, и она не отвечает в трекере.",
        [
            (
                "Написать лиду той команды напрямую с цифрами и конкретной просьбой, а пока "
                "сделать то, что в вашей зоне (кеш, индексы на своей стороне), и обновить статус "
                "задачи",
                4,
            ),
            ("Поднять вопрос на общей встрече и ждать решения", 3),
            ("Перевести задачу в «заблокировано» и взять другую", 2),
            ("Тихо закрыть задачу как «невозможно»", 1),
        ],
    ),
    (
        "После вашего релиза в {svc} ночью был инцидент; его уже починил дежурный из другой "
        "команды. Утром на разборе обсуждают причины.",
        [
            (
                "Признать, что дефект был в вашем изменении, рассказать, как он прошёл проверки, "
                "и взять на себя задачи, чтобы такое ловилось до релиза",
                4,
            ),
            ("Поблагодарить дежурного и быстро исправить дефект", 3),
            ("Объяснить, что тесты были зелёными, и предложить усилить ревью", 2),
            ("Промолчать: инцидент уже закрыт", 1),
        ],
    ),
]


class SjtOwnership(_Sjt):
    slug = "sjt_ownership"
    skill = "ownership"
    skill_type = SkillType.soft
    level = 4
    bank = _OWNERSHIP


# --- опыт: безопасный релиз ---

_RELEASE = [
    "Согласовать окно релиза и предупредить поддержку",
    "Применить обратно совместимую миграцию БД (добавить новые колонки, старые не трогать)",
    "Выкатить новую версию {svc} на небольшую долю трафика (канареечный релиз)",
    "Сравнить ошибки и задержки канарейки с текущей версией",
    "Расширить выкладку {svc} на весь трафик",
    "После стабилизации удалить старые колонки и код совместимости",
    "Написать итог в канал релизов и закрыть задачу",
]


class ReleaseRolloutOrder(_Order):
    slug = "release_rollout_order"
    skill = "commercial_experience"
    skill_type = SkillType.experience
    level = 3
    steps = _RELEASE
    min_steps = 4
    prompt = (
        "В компании «{company}» вы выпускаете версию сервиса {svc} с изменением схемы БД "
        "без простоя. Расставьте шаги в правильном порядке."
    )


FAMILIES = [
    LruCacheTrace(),
    JsEventLoopOrder(),
    EdgeCaseInput(),
    RicePriority(),
    SjtOwnership(),
    ReleaseRolloutOrder(),
]
