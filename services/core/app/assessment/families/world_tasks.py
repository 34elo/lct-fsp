"""Семейства по миру (E26-2): архитектура, данные, логи, SQL, SJT по команде.

Всё берётся из полного `World` (E26-1): граф сервисов (`nodes`, `edges`), таблицы с данными
(`data`), метрики с рядом (`kpis`), команда (`team`). Истина известна генератору: ключ считается
по миру на Python, а для данных и SQL `meta["exec"]` повторяет расчёт исполнением (SQL — в
SQLite в памяти), чтобы `make families-check` сверил решатель с исполнением.

Ручки сложности тянутся из `rng` семейства; мир даёт только имена, артефакты и масштаб.
"""

from __future__ import annotations

import re
from random import Random

from fsp_contracts.assessment import SkillType

from app.assessment.families.base import BaseFamily, Item, Kind
from app.assessment.world import Cell, Member, Table, World

_APP = ("api", "worker")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --- общие помощники --------------------------------------------------------------------------
def _edges_text(world: World) -> str:
    nodes = ", ".join(f"{n.name} ({n.kind})" for n in world.nodes)
    lines = "\n".join(f"- {a} → {b}" for a, b in world.edges)
    return f"Узлы: {nodes}.\nЗависимости (A → B: A вызывает B или пишет в B):\n{lines}"


def _cell(v: object) -> str:
    """Ячейка Markdown-таблицы: `|` и переводы строк в значении не ломают разметку."""
    return str(v).replace("|", "\\|").replace("\n", " ")


def _render(t: Table) -> str:
    """Таблица для условия задания в Markdown (GFM): подпись со схемой и сама таблица (E39-9)."""
    head = "| " + " | ".join(_cell(c) for c in t.columns) + " |"
    rule = "|" + "|".join(" --- " for _ in t.columns) + "|"
    rows = "\n".join("| " + " | ".join(_cell(v) for v in r) + " |" for r in t.rows)
    return f"`{t.schema()}`\n\n{head}\n{rule}\n{rows}"


def _num_cols(t: Table) -> list[str]:
    """Целочисленные колонки с данными (не `id` и не внешние ключи)."""
    fk = {c for c, _ in t.foreign_keys}
    return [
        c
        for c in t.columns
        if c != "id"
        and c not in fk
        and all(isinstance(v, int) and not isinstance(v, bool) for v in t.column(c))
    ]


def _cat_cols(t: Table) -> list[str]:
    """Строковые колонки-категории (не даты), где есть хотя бы два разных значения."""
    return [
        c
        for c in t.columns
        if all(isinstance(v, str) and not _DATE.match(v) for v in t.column(c))
        and len(set(t.column(c))) >= 2
    ]


def _q(v: Cell) -> str:
    return f"'{v}'" if isinstance(v, str) else str(v)


def _sqlite_exec(tables: list[Table], sql: str) -> str:
    """Python-фрагмент: таблицы мира в SQLite в памяти, запрос, печать первой ячейки."""
    lines = ["import sqlite3", 'db = sqlite3.connect(":memory:")']
    for t in tables:
        cols = ", ".join(t.columns)
        marks = ", ".join("?" for _ in t.columns)
        lines.append(f'db.execute("CREATE TABLE {t.name} ({cols})")')
        lines.append(f'db.executemany("INSERT INTO {t.name} VALUES ({marks})", {list(t.rows)!r})')
    lines.append(f"print(db.execute({sql!r}).fetchone()[0])")
    return "\n".join(lines)


