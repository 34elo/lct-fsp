"""Цепочки-инциденты: метрики → логи → код → архитектура → ответ в одном задании.

Задание `kind = chain`: общий рассказ об инциденте и пять шагов-`Item` обычных типов
(`choice`, `find_bug`, `exact`, `estimate`). Ответ — список ответов по шагам, балл — средний балл
шагов, поэтому цепочка входит в θ и калибруется как обычное семейство (один `b` на всю цепочку).

Шаги связаны: следующий опирается на вывод предыдущего, а его артефакт не называет прошлые ответы
(сервис-первопричина в коде и архитектуре — «сервис-первопричина», не имя). Код в шаге «код»
показывает оба подозрительных места, дефект — только в одном, поэтому листинг не выдаёт причину.
Всё строится из полного `World`: граф, метрики, таблицы, нагрузка. Ручки — из `rng`
семейства до обращения к миру. Код варианта не исполняется: это текст для чтения.
"""

from __future__ import annotations

from random import Random

from fsp_contracts.assessment import SkillType

from app.assessment.families.base import BaseFamily, Item, Kind
from app.assessment.families.world_tasks import _APP, _edges_text, _fk_pairs
from app.assessment.world import Metric, World

# Метрики, у которых рост — плохо: инцидент двигает их вверх, остальные — вниз.
_UP_IS_BAD = {"fraud_rate", "churn", "latency_p95", "cost_per_query"}
_DAYS = 7
_INTRO = "Ответьте на шаги по порядку: каждый следующий опирается на вывод предыдущего."


def _fmt(v: float, digits: int) -> str:
    return str(int(v)) if digits == 0 else f"{v:.{digits}f}"


def _digits(m: Metric) -> int:
    if all(float(v).is_integer() for v in m.series):
        return 0
    return max(len(str(v).split(".")[1]) for v in m.series if "." in str(v))


def _shuffled(rng: Random, correct: str, others: list[str]) -> tuple[list[str], int]:
    opts = rng.sample([correct, *others], k=1 + len(others))
    return opts, opts.index(correct)


def _deep_app(world: World) -> list[str]:
    """Прикладные сервисы, которые вызывает другой прикладной: каскад длиннее одного звена."""
    app = [n.name for n in world.nodes if n.kind in _APP]
    return [s for s in app if any(c in app for c in world.callers(s))] or app


def _entries_hit(world: World, src: str) -> int:
    """Сколько входов gateway (прямых зависимостей gateway) задевает отказ или замедление `src`."""
    hit = {src, *world.impacted_by(src)}
    return sum(1 for e in world.deps("gateway") if e in hit)


def _metrics_step(rng: Random, world: World, drop: int) -> Item:
    """Шаг «метрики»: бизнес-метрики за 7 дней, одна сегодня ушла на `drop` % в плохую сторону."""
    # Шаг округления ≤ 2 % значения: иначе выброс тонет в округлении (стоимость 0.09 ₽).
    fine = [
        i for i, m in enumerate(world.kpis) if 10 ** -_digits(m) <= 0.02 * min(m.series[-_DAYS:])
    ]
    m_i = rng.choice(fine or list(range(len(world.kpis))))
    rows = []
    for i, m in enumerate(world.kpis):
        series = list(m.series[-_DAYS:])
        d = _digits(m)
        if i == m_i:
            sign = 1 if m.name in _UP_IS_BAD else -1
            series[-1] = round(series[-1] * (1 + sign * drop / 100), d)
        rows.append(f"- {m.title} ({m.unit}): " + ", ".join(_fmt(v, d) for v in series))
    titles = [m.title for m in world.kpis]
    opts = rng.sample(titles, k=len(titles))
    return Item(
        kind=Kind.choice,
        stem=(
            f"Метрики за последние {_DAYS} дней, последнее значение — сегодня:\n"
            + "\n".join(rows)
            + "\n\nКакая метрика сегодня сигнализирует об инциденте?"
        ),
        options=opts,
        key=opts.index(world.kpis[m_i].title),
        meta={"metric": world.kpis[m_i].name},
    )


# --- цепочка 1: отказ после релиза -------------------------------------------------------------
_REASON = (
    "connection pool exhausted (50/50 in use), waited 3000ms",
    "MemoryError: container OOMKilled, RSS 2.0 GiB of 2.0 GiB limit",
)


