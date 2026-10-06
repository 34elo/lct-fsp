"""Мир варианта (assessment.md §4, ADR-021): вымышленная компания как общий вход для семейств.

`World.from_seed(seed, domain)` детерминированно даёт: домен, компанию, словарь сущностей,
сервисы как граф (узлы, зависимости, владельцы, нагрузка), таблицы с данными (связаны внешними
ключами), метрики с рядом за 14 дней и команду. Компании и люди вымышленные.

Совместимость с E22-1: поля `company`, `entities`, `services`, `tables`, `metrics`, `scale`
получаются той же последовательностью вызовов `Random(seed)`, что и раньше, — уже выданные
задания пересобираются с тем же ключом. Новые части берут свои генераторы
`Random(f"{seed}:{domain}:<часть>")` и не сдвигают старые.

Перекраска не меняет ручки сложности: семейство берёт из мира только имена, артефакты и масштаб
чисел, а ручки тянет из своего `rng`. Домен выбирается по вакансии (`domain_for_vacancy`),
по профессии (`domain_for_profession`) или случайно.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from random import Random
from typing import Any

# --- Словари доменов --------------------------------------------------------------------------
# Порядок и состав списков `_DOMAINS` не менять: от них зависят старые сиды (см. докстринг).
_DOMAINS: dict[str, dict[str, list[str]]] = {
    "ecommerce": {
        "companies": ["Корзинка", "ТоварОнлайн", "Быстрый склад"],
        "entities": ["order", "cart", "product", "customer", "delivery"],
        "services": ["catalog", "checkout", "payments", "shipping", "search"],
        "metrics": ["conversion", "aov", "gmv", "retention"],
    },
    "fintech": {
        "companies": ["Монетка", "ПлатёжПро", "Копилка"],
        "entities": ["account", "transfer", "card", "client", "limit"],
        "services": ["ledger", "antifraud", "cards", "notifications", "kyc"],
        "metrics": ["fraud_rate", "tpv", "churn", "arpu"],
    },
    "edtech": {
        "companies": ["Учисьлегко", "КодКласс", "Умник"],
        "entities": ["course", "lesson", "student", "homework", "teacher"],
        "services": ["courses", "video", "grading", "billing", "chat"],
        "metrics": ["completion", "dau", "nps", "ltv"],
    },
    "rag_service": {
        "companies": ["ИИ-Справка", "ДокПоиск", "Знайка"],
        "entities": ["document", "chunk", "query", "answer", "embedding"],
        "services": ["ingest", "retriever", "reranker", "generator", "feedback"],
        "metrics": ["recall_at_k", "faithfulness", "latency_p95", "cost_per_query"],
    },
}

DOMAINS: tuple[str, ...] = tuple(_DOMAINS)
DOMAIN_TITLES: dict[str, str] = {
    "ecommerce": "e-commerce",
    "fintech": "финтех",
    "edtech": "онлайн-образование",
    "rag_service": "RAG-сервис",
}

# Граф сервисов. `rank` — порядок сверху вниз: зависимость идёт только к сервису ниже по рангу,
# поэтому граф ацикличен при любых случайных добавках. `entry` — что видно снаружи через gateway.
# `kind`: api | worker. `infra[svc]` = (обязательные, возможные) инфраструктурные зависимости.
_GRAPH: dict[str, dict[str, Any]] = {
    "ecommerce": {
        "rank": ["search", "checkout", "catalog", "payments", "shipping"],
        "workers": {"shipping"},
        "entry": ["search", "checkout", "catalog"],
        "edges": [
            ("search", "catalog"),
            ("checkout", "catalog"),
            ("checkout", "payments"),
            ("checkout", "shipping"),
        ],
        "infra_nodes": [
            ("postgres", "storage"),
            ("redis", "cache"),
            ("queue", "queue"),
            ("pay_provider", "external"),
        ],
        "infra": {
            "search": (("redis",), ("postgres",)),
            "checkout": (("postgres",), ("redis", "queue")),
            "catalog": (("postgres",), ("redis",)),
            "payments": (("pay_provider", "postgres"), ("queue",)),
            "shipping": (("queue",), ("postgres",)),
        },
    },
    "fintech": {
        "rank": ["cards", "antifraud", "kyc", "ledger", "notifications"],
        "workers": {"notifications"},
        "entry": ["cards", "kyc"],
        "edges": [
            ("cards", "antifraud"),
            ("cards", "ledger"),
            ("antifraud", "kyc"),
            ("ledger", "notifications"),
        ],
        "infra_nodes": [
            ("postgres", "storage"),
            ("redis", "cache"),
            ("queue", "queue"),
            ("card_network", "external"),
        ],
        "infra": {
            "cards": (("card_network",), ("postgres", "redis")),
            "antifraud": (("redis",), ("postgres",)),
            "kyc": (("postgres",), ("queue",)),
            "ledger": (("postgres",), ("queue",)),
            "notifications": (("queue",), ("redis",)),
        },
    },
    "edtech": {
        "rank": ["chat", "grading", "courses", "billing", "video"],
        "workers": {"video"},
        "entry": ["chat", "grading", "courses"],
        "edges": [
            ("chat", "courses"),
            ("grading", "courses"),
            ("courses", "video"),
            ("courses", "billing"),
        ],
        "infra_nodes": [
            ("postgres", "storage"),
            ("redis", "cache"),
            ("queue", "queue"),
            ("object_storage", "storage"),
        ],
        "infra": {
            "chat": (("redis",), ("postgres", "queue")),
            "grading": (("postgres",), ("queue",)),
            "courses": (("postgres",), ("redis",)),
            "billing": (("postgres",), ("queue",)),
            "video": (("object_storage",), ("queue",)),
        },
    },
    "rag_service": {
        "rank": ["feedback", "generator", "retriever", "reranker", "ingest"],
        "workers": {"ingest"},
        "entry": ["feedback", "generator", "ingest"],
        "edges": [
            ("feedback", "generator"),
            ("generator", "retriever"),
            ("retriever", "reranker"),
        ],
        "infra_nodes": [
            ("postgres", "storage"),
            ("vector_db", "storage"),
            ("queue", "queue"),
            ("llm", "external"),
        ],
        "infra": {
            "feedback": (("postgres",), ("queue",)),
            "generator": (("llm",), ("postgres",)),
            "retriever": (("vector_db",), ()),
            "reranker": ((), ("llm",)),
            "ingest": (("vector_db", "queue"), ("postgres",)),
        },
    },
}

# Таблицы: сущность → колонки. Тип колонки: ("id",), ("fk", сущность), ("money", lo, hi),
# ("int", lo, hi), ("float", lo, hi), ("enum", значения), ("date",), ("label", варианты).
_SCHEMA: dict[str, dict[str, list[tuple[str, tuple]]]] = {
    "ecommerce": {
        "customer": [
            ("id", ("id",)),
            ("city", ("enum", ("Москва", "Казань", "Пермь", "Томск"))),
            ("created_at", ("date",)),
        ],
        "product": [
            ("id", ("id",)),
            ("title", ("label", ("чайник", "кеды", "лампа", "рюкзак", "плед", "кружка"))),
            ("category", ("enum", ("дом", "одежда", "спорт"))),
            ("price", ("money", 200, 20_000)),
        ],
        "order": [
            ("id", ("id",)),
            ("customer_id", ("fk", "customer")),
            ("status", ("enum", ("new", "paid", "shipped", "cancelled"))),
            ("total", ("money", 500, 30_000)),
            ("created_at", ("date",)),
        ],
        "cart": [
            ("id", ("id",)),
            ("customer_id", ("fk", "customer")),
            ("product_id", ("fk", "product")),
            ("qty", ("int", 1, 5)),
        ],
        "delivery": [
            ("id", ("id",)),
            ("order_id", ("fk", "order")),
            ("status", ("enum", ("pending", "in_transit", "delivered"))),
            ("days", ("int", 1, 7)),
        ],
    },
    "fintech": {
        "client": [
            ("id", ("id",)),
            ("segment", ("enum", ("mass", "premium", "sme"))),
            ("created_at", ("date",)),
        ],
        "account": [
            ("id", ("id",)),
            ("client_id", ("fk", "client")),
            ("currency", ("enum", ("RUB", "USD", "CNY"))),
            ("balance", ("money", 0, 500_000)),
        ],
        "card": [
            ("id", ("id",)),
            ("account_id", ("fk", "account")),
            ("type", ("enum", ("debit", "credit"))),
            ("status", ("enum", ("active", "blocked"))),
        ],
        "transfer": [
            ("id", ("id",)),
            ("account_id", ("fk", "account")),
            ("amount", ("money", 100, 100_000)),
            ("status", ("enum", ("done", "pending", "declined"))),
            ("created_at", ("date",)),
        ],
        "limit": [
            ("id", ("id",)),
            ("account_id", ("fk", "account")),
            ("daily", ("money", 10_000, 300_000)),
        ],
    },
    "edtech": {
        "teacher": [
            ("id", ("id",)),
            ("subject", ("enum", ("python", "math", "sql", "english"))),
            ("rating", ("float", 3.5, 5.0)),
        ],
        "course": [
            ("id", ("id",)),
            ("teacher_id", ("fk", "teacher")),
            ("title", ("label", ("Основы", "Практикум", "Интенсив", "Буткемп"))),
            ("price", ("money", 0, 60_000)),
        ],
        "student": [
            ("id", ("id",)),
            ("city", ("enum", ("Москва", "Казань", "Пермь", "Томск"))),
            ("created_at", ("date",)),
        ],
        "lesson": [
            ("id", ("id",)),
            ("course_id", ("fk", "course")),
            ("duration_min", ("int", 30, 90)),
        ],
        "homework": [
            ("id", ("id",)),
            ("student_id", ("fk", "student")),
            ("lesson_id", ("fk", "lesson")),
            ("score", ("int", 0, 100)),
            ("status", ("enum", ("sent", "checked", "late"))),
        ],
    },
    "rag_service": {
        "document": [
            ("id", ("id",)),
            ("source", ("enum", ("wiki", "pdf", "tickets"))),
            ("pages", ("int", 1, 120)),
            ("updated_at", ("date",)),
        ],
        "chunk": [
            ("id", ("id",)),
            ("document_id", ("fk", "document")),
            ("tokens", ("int", 100, 800)),
        ],
        "embedding": [
            ("id", ("id",)),
            ("chunk_id", ("fk", "chunk")),
            ("model", ("enum", ("e5-small", "bge-m3"))),
            ("dim", ("enum", (384, 1024))),
        ],
        "query": [
            ("id", ("id",)),
            ("channel", ("enum", ("web", "telegram", "api"))),
            ("latency_ms", ("int", 200, 3000)),
            ("created_at", ("date",)),
        ],
        "answer": [
            ("id", ("id",)),
            ("query_id", ("fk", "query")),
            ("chunk_id", ("fk", "chunk")),
            ("faithful", ("enum", (0, 1))),
            ("rating", ("int", 1, 5)),
        ],
    },
}

# Метрики: имя → (единица, название, lo, hi, знаков после запятой, на пользователя в сутки).
# Если последний флаг True, значение умножается на 10**scale (оборот, DAU).
_METRICS: dict[str, dict[str, tuple[str, str, float, float, int, bool]]] = {
    "ecommerce": {
        "conversion": ("%", "конверсия в заказ", 1.5, 4.0, 2, False),
        "aov": ("₽", "средний чек", 1500, 6000, 0, False),
        "gmv": ("₽/сутки", "оборот", 30, 150, 0, True),
        "retention": ("%", "удержание 30 дней", 20, 45, 1, False),
    },
    "fintech": {
        "fraud_rate": ("%", "доля мошеннических операций", 0.05, 0.5, 3, False),
        "tpv": ("₽/сутки", "объём платежей", 200, 900, 0, True),
        "churn": ("%", "отток в месяц", 1.0, 5.0, 2, False),
        "arpu": ("₽", "доход на клиента в месяц", 150, 900, 0, False),
    },
    "edtech": {
        "completion": ("%", "доходимость курса", 10, 60, 1, False),
        "dau": ("чел.", "активных в сутки", 0.05, 0.3, 0, True),
        "nps": ("пункт", "NPS", 10, 60, 0, False),
        "ltv": ("₽", "доход за жизнь ученика", 3000, 30_000, 0, False),
    },
    "rag_service": {
        "recall_at_k": ("доля", "recall@5 ретривера", 0.6, 0.95, 3, False),
        "faithfulness": ("доля", "ответы, подтверждённые источником", 0.7, 0.98, 3, False),
        "latency_p95": ("мс", "задержка ответа p95", 800, 4000, 0, False),
        "cost_per_query": ("₽", "стоимость запроса", 0.05, 2.0, 2, False),
    },
}

_PEOPLE = (
    "Анна",
    "Борис",
    "Вера",
    "Глеб",
    "Дина",
    "Егор",
    "Жанна",
    "Илья",
    "Кира",
    "Лев",
    "Мира",
    "Никита",
    "Ольга",
    "Павел",
    "Рита",
    "Семён",
)
_ROLES = ("бэкенд", "фронтенд", "QA", "аналитик", "DevOps", "продакт")
_ROLES_EXTRA = {"rag_service": ("ML-инженер",), "fintech": ("специалист по рискам",)}

HISTORY_DAYS = 14

# --- Домен из вакансии и профессии ------------------------------------------------------------
_PROFESSION_DOMAIN = {"ai_engineer": "rag_service"}
_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ecommerce": (
        "e-commerce",
        "ecommerce",
        "маркетплейс",
        "интернет-магазин",
        "ритейл",
        "retail",
        "корзин",
        "товар",
        "доставк",
        "склад",
        "покупател",
    ),
    "fintech": (
        "финтех",
        "fintech",
        "банк",
        "платёж",
        "платеж",
        "кредит",
        "антифрод",
        "эквайринг",
        "финанс",
        "страхов",
        "брокер",
        "процессинг",
    ),
    "edtech": (
        "edtech",
        "образован",
        "онлайн-школ",
        "онлайн-курс",
        "студент",
        "учени",
        "lms",
    ),
    "rag_service": (
        "rag",
        "llm",
        "ллм",
        "retrieval",
        "эмбеддинг",
        "embedding",
        "векторн",
        "genai",
        "языков модел",
        "ии-ассистент",
        "ai-ассистент",
        "чат-бот",
        "промпт",
    ),
}


def domain_for_profession(profession: str | None) -> str | None:
    """Домен, который профессия задаёт сама (AI Engineer → RAG-сервис), иначе `None`."""
    return _PROFESSION_DOMAIN.get(profession or "")


def domain_from_text(*texts: str | None) -> str | None:
    """Домен по ключевым словам; при равенстве или без совпадений — `None` (решает сид)."""
    text = " ".join(t for t in texts if t).lower()
    if not text:
        return None
    hits = {
        d: sum(len(re.findall(re.escape(k), text)) for k in kws) for d, kws in _KEYWORDS.items()
    }
    best = max(hits.values())
    top = [d for d, n in hits.items() if n == best]
    return top[0] if best > 0 and len(top) == 1 else None


def domain_for_vacancy(
    role: str | None, title: str | None = None, description: str | None = None
) -> str | None:
    """Домен из вакансии: сначала профессия (AI Engineer → RAG), затем текст вакансии."""
    return domain_for_profession(role) or domain_from_text(title, description)


# --- Модель мира ------------------------------------------------------------------------------
Cell = int | float | str


@dataclass(frozen=True)
class Service:
    name: str
    kind: str  # api | worker | gateway | storage | cache | queue | external
    owner: str | None  # имя из команды; у инфраструктуры нет
    rps: int  # запросов в секунду в пике
    p95_ms: int


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Cell, ...], ...]
    foreign_keys: tuple[tuple[str, str], ...]  # (колонка, таблица)

    def column(self, name: str) -> tuple[Cell, ...]:
        i = self.columns.index(name)
        return tuple(r[i] for r in self.rows)

    def as_dicts(self) -> list[dict[str, Cell]]:
        return [dict(zip(self.columns, r, strict=True)) for r in self.rows]

    def schema(self) -> str:
        """`orders(id, customer_id → customers.id, status)` — для условий заданий."""
        fk = dict(self.foreign_keys)
        cols = ", ".join(f"{c} → {fk[c]}.id" if c in fk else c for c in self.columns)
        return f"{self.name}({cols})"


@dataclass(frozen=True)
class Metric:
    name: str
    unit: str
    title: str
    series: tuple[float, ...]  # по дням, последний — сегодня

    @property
    def value(self) -> float:
        return self.series[-1]


@dataclass(frozen=True)
class Member:
    name: str
    role: str
    years: int
    services: tuple[str, ...]  # чем владеет


@dataclass(frozen=True)
class World:
    seed: int
    domain: str
    company: str
    entities: tuple[str, ...]
    services: tuple[str, ...]  # прикладные сервисы домена (имена)
    tables: tuple[str, ...]  # имена таблиц, по одной на сущность
    metrics: tuple[str, ...]  # имена метрик
    scale: int  # порядок «пользователей в сутки»: 10^scale
    nodes: tuple[Service, ...] = ()  # все узлы графа: gateway, сервисы, инфраструктура
    edges: tuple[tuple[str, str], ...] = ()  # (A, B): A зависит от B (вызывает, пишет в B)
    data: tuple[Table, ...] = ()  # таблицы с данными, порядок как в `tables`
    kpis: tuple[Metric, ...] = ()  # метрики со значениями, порядок как в `metrics`
    team: tuple[Member, ...] = ()

    @classmethod
    def from_seed(cls, seed: int, domain: str | None = None) -> World:
        # Старая часть (E22-1): последовательность вызовов rng не менять.
        rng = Random(seed)
        dom = domain if domain in _DOMAINS else rng.choice(DOMAINS)
        d = _DOMAINS[dom]
        entities = tuple(rng.sample(d["entities"], k=len(d["entities"])))
        company = rng.choice(d["companies"])
        services = tuple(rng.sample(d["services"], k=len(d["services"])))
        scale = rng.randint(4, 7)

        def sub(part: str) -> Random:
            return Random(f"{seed}:{dom}:{part}")

        team = _team(sub("team"), dom, services)
        owners = {s: m.name for m in team for s in m.services}
        nodes, edges = _graph(sub("graph"), dom, scale, owners)
        return cls(
            seed=seed,
            domain=dom,
            company=company,
            entities=entities,
            services=services,
            tables=tuple(_plural(e) for e in entities),
            metrics=tuple(d["metrics"]),
            scale=scale,
            nodes=nodes,
            edges=edges,
            data=_tables(sub("data"), dom, entities),
            kpis=_metrics(sub("metrics"), dom, scale),
            team=team,
        )

    # --- доступ ---
    @property
    def domain_title(self) -> str:
        return DOMAIN_TITLES[self.domain]

    def service(self, name: str) -> Service:
        return next(n for n in self.nodes if n.name == name)

    def table(self, name: str) -> Table:
        return next(t for t in self.data if t.name == name)

    def metric(self, name: str) -> Metric:
        return next(m for m in self.kpis if m.name == name)

    def deps(self, name: str) -> tuple[str, ...]:
        """От кого зависит узел (прямые исходящие рёбра)."""
        return tuple(b for a, b in self.edges if a == name)

    def callers(self, name: str) -> tuple[str, ...]:
        """Кто зависит от узла (прямые входящие рёбра)."""
        return tuple(a for a, b in self.edges if b == name)

    def impacted_by(self, name: str) -> tuple[str, ...]:
        """Узлы, которые затронет отказ `name` (транзитивно вверх по графу), в порядке `nodes`."""
        hit: set[str] = set()
        stack = [name]
        while stack:
            for a in self.callers(stack.pop()):
                if a not in hit:
                    hit.add(a)
                    stack.append(a)
        return tuple(n.name for n in self.nodes if n.name in hit)

    def topo_order(self) -> tuple[str, ...]:
        """Порядок «сначала зависимости»: каждый узел идёт после всех, от кого зависит."""
        out: list[str] = []
        done: set[str] = set()
        names = [n.name for n in self.nodes]
        while len(out) < len(names):
            for n in names:
                if n not in done and all(b in done for b in self.deps(n)):
                    out.append(n)
                    done.add(n)
                    break
            else:  # pragma: no cover - граф ацикличен по построению
                raise ValueError("цикл в графе сервисов")
        return tuple(out)


def _plural(entity: str) -> str:
    """Имя таблицы: `order` → `orders`, `delivery` → `deliveries`, `query` → `queries`."""
    return entity[:-1] + "ies" if entity.endswith("y") else entity + "s"


# --- Генераторы частей ------------------------------------------------------------------------
def _team(rng: Random, dom: str, services: tuple[str, ...]) -> tuple[Member, ...]:
    n = rng.randint(4, 6)
    names = rng.sample(_PEOPLE, k=n)
    pool = list(_ROLES) + list(_ROLES_EXTRA.get(dom, ()))
    roles = ["тимлид", *rng.sample(pool, k=n - 1)]
    # Сервисами владеют инженеры (не продакт и не аналитик); тимлид — если инженеров мало.
    engineers = [i for i, r in enumerate(roles) if r not in ("продакт", "аналитик")]
    owned: dict[int, list[str]] = {i: [] for i in range(n)}
    for k, s in enumerate(services):
        owned[engineers[k % len(engineers)]].append(s)
    return tuple(
        Member(
            name=names[i],
            role=roles[i],
            years=rng.randint(5, 12) if i == 0 else rng.randint(1, 8),
            services=tuple(owned[i]),
        )
        for i in range(n)
    )


def _graph(
    rng: Random, dom: str, scale: int, owners: dict[str, str]
) -> tuple[tuple[Service, ...], tuple[tuple[str, str], ...]]:
    g = _GRAPH[dom]
    rank: list[str] = g["rank"]
    edges: list[tuple[str, str]] = [("gateway", s) for s in g["entry"]]
    edges += list(g["edges"])
    # Случайные добавки: 0–2 ребра вниз по рангу (граф остаётся ацикличным).
    candidates = [(a, b) for i, a in enumerate(rank) for b in rank[i + 1 :] if (a, b) not in edges]
    edges += rng.sample(candidates, k=min(len(candidates), rng.randint(0, 2)))
    for s in rank:
        must, maybe = g["infra"][s]
        edges += [(s, x) for x in must]
        edges += [(s, x) for x in maybe if rng.random() < 0.5]

    # Пиковый RPS на входе: пользователи × запросов на пользователя × пиковость / секунд в сутках.
    peak = max(1, round(10**scale * rng.randint(20, 60) * rng.uniform(2.0, 4.0) / 86_400))
    nodes = [Service("gateway", "gateway", None, peak, rng.randint(5, 30))]
    for s in rank:
        share = rng.uniform(0.1, 1.0)
        nodes.append(
            Service(
                name=s,
                kind="worker" if s in g["workers"] else "api",
                owner=owners.get(s),
                rps=max(1, round(peak * share)),
                p95_ms=rng.randint(4, 40) * 10,
            )
        )
    used = {b for _, b in edges}
    for name, kind in g["infra_nodes"]:
        if name in used:
            nodes.append(Service(name, kind, None, 0, rng.randint(1, 20)))
    order = {n.name: i for i, n in enumerate(nodes)}
    edges.sort(key=lambda e: (order[e[0]], order[e[1]]))
    return tuple(nodes), tuple(edges)


def _cell(rng: Random, spec: tuple, counts: dict[str, int], row_id: int) -> Cell:
    match spec[0]:
        case "id":
            return row_id
        case "fk":
            return rng.randint(1, counts[spec[1]])
        case "money":
            return rng.randint(spec[1] // 10, spec[2] // 10) * 10
        case "int":
            return rng.randint(spec[1], spec[2])
        case "float":
            return round(rng.uniform(spec[1], spec[2]), 1)
        case "enum" | "label":
            return rng.choice(spec[1])
        case "date":
            return f"2026-09-{rng.randint(1, 30):02d}"
    raise ValueError(f"неизвестный тип колонки: {spec!r}")


def _tables(rng: Random, dom: str, entities: tuple[str, ...]) -> tuple[Table, ...]:
    schema = _SCHEMA[dom]
    counts = {e: rng.randint(6, 10) for e in entities}
    out: list[Table] = []
    for e in entities:
        cols = schema[e]
        rows = tuple(
            tuple(_cell(rng, spec, counts, i) for _, spec in cols) for i in range(1, counts[e] + 1)
        )
        out.append(
            Table(
                name=_plural(e),
                columns=tuple(c for c, _ in cols),
                rows=rows,
                foreign_keys=tuple((c, _plural(spec[1])) for c, spec in cols if spec[0] == "fk"),
            )
        )
    return tuple(out)


def _metrics(rng: Random, dom: str, scale: int) -> tuple[Metric, ...]:
    out: list[Metric] = []
    for name in _DOMAINS[dom]["metrics"]:
        unit, title, lo, hi, digits, per_user = _METRICS[dom][name]
        base = rng.uniform(lo, hi) * (10**scale if per_user else 1)
        series = tuple(
            round(base * (1 + rng.uniform(-0.05, 0.05)), digits) for _ in range(HISTORY_DAYS)
        )
        if digits == 0:
            series = tuple(float(int(v)) for v in series)
        out.append(Metric(name, unit, title, series))
    return tuple(out)