# --- архитектура: правила графа ---------------------------------------------------------------
class ArchBlastRadius(BaseFamily):
    """Отказ узла графа: сколько прикладных сервисов он заденет (транзитивно). Ответ — число."""

    slug = "arch_blast_radius"
    kind = Kind.exact
    skill = "system_design"
    skill_type = SkillType.thinking
    level = 3
    # infra = 1: отказывает инфраструктура (задевает несколько веток), 0 — прикладной сервис.
    knob_bounds = {"infra": (0, 1)}

    def generate(self, rng: Random, world: World) -> Item:
        def hit(name: str) -> list[str]:
            return [n for n in world.impacted_by(name) if world.service(n).kind in _APP]

        infra = rng.randint(0, 1)
        cands = [
            n.name
            for n in world.nodes
            if n.kind != "gateway" and (n.kind not in _APP) == bool(infra) and hit(n.name)
        ]
        down = rng.choice(cands)
        key = len(hit(down))
        return Item(
            kind=self.kind,
            stem=(
                f"Схема сервисов компании «{world.company}» ({world.domain_title}).\n"
                f"{_edges_text(world)}\n\n"
                f"Узел {down} полностью отказал, обходных путей и кешей нет. Сколько прикладных "
                "сервисов (api и worker; gateway и инфраструктуру не считаем) перестанут "
                "работать полностью или частично?"
            ),
            key=key,
            time_limit_s=180,
            meta={"knobs": {"infra": infra}, "down": down},
        )


class ArchStartOrder(BaseFamily):
    """Порядок подъёма цепочки зависимостей после аварии. Ответ — порядок.

    Узлы берутся с одного пути графа от gateway: каждый зависит (транзитивно) от следующего,
    поэтому правильный порядок запуска единственный.
    """

    slug = "arch_start_order"
    kind = Kind.order
    skill = "microservices"
    skill_type = SkillType.thinking
    level = 3
    knob_bounds = {"n_steps": (3, 4)}  # путь от gateway во всех доменах не короче 4 узлов

    def generate(self, rng: Random, world: World) -> Item:
        n = rng.randint(3, 4)
        paths: list[list[str]] = []

        def walk(path: list[str]) -> None:
            nxt = world.deps(path[-1])
            if not nxt:
                paths.append(path)
            for b in nxt:
                walk([*path, b])

        walk(["gateway"])
        path = rng.choice([p for p in paths if len(p) >= n])
        picked = sorted(rng.sample(range(len(path)), k=n))
        chain = [path[i] for i in picked][::-1]  # сначала зависимости
        shown = rng.sample(chain, k=n)
        return Item(
            kind=self.kind,
            stem=(
                f"Компания «{world.company}» поднимает инфраструктуру после полного отключения "
                "дата-центра.\n"
                f"{_edges_text(world)}\n\n"
                "Узел можно запускать, только когда работает всё, от чего он зависит. "
                "Расставьте показанные узлы в порядке запуска."
            ),
            options=shown,
            key=[shown.index(x) for x in chain],
            time_limit_s=150,
            meta={"knobs": {"n_steps": n}},
        )


# --- анализ данных с известной истиной -------------------------------------------------------
class DataTableAggregate(BaseFamily):
    """Сводка по таблице мира с фильтром: сумма, количество или максимум. Ответ — число."""

    slug = "data_table_aggregate"
    kind = Kind.exact
    skill = "data_analysis"
    skill_type = SkillType.hard
    level = 2
    knob_bounds = {"op": (0, 2)}  # 0 — количество, 1 — сумма, 2 — максимум

    def generate(self, rng: Random, world: World) -> Item:
        op_i = rng.randint(0, 2)
        op = ("count", "sum", "max")[op_i]
        tables = [t for t in world.data if _num_cols(t) and _cat_cols(t)]
        t = rng.choice(tables)
        num, cat = rng.choice(_num_cols(t)), rng.choice(_cat_cols(t))
        value = rng.choice(sorted(set(t.column(cat))))
        i, j = t.columns.index(num), t.columns.index(cat)
        sel = [r[i] for r in t.rows if r[j] == value]
        key = {"sum": sum(sel), "count": len(sel), "max": max(sel)}[op]
        what = {
            "sum": f"Какова сумма значений {num}",
            "count": "Каково количество строк",
            "max": f"Каково максимальное значение {num}",
        }[op]
        expr = {"sum": "sum(sel)", "count": "len(sel)", "max": "max(sel)"}[op]
        code = (
            f"rows = {list(t.rows)!r}\n"
            f"sel = [r[{i}] for r in rows if r[{j}] == {value!r}]\n"
            f"print({expr})"
        )
        return Item(
            kind=self.kind,
            stem=(
                f"Выгрузка из базы «{world.company}»:\n\n{_render(t)}\n\n"
                f"{what} среди строк, где {cat} = {value}?"
            ),
            key=key,
            time_limit_s=150,
            meta={"exec": code, "knobs": {"op": op_i}},
        )