def _outage_code(bug: int, ent: str, table: str) -> tuple[list[str], list[int]]:
    """Два места релиза: работа с пулом и кеш страниц. Дефект только в одном (по `bug`)."""
    if bug == 0:  # соединение не возвращается в пул на раннем выходе
        pool = [
            f"def get_{ent}_summary({ent}_id):",
            "    conn = pool.acquire()",
            f'    row = conn.fetch_one("SELECT * FROM {table} WHERE id = %s", {ent}_id)',
            "    if row is None:",
            "        return None",
            "    pool.release(conn)",
            f'    return {{"{ent}": row}}',
        ]
        bad_pool = [5]
    else:
        pool = [
            f"def get_{ent}_summary({ent}_id):",
            "    conn = pool.acquire()",
            "    try:",
            f'        row = conn.fetch_one("SELECT * FROM {table} WHERE id = %s", {ent}_id)',
            "    finally:",
            "        pool.release(conn)",
            f'    return {{"{ent}": row}} if row else None',
        ]
        bad_pool = []
    if bug == 1:  # ключ уникален на каждый запрос, кеш без ограничения — растёт без конца
        cache = [
            "_pages = {}",
            "",
            f"def render_{ent}_page({ent}_id, request_id):",
            f"    key = (request_id, {ent}_id)",
            "    if key not in _pages:",
            f"        _pages[key] = build_page({ent}_id)",
            "    return _pages[key]",
        ]
        bad_cache = [4, 6]
    else:
        cache = [
            "_pages = LRUCache(maxsize=1000, ttl=60)",
            "",
            f"def render_{ent}_page({ent}_id, request_id):",
            f"    key = {ent}_id",
            "    if key not in _pages:",
            f"        _pages[key] = build_page({ent}_id)",
            "    return _pages[key]",
        ]
        bad_cache = []
    lines = [*pool, "", *cache]
    off = len(pool) + 1
    return lines, [*bad_pool, *(off + i for i in bad_cache)]


def _listing(lines: list[str]) -> str:
    return "\n".join(f"{i:>2}  {s}" for i, s in enumerate(lines, start=1))


class IncidentChainOutage(BaseFamily):
    """Ночной отказ после релиза: метрика → логи каскада → дефект в коде → входы → действие."""

    slug = "incident_chain_outage"
    kind = Kind.chain
    skill = "root_cause_analysis"
    skill_type = SkillType.thinking
    level = 4
    # bug: 0 — утечка соединений из пула, 1 — неограниченный кеш (память);
    # noise_error: 1 — шум до инцидента тоже ERROR; drop_pct — отклонение метрики.
    knob_bounds = {"bug": (0, 1), "noise_error": (0, 1), "drop_pct": (25, 40)}

    def generate(self, rng: Random, world: World) -> Item:
        bug, noise_error, drop = rng.randint(0, 1), rng.randint(0, 1), rng.randint(25, 40)

        s_metrics = _metrics_step(rng, world, drop)

        # --- логи: релиз двух сервисов, каскад timeout вверх от первопричины ---
        app = [n.name for n in world.nodes if n.kind in _APP]
        broken = rng.choice(_deep_app(world))
        impacted = world.impacted_by(broken)
        others = [s for s in app if s != broken]
        healthy = [s for s in others if s not in impacted]
        herring = rng.choice(healthy or others)
        h, m0 = rng.randint(0, 22), rng.randint(0, 40)

        def ts(sec: int) -> str:
            return f"{h:02d}:{m0 + sec // 60:02d}:{sec % 60:02d}"

        logs: list[tuple[int, str]] = []
        rel = rng.sample([broken, herring], k=2)
        for k, svc in enumerate(rel):
            sec = rng.randint(0, 9) + 10 * k
            logs.append((sec, f"INFO  deploy: {svc} v2.{rng.randint(1, 40)}"))
        noise = "ERROR {}: 400 invalid field 'qty'" if noise_error else "WARN  {}: slow request"
        logs.append((rng.randint(21, 40), noise.format(herring)))
        t = rng.randint(60, 90)
        logs.append((t, f"ERROR {broken}: {_REASON[bug]}"))
        dist, frontier = {broken: 0}, [broken]
        while frontier:
            nxt = []
            for b in frontier:
                for a in world.callers(b):
                    if a not in dist:
                        dist[a] = dist[b] + 1
                        nxt.append(a)
            for a in nxt:
                t += rng.randint(1, 4)
                dep = next(b for b in world.deps(a) if b in dist and dist[b] < dist[a])
                if a == "gateway":
                    logs.append((t, f"ERROR gateway: 504 upstream {dep} timeout"))
                else:
                    logs.append((t, f"ERROR {a}: call to {dep} failed: timeout after 3000ms"))
            frontier = nxt
        logs.sort(key=lambda x: x[0])
        hit = [x for x in impacted if x != "gateway"]
        pool = list(dict.fromkeys([herring, *hit[:2], *healthy]))
        opts, key = _shuffled(rng, broken, [x for x in pool if x != broken][:3])
        s_logs = Item(
            kind=Kind.choice,
            stem=(
                "Логи за ночь (все сервисы):\n"
                + "\n".join(f"{ts(sec)} {line}" for sec, line in logs)
                + "\n\nКакой сервис — первопричина инцидента?"
            ),
            options=opts,
            key=key,
        )

        # --- код: два места последнего релиза первопричины ---
        # Таблица не совпадает с именем первопричины (`cards`, `courses`): иначе код её выдаёт.
        ents = [e for i, e in enumerate(world.entities) if world.tables[i] != broken]
        ent = rng.choice(ents or list(world.entities))
        lines, bad = _outage_code(bug, ent, world.tables[world.entities.index(ent)])
        s_code = Item(
            kind=Kind.find_bug,
            stem=(
                "Код из последнего релиза сервиса-первопричины (два изменённых места):\n\n"
                f"{_listing(lines)}\n\nОтметьте строки, которые вызвали ошибку из логов."
            ),
            key=bad,
        )

        # --- архитектура: сколько входов gateway отдают ошибки пользователям ---
        s_arch = Item(
            kind=Kind.exact,
            stem=(
                "Пока первопричина не устранена, сколько входов через gateway (сервисов, которые "
                "gateway вызывает напрямую) отдают пользователям ошибки? Ответ — число."
            ),
            key=_entries_hit(world, broken),
        )

        # --- ответ: первое действие ---
        fix = (
            "Откатить релиз сервиса-первопричины, затем возвращать соединение в пул на всех "
            "путях (try/finally)",
            "Откатить релиз сервиса-первопричины, затем убрать request_id из ключа кеша и "
            "ограничить кеш (LRU, TTL)",
        )
        bigger = (
            "Увеличить пул соединений до 200 и перезапустить сервис-первопричину",
            "Вдвое увеличить лимит памяти контейнера сервиса-первопричины",
        )
        opts, key = _shuffled(
            rng,
            fix[bug],
            [
                bigger[bug],
                fix[1 - bug],
                "Поднять таймауты вызовов у вызывающих сервисов до 30 секунд",
            ],
        )
        s_fix = Item(
            kind=Kind.choice,
            stem="Что сделать дежурному в первую очередь?",
            options=opts,
            key=key,
        )

        steps = (s_metrics, s_logs, s_code, s_arch, s_fix)
        return Item(
            kind=self.kind,
            stem=(
                f"Ночной инцидент в компании «{world.company}» ({world.domain_title}). "
                f"{_INTRO}\n\n{_edges_text(world)}"
            ),
            key=[s.key for s in steps],
            time_limit_s=600,
            steps=steps,
            meta={
                "knobs": {"bug": bug, "noise_error": noise_error, "drop_pct": drop},
                "root": broken,
            },
        )


