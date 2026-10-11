"""Полный `World`: граф, данные, метрики, команда, домен."""

from random import Random

import pytest
from app.assessment import families as registry
from app.assessment import plan_preview
from app.assessment import selection as sel
from app.assessment.config import load_config
from app.assessment.psychometrics import calibrate_b, p_correct
from app.assessment.world import (
    _DOMAINS,
    DOMAINS,
    HISTORY_DAYS,
    World,
    domain_for_profession,
    domain_for_vacancy,
    domain_from_text,
)
from fsp_contracts.assessment import TestGrade

CFG = load_config()
SEEDS = [(i * 2_654_435_761 + 97) % 2**63 for i in range(60)]


def test_one_seed_one_world():
    for s in SEEDS[:20]:
        for d in (*DOMAINS, None):
            assert World.from_seed(s, d) == World.from_seed(s, d)
    worlds = {World.from_seed(s, "fintech") for s in SEEDS}
    assert len({w.data for w in worlds}) == len(SEEDS)
    assert len({(w.company, w.team) for w in worlds}) > 10


def test_legacy_fields_unchanged():
    """Старые поля — та же последовательность `Random(seed)`, что раньше: выданные задания живы."""
    for s in SEEDS:
        for d in (None, "rag_service"):
            rng = Random(s)
            dom = d or rng.choice(DOMAINS)
            src = _DOMAINS[dom]
            entities = tuple(rng.sample(src["entities"], k=5))
            company = rng.choice(src["companies"])
            services = tuple(rng.sample(src["services"], k=5))
            scale = rng.randint(4, 7)
            w = World.from_seed(s, d)
            assert (w.domain, w.entities, w.company, w.services, w.scale) == (
                dom,
                entities,
                company,
                services,
                scale,
            )


@pytest.mark.parametrize("domain", DOMAINS)
def test_service_graph(domain):
    for s in SEEDS:
        w = World.from_seed(s, domain)
        names = [n.name for n in w.nodes]
        assert len(names) == len(set(names))
        assert all(a in names and b in names for a, b in w.edges)
        assert len(w.topo_order()) == len(names)  # ацикличен
        assert w.callers("gateway") == () and w.deps("gateway")
        assert set(w.services) <= set(names)
        engineers = {m.name for m in w.team if m.role not in ("продакт", "аналитик")}
        for svc in w.services:
            node = w.service(svc)
            assert node.kind in ("api", "worker") and node.owner in engineers
            assert node.rps >= 1 and node.p95_ms > 0
            assert "gateway" in w.impacted_by(svc) or w.callers(svc) == ()
        infra = [n for n in w.nodes if n.kind not in ("api", "worker", "gateway")]
        assert infra and all(w.callers(n.name) for n in infra)  # лишней инфраструктуры нет


@pytest.mark.parametrize("domain", DOMAINS)
def test_tables_with_data(domain):
    for s in SEEDS:
        w = World.from_seed(s, domain)
        assert tuple(t.name for t in w.data) == w.tables
        assert all(not t.endswith("ys") for t in w.tables)  # deliveries, queries
        for t in w.data:
            assert 6 <= len(t.rows) <= 10
            assert t.column("id") == tuple(range(1, len(t.rows) + 1))
            assert all(len(r) == len(t.columns) for r in t.rows)
            for col, ref in t.foreign_keys:
                n = len(w.table(ref).rows)
                assert all(1 <= v <= n for v in t.column(col)), (t.name, col)
                assert f"{col} → {ref}.id" in t.schema()
            assert t.as_dicts()[0]["id"] == 1


@pytest.mark.parametrize("domain", DOMAINS)
def test_metrics_and_team(domain):
    for s in SEEDS[:20]:
        w = World.from_seed(s, domain)
        assert tuple(m.name for m in w.kpis) == w.metrics
        for m in w.kpis:
            assert len(m.series) == HISTORY_DAYS and m.value == m.series[-1] > 0
            assert m.unit and m.title
        assert 4 <= len(w.team) <= 6 and w.team[0].role == "тимлид"
        assert len({m.name for m in w.team}) == len(w.team)
        owned = [s for m in w.team for s in m.services]
        assert sorted(owned) == sorted(w.services)
        assert w.domain_title