class KpiAnomalyDay(BaseFamily):
    """Ряд метрики за 14 дней с одним выбросом: в какой день аномалия. Ответ — индекс варианта.

    Обычные дни колеблются в пределах ±5 % от базы, выброс — на 25–40 %, поэтому ключ однозначен.
    """

    slug = "kpi_anomaly_day"
    kind = Kind.choice
    skill = "data_driven_thinking"
    skill_type = SkillType.thinking
    level = 2
    knob_bounds = {"shift_pct": (25, 40)}

    def generate(self, rng: Random, world: World) -> Item:
        m = rng.choice(world.kpis)
        series = list(m.series)
        whole = all(float(v).is_integer() for v in series)
        digits = 0 if whole else max(len(str(v).split(".")[1]) for v in series)
        day = rng.randrange(1, len(series) - 1)
        shift = rng.randint(25, 40)
        sign = rng.choice([1, -1])
        if m.unit == "доля":  # доля не больше 1: выброс вниз
            sign = -1
        series[day] = round(series[day] * (1 + sign * shift / 100), digits)

        def fmt(v: float) -> str:
            return str(int(v)) if whole else str(v)

        dates = [f"2026-09-{17 + d:02d}" for d in range(len(series))]
        rows = "\n".join(f"{dt}: {fmt(v)}" for dt, v in zip(dates, series, strict=True))
        others = rng.sample([d for d in range(len(series)) if d != day], k=3)
        opts = sorted([day, *others])
        return Item(
            kind=self.kind,
            stem=(
                f"Метрика «{m.title}» ({m.unit}) сервиса компании «{world.company}» по дням:\n"
                f"{rows}\n\nВ какой день значение выбивается из обычного поведения ряда?"
            ),
            options=[dates[d] for d in opts],
            key=opts.index(day),
            time_limit_s=120,
            meta={"knobs": {"shift_pct": shift}},
        )


# --- логи инцидента ---------------------------------------------------------------------------
_REASONS = (
    "connection pool exhausted (50/50 in use)",
    "OutOfMemoryError: heap limit reached",
    "panic: nil pointer dereference in handler",
    "disk full: cannot write temp file",
)


