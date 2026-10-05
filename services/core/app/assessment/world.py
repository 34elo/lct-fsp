"""Мир варианта (assessment.md §4): компания, домен, сущности, сервисы, таблицы, метрики.

Минимальная версия (E22-1): детерминированно из сида, без внешних данных. Компании вымышленные.
Перекраска не меняет ручки сложности: семейства берут из мира только имена и масштаб чисел.
"""

from __future__ import annotations

from dataclasses import dataclass
from random import Random

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


@dataclass(frozen=True)
class World:
    seed: int
    domain: str
    company: str
    entities: tuple[str, ...]
    services: tuple[str, ...]
    tables: tuple[str, ...]
    metrics: tuple[str, ...]
    scale: int  # порядок «пользователей в сутки»: 10^scale

    @classmethod
    def from_seed(cls, seed: int, domain: str | None = None) -> World:
        rng = Random(seed)
        dom = domain if domain in _DOMAINS else rng.choice(DOMAINS)
        d = _DOMAINS[dom]
        entities = tuple(rng.sample(d["entities"], k=len(d["entities"])))
        return cls(
            seed=seed,
            domain=dom,
            company=rng.choice(d["companies"]),
            entities=entities,
            services=tuple(rng.sample(d["services"], k=len(d["services"]))),
            tables=tuple(f"{e}s" for e in entities),
            metrics=tuple(d["metrics"]),
            scale=rng.randint(4, 7),
        )