def test_fraction_metrics_stay_in_bounds():
    """Метрики с единицей 'доля' остаются в [0.0, 1.0] несмотря на шум."""
    for domain in DOMAINS:
        for s in SEEDS[:30]:
            w = World.from_seed(s, domain)
            for m in w.kpis:
                if m.unit == "доля":
                    assert all(0.0 <= v <= 1.0 for v in m.series), (
                        f"{domain}/{m.name}: значения вне [0.0, 1.0]: {m.series}"
                    )


def test_domain_from_vacancy_and_profession():
    assert domain_for_profession("ai_engineer") == "rag_service"
    assert domain_for_profession("backend") is None
    assert domain_for_vacancy("ai_engineer", "Python-разработчик", "маркетплейс") == "rag_service"
    assert domain_for_vacancy("backend", "Бэкенд в банк", "платёжный процессинг") == "fintech"
    assert domain_for_vacancy("backend", "Python", "Маркетплейс: склад и доставка") == "ecommerce"
    assert domain_for_vacancy("ml", "ML", "LLM-ассистент, RAG по базе знаний") == "rag_service"
    assert domain_for_vacancy("frontend", "Онлайн-школа", "LMS для студентов") == "edtech"
    assert domain_for_vacancy("qa", "QA", "Тестирование веб-приложений") is None
    assert domain_from_text("банк", "доставка") is None  # ничья → решает сид
    assert domain_from_text(None, "") is None


def _knobs(fam, seed, domain):
    return fam.generate(Random(seed), World.from_seed(seed, domain)).meta.get("knobs")


def test_recolor_keeps_knobs():
    """Перекраска (другой домен при том же rng семейства) не меняет ручки сложности."""
    for fam in registry.REGISTRY.values():
        for s in SEEDS[:30]:
            knobs = {repr(_knobs(fam, s, d)) for d in DOMAINS}
            assert len(knobs) == 1, (fam.slug, knobs)


def test_recolor_keeps_b_on_synthetic():
    """Синтетика: успех зависит от θ и ручек варианта; `b` после калибровки одна во всех доменах."""
    fams = [f for f in registry.REGISTRY.values() if getattr(f, "knob_bounds", None)]
    assert fams
    for fam in fams:
        bs = []
        for d in DOMAINS:
            rng = Random(fam.slug)  # одни и те же синтетические кандидаты
            b, n = 0.0, 0
            for s in SEEDS:
                knobs = _knobs(fam, s, d)
                lo_hi = fam.knob_bounds
                hard = sum(
                    (knobs[k] - lo) / ((hi - lo) or 1) for k, (lo, hi) in lo_hi.items()
                ) / len(lo_hi)
                theta = rng.gauss(0.0, 1.0)
                y = 1.0 if rng.random() < p_correct(theta, hard * 2 - 1) else 0.0
                b, n = calibrate_b(b, n, theta, y, CFG), n + 1
            bs.append(b)
        assert max(bs) - min(bs) < 1e-9, (fam.slug, bs)


def test_plan_examples_use_given_domain():
    weights = {"python": 1.0, "algorithms": 1.0, "estimation": 1.0}
    types = {"python": "hard", "algorithms": "fundamental", "estimation": "thinking"}
    sections = sel.build_plan(weights, types, TestGrade.middle, CFG)
    by_domain = {d: plan_preview.examples(sections, TestGrade.middle, CFG, d) for d in DOMAINS}
    assert by_domain["fintech"] == plan_preview.examples(sections, TestGrade.middle, CFG, "fintech")
    assert len({repr(v) for v in by_domain.values()}) > 1