class IncidentLogRootCause(BaseFamily):
    """Логи инцидента: по цепочке ошибок `upstream … timeout` найти сервис-первопричину.

    Ответ — индекс варианта. Первопричина — единственный сервис со своей (не upstream) ошибкой;
    отвлекающий манёвр — предупреждение о медленном запросе у здорового сервиса до инцидента.
    """

    slug = "incident_log_root_cause"
    kind = Kind.choice
    skill = "monitoring"
    skill_type = SkillType.hard
    level = 3
    knob_bounds = {"noise_error": (0, 1)}  # 1 — шум до инцидента тоже ERROR (ошибка клиента)

    def generate(self, rng: Random, world: World) -> Item:
        noise_error = rng.randint(0, 1)
        app = [n.name for n in world.nodes if n.kind in _APP]
        # Первопричина — сервис, у которого есть прикладные вызывающие: цепочка ошибок длиннее.
        deep = [s for s in app if any(c in app for c in world.callers(s))]
        broken = rng.choice(deep or app)
        impacted = world.impacted_by(broken)
        healthy = [s for s in app if s != broken and s not in impacted]
        h, m, s0 = rng.randint(0, 23), rng.randint(0, 50), rng.randint(0, 20)

        def ts(sec: int) -> str:
            total = s0 + sec
            return f"{h:02d}:{m + total // 60:02d}:{total % 60:02d}"

        logs: list[tuple[int, str]] = []
        for n in rng.sample(app, k=min(3, len(app))):  # фон до инцидента
            logs.append((rng.randint(0, 19), f"INFO  {n}: GET /health 200"))
        herring = rng.choice(healthy) if healthy else None
        if herring:  # шум до инцидента: медленный запрос или ошибка клиента, каскада нет
            noise = "ERROR {}: 400 invalid field 'qty'" if noise_error else "WARN  {}: slow query"
            logs.append((rng.randint(5, 15), noise.format(herring)))
        t0 = rng.randint(20, 30)
        logs.append((t0, f"ERROR {broken}: {rng.choice(_REASONS)}"))
        # Ошибки идут вверх по графу: чем дальше от первопричины, тем позже.
        dist, frontier, t = {broken: 0}, [broken], t0
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
        text = "\n".join(f"{ts(sec)} {line}" for sec, line in logs)

        hit = [x for x in impacted if x != "gateway"]
        rest = [x for x in healthy if x != herring]
        pool = hit[:2] + ([herring] if herring else []) + rest
        others = list(dict.fromkeys(pool))[:3] or ["gateway"]
        options = rng.sample([broken, *others], k=1 + len(others))
        return Item(
            kind=self.kind,
            stem=(
                f"Ночной инцидент в компании «{world.company}». Зависимости сервисов:\n"
                f"{_edges_text(world)}\n\nЛоги:\n{text}\n\n"
                "Какой сервис — первопричина инцидента?"
            ),
            options=options,
            key=options.index(broken),
            time_limit_s=180,
            meta={"knobs": {"noise_error": noise_error}},
        )


# --- SQL по таблицам мира ---------------------------------------------------------------------
def _fk_pairs(world: World, need_cat: bool) -> list[tuple[Table, str, Table]]:
    """(дочерняя таблица, колонка FK, родительская таблица) из данных мира."""
    names = {t.name: t for t in world.data}
    return [
        (t, col, names[ref])
        for t in world.data
        for col, ref in t.foreign_keys
        if ref in names and (not need_cat or _cat_cols(names[ref]))
    ]


class SqlJoinFilter(BaseFamily):
    """JOIN по внешнему ключу и фильтр по родителю: что вернёт запрос. Ответ — число."""

    slug = "sql_join_filter"
    kind = Kind.exact
    skill = "sql"
    skill_type = SkillType.hard
    level = 2
    knob_bounds = {"agg_sum": (0, 1)}  # 0 — COUNT(*), 1 — SUM по колонке дочерней таблицы

    def generate(self, rng: Random, world: World) -> Item:
        agg_sum = rng.randint(0, 1)
        pairs = [p for p in _fk_pairs(world, need_cat=True) if _num_cols(p[0]) or not agg_sum]
        child, fk, parent = rng.choice(pairs)
        cat = rng.choice(_cat_cols(parent))
        ci = child.columns.index(fk)
        pc = dict(zip(parent.column("id"), parent.column(cat), strict=True))
        joined = [r for r in child.rows if r[ci] in pc]
        value = rng.choice(sorted({pc[r[ci]] for r in joined}))
        sel = [r for r in joined if pc[r[ci]] == value]
        if agg_sum:
            num = rng.choice(_num_cols(child))
            ni = child.columns.index(num)
            agg, key = f"SUM(c.{num})", sum(r[ni] for r in sel)
        else:
            agg, key = "COUNT(*)", len(sel)
        sql = (
            f"SELECT {agg} FROM {child.name} AS c JOIN {parent.name} AS p ON c.{fk} = p.id "
            f"WHERE p.{cat} = {_q(value)}"
        )
        return Item(
            kind=self.kind,
            stem=(
                f"Таблицы базы «{world.company}»:\n\n{_render(parent)}\n\n{_render(child)}\n\n"
                f"Что вернёт запрос?\n\n```sql\n{sql};\n```"
            ),
            key=key,
            time_limit_s=180,
            meta={
                "exec": _sqlite_exec([parent, child], sql),
                "knobs": {"agg_sum": agg_sum},
            },
        )