# --- цепочка 2: деградация задержки -----------------------------------------------------------
class IncidentChainLatency(BaseFamily):
    """Медленно после релиза: p95 → журнал БД → код и миграция → нагрузка на БД → исправление.

    `cause = 0` — N+1 запросов в обработчике, `1` — релизная миграция удалила индекс.
    """

    slug = "incident_chain_latency"
    kind = Kind.chain
    skill = "performance_reasoning"
    skill_type = SkillType.thinking
    level = 4
    knob_bounds = {"cause": (0, 1), "rows": (5, 12)}

    def generate(self, rng: Random, world: World) -> Item:
        cause, k = rng.randint(0, 1), rng.randint(5, 12)

        # --- метрики: p95 по сервисам неделю назад и сегодня ---
        app = [n.name for n in world.nodes if n.kind in _APP]
        deep = _deep_app(world)
        src = rng.choice([s for s in deep if "postgres" in world.deps(s)] or deep)
        impacted = world.impacted_by(src)
        delta = rng.randint(30, 90) * 10
        rows = []
        for s in app:
            base = world.service(s).p95_ms
            if s == src:
                now = base + delta
            elif s in impacted:
                now = base + round(delta * rng.uniform(0.6, 0.95))
            else:
                now = round(base * rng.uniform(0.95, 1.05))
            rows.append(f"- {s}: {base} → {now}")
        pool = list(dict.fromkeys([*[x for x in impacted if x in app], *app]))
        opts, key = _shuffled(rng, src, [x for x in pool if x != src][:3])
        s_metrics = Item(
            kind=Kind.choice,
            stem=(
                "p95 задержки по сервисам, мс (неделю назад → сегодня):\n"
                + "\n".join(rows)
                + "\n\nВ каком сервисе источник роста задержки?"
            ),
            options=opts,
            key=key,
        )

        # --- логи: журнал запросов БД одного вызова сервиса-источника ---
        pairs = _fk_pairs(world, need_cat=False)
        child, fk, parent = rng.choice(
            [p for p in pairs if src not in (p[0].name, p[2].name)] or pairs
        )
        ids = sorted(rng.sample(range(1, 200), k=k))
        log = [f"duration: 2.8 ms  statement: SELECT * FROM {parent.name} ORDER BY id LIMIT {k}"]
        if cause == 0:
            log += [
                f"duration: {rng.randint(15, 40) / 10} ms  statement: "
                f"SELECT * FROM {child.name} WHERE {fk} = {i}"
                for i in ids
            ]
        else:
            n_rows = rng.randint(200, 900) * 1000
            log += [
                f"duration: {rng.randint(9000, 19000) / 10} ms  statement: "
                f"SELECT * FROM {child.name} WHERE {fk} = ANY('{{{','.join(map(str, ids))}}}')",
                f"  plan: Seq Scan on {child.name} (rows={n_rows}) Filter: ({fk} = ANY(...))",
            ]
        what = (
            f"N+1: отдельный запрос к {child.name} на каждую строку {parent.name}",
            f"Полный перебор {child.name}: запрос по {fk} идёт без индекса",
        )
        opts, key = _shuffled(
            rng,
            what[cause],
            [
                what[1 - cause],
                "Блокировка: запросы ждут долгую транзакцию",
                "Пул соединений исчерпан: запросы ждут свободное соединение",
            ],
        )
        s_logs = Item(
            kind=Kind.choice,
            stem=(
                "Журнал запросов postgres за один вызов медленного обработчика сервиса-источника:\n"
                + "\n".join(log)
                + "\n\nЧто показывает журнал?"
            ),
            options=opts,
            key=key,
        )

        # --- код: обработчик и миграция релиза, дефект только в одном ---
        if cause == 0:
            handler = [
                f"def list_{parent.name}(limit):",
                f'    items = db.fetch_all("SELECT * FROM {parent.name} '
                'ORDER BY id LIMIT %s", limit)',
                "    for it in items:",
                f'        it["{child.name}"] = db.fetch_all("SELECT * FROM {child.name} '
                f'WHERE {fk} = %s", it["id"])',
                "    return items",
            ]
            mig = [
                f"ALTER TABLE {child.name} ADD COLUMN note text;",
                f"ANALYZE {child.name};",
            ]
            bad = [4]
        else:
            handler = [
                f"def list_{parent.name}(limit):",
                f'    items = db.fetch_all("SELECT * FROM {parent.name} '
                'ORDER BY id LIMIT %s", limit)',
                "    ids = [it['id'] for it in items]",
                f'    kids = db.fetch_all("SELECT * FROM {child.name} WHERE {fk} = ANY(%s)", ids)',
                f"    return attach(items, kids, by='{fk}')",
            ]
            mig = [
                f"ALTER TABLE {child.name} ADD COLUMN note text;",
                f"DROP INDEX idx_{child.name}_{fk};",
            ]
            bad = [len(handler) + 4]  # пустая строка, комментарий, ALTER, DROP
        lines = [*handler, "", "-- migrations/0042_release.sql", *mig]
        s_code = Item(
            kind=Kind.find_bug,
            stem=(
                "Изменения последнего релиза сервиса-источника: обработчик и миграция.\n\n"
                f"{_listing(lines)}\n\nОтметьте строки, из-за которых выросла задержка."
            ),
            key=bad,
        )

        # --- архитектура: нагрузка на postgres от обработчика ---
        rps = world.service(src).rps
        per_call = 1 + k if cause == 0 else 2
        s_arch = Item(
            kind=Kind.estimate,
            stem=(
                f"Сервис-источник в пике получает {rps} вызовов этого обработчика в секунду; "
                "журнал из шага 2 — один типичный вызов. Сколько запросов в секунду обработчик "
                "отправляет в postgres? Достаточно оценки."
            ),
            key=rps * per_call,
        )

        fixes = (
            f"Загрузить строки {child.name} одним запросом для всех {parent.name} "
            f"({fk} = ANY(...) или JOIN)",
            f"Вернуть индекс по {child.name}.{fk} (CREATE INDEX CONCURRENTLY)",
        )
        opts, key = _shuffled(
            rng,
            fixes[cause],
            [
                fixes[1 - cause],
                "Вдвое увеличить пул соединений к postgres",
                "Кешировать ответы gateway на 5 минут",
            ],
        )
        s_fix = Item(
            kind=Kind.choice,
            stem="Какое исправление убирает причину?",
            options=opts,
            key=key,
        )

        steps = (s_metrics, s_logs, s_code, s_arch, s_fix)
        return Item(
            kind=self.kind,
            stem=(
                f"После релиза в компании «{world.company}» ({world.domain_title}) пользователи "
                f"жалуются на медленные страницы. {_INTRO}\n\n{_edges_text(world)}"
            ),
            key=[s.key for s in steps],
            time_limit_s=600,
            steps=steps,
            meta={"knobs": {"cause": cause, "rows": k}, "root": src},
        )


FAMILIES = [IncidentChainOutage(), IncidentChainLatency()]