class SqlLeftJoin(BaseFamily):
    """LEFT JOIN: родители без детей, COUNT(*) против COUNT(колонки), лидер по числу детей."""

    slug = "sql_left_join"
    kind = Kind.exact
    skill = "sql"
    skill_type = SkillType.hard
    level = 3
    # 0 — родители без детей, 1 — COUNT(*) по LEFT JOIN, 2 — лидер по числу детей
    knob_bounds = {"variant": (0, 2)}

    def generate(self, rng: Random, world: World) -> Item:
        variant = rng.randint(0, 2)
        child, fk, parent = rng.choice(_fk_pairs(world, need_cat=False))
        ci = child.columns.index(fk)
        kids = {pid: sum(1 for r in child.rows if r[ci] == pid) for pid in parent.column("id")}
        join = f"FROM {parent.name} AS p LEFT JOIN {child.name} AS c ON c.{fk} = p.id"
        if variant == 0:
            sql = f"SELECT COUNT(*) {join} WHERE c.id IS NULL"
            key = sum(1 for k in kids.values() if k == 0)
        elif variant == 1:
            sql = f"SELECT COUNT(*) {join}"
            key = sum(max(1, k) for k in kids.values())
        else:
            sql = f"SELECT p.id {join} GROUP BY p.id ORDER BY COUNT(c.id) DESC, p.id LIMIT 1"
            key = min(kids, key=lambda pid: (-kids[pid], pid))
        return Item(
            kind=self.kind,
            stem=(
                f"Таблицы базы «{world.company}»:\n\n{_render(parent)}\n\n{_render(child)}\n\n"
                f"Что вернёт запрос?\n\n```sql\n{sql};\n```"
            ),
            key=key,
            time_limit_s=180,
            meta={
                "exec": _sqlite_exec([parent, child], sql),
                "knobs": {"variant": variant},
            },
        )


# --- SJT по команде ---------------------------------------------------------------------------
def _years(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} год"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} года"
    return f"{n} лет"


# Ситуация: условие с {lead}, {who}, {role}, {svc}, {years}; действия с оценкой 1..4 (все разные).
_TEAMWORK: list[tuple[str, list[tuple[str, int]]]] = [
    (
        "Вы нашли ошибку в сервисе {svc}, которая блокирует вашу задачу. Сервисом владеет "
        "{who} ({role}), сейчас в отпуске до понедельника. Тимлид — {lead}.",
        [
            (
                "Завести задачу с шагами воспроизведения, предложить исправление PR'ом в {svc} "
                "и попросить тимлида ({lead}) назначить ревьюера на время отпуска владельца",
                4,
            ),
            ("Написать владельцу ({who}) в личные сообщения и попросить посмотреть из отпуска", 3),
            ("Отложить свою задачу до возвращения владельца", 2),
            ("Тихо поправить {svc} прямо в main без ревью", 1),
        ],
    ),
    (
        "На ретро {who} ({role}) говорит, что сервис {svc} постоянно ломают чужие изменения, "
        "и предлагает запретить другим в него коммитить. Тимлид — {lead}.",
        [
            (
                "Разобрать вместе с владельцем ({who}) последние поломки и предложить "
                "контрактные тесты и обязательное ревью владельца для {svc}",
                4,
            ),
            ("Попросить тимлида ({lead}) решить, кто может коммитить в {svc}", 3),
            ("Согласиться с запретом, чтобы закрыть тему", 2),
            ("Возразить, что владелец {svc} просто плохо пишет тесты", 1),
        ],
    ),
]

_MENTORING: list[tuple[str, list[tuple[str, int]]]] = [
    (
        "{who} ({role}, опыт — {years}) получил(а) первую задачу в сервисе {svc}. Прошло три "
        "дня, прогресса не видно, вопросов новичок не задаёт. Вы — наставник.",
        [
            (
                "Предложить короткий созвон: вместе разобрать, где застряли, и договориться "
                "о ежедневной сверке на время задачи",
                4,
            ),
            ("Прислать ссылки на документацию по {svc} и попросить писать, если что", 3),
            ("Сообщить тимлиду ({lead}), что задача буксует", 2),
            ("Доделать задачу самому, чтобы не срывать срок", 1),
        ],
    ),
    (
        "{who} ({role}, опыт — {years}) второй раз подряд ломает миграции в сервисе {svc} "
        "одной и той же ошибкой. Вы — наставник, тимлид — {lead}.",
        [
            (
                "Разобрать ошибку вместе, предложить добавить проверку в CI и чек-лист "
                "для миграций {svc}",
                4,
            ),
            ("Подробно описать ошибку в комментарии к PR", 3),
            ("Самому проверять все миграции новичка перед мержем", 2),
            ("Отметить ошибку при всей команде на стендапе", 1),
        ],
    ),
]


class _TeamSjt(BaseFamily):
    kind = Kind.sjt
    bank: list[tuple[str, list[tuple[str, int]]]]

    def person(self, rng: Random, team: tuple[Member, ...]) -> Member:
        raise NotImplementedError

    def generate(self, rng: Random, world: World) -> Item:
        lead = world.team[0]
        who = self.person(rng, world.team)
        own = [s for m in world.team for s in m.services]
        svc = rng.choice(list(who.services) or own)
        ctx = {
            "lead": lead.name,
            "who": who.name,
            "role": who.role,
            "svc": svc,
            "years": _years(who.years),
        }
        text, acts = rng.choice(self.bank)
        shown = rng.sample(acts, k=len(acts))
        team = "; ".join(f"{m.name} — {m.role}" for m in world.team)
        return Item(
            kind=self.kind,
            stem=(
                f"Команда «{world.company}»: {team}.\n\n{text.format(**ctx)}\n\n"
                "Расставьте действия от самого эффективного к наименее эффективному."
            ),
            options=[a.format(**ctx) for a, _ in shown],
            key=sorted(range(len(shown)), key=lambda i: -shown[i][1]),
            time_limit_s=180,
            meta={"ratings": [r for _, r in shown]},
        )


class SjtTeamwork(_TeamSjt):
    """Владелец сервиса из команды мира: совместная работа над чужим кодом."""

    slug = "sjt_teamwork"
    skill = "teamwork"
    skill_type = SkillType.soft
    level = 2
    bank = _TEAMWORK

    def person(self, rng: Random, team: tuple[Member, ...]) -> Member:
        owners = [m for m in team[1:] if m.services] or [team[0]]
        return rng.choice(owners)


class SjtMentoring(_TeamSjt):
    """Самый младший по опыту в команде мира: наставничество."""

    slug = "sjt_mentoring"
    skill = "mentoring"
    skill_type = SkillType.soft
    level = 3
    bank = _MENTORING

    def person(self, rng: Random, team: tuple[Member, ...]) -> Member:
        pool = [m for m in team[1:] if m.services] or list(team[1:])
        return min(pool, key=lambda m: (m.years, m.name))


FAMILIES = [
    ArchBlastRadius(),
    ArchStartOrder(),
    DataTableAggregate(),
    KpiAnomalyDay(),
    IncidentLogRootCause(),
    SqlJoinFilter(),
    SqlLeftJoin(),
    SjtTeamwork(),
    SjtMentoring(),
]
