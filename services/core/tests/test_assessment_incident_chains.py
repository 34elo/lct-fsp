"""E26-3: цепочки-инциденты — метрики → логи → код → архитектура → ответ (assessment.md §4)."""

import re
import statistics
import uuid
from random import Random

import pytest
from app.assessment import families as registry
from app.assessment.families import check, incident_chains
from app.assessment.families.base import Kind
from app.assessment.families.spec import FamilySpec
from app.assessment.router import NextOut, PlanExampleOut
from app.assessment.world import DOMAINS, World
from pydantic import ValidationError

FAMILIES = incident_chains.FAMILIES
SEEDS = check.seeds(60)
STEP_KINDS = {
    "incident_chain_outage": [Kind.choice, Kind.choice, Kind.find_bug, Kind.exact, Kind.choice],
    "incident_chain_latency": [Kind.choice, Kind.choice, Kind.find_bug, Kind.estimate, Kind.choice],
}


def build(slug: str, seed: int, domain: str):
    world = World.from_seed(seed, domain)
    return registry.get(slug).generate(Random(seed), world), world


def entries_hit(world: World, src: str) -> int:
    hit = {src, *world.impacted_by(src)}
    return len([e for a, e in world.edges if a == "gateway" and e in hit])


def named(name: str, text: str) -> bool:
    return re.search(rf"\b{name}\b", text) is not None


def test_registered_as_code_families():
    for fam in FAMILIES:
        assert registry.get(fam.slug) is fam
        assert fam.kind == Kind.chain and fam.skill_type == "thinking"


@pytest.mark.parametrize("domain", DOMAINS)
@pytest.mark.parametrize("fam", FAMILIES, ids=lambda f: f.slug)
def test_passes_check_in_every_domain(fam, domain):
    for seed in SEEDS:
        item, world = build(fam.slug, seed, domain)
        assert check.check_item(fam, item) == [], (fam.slug, domain, seed)
        assert build(fam.slug, seed, domain)[0] == item
        assert [s.kind for s in item.steps] == STEP_KINDS[fam.slug]
        assert world.company in item.stem


@pytest.mark.parametrize("slug", sorted(STEP_KINDS))
def test_score_is_mean_of_steps(slug):
    fam = registry.get(slug)
    item, _ = build(slug, 5, "ecommerce")
    key = list(item.key)
    assert fam.score(item, key) == 1.0
    assert fam.score(item, [None, *key[1:]]) == pytest.approx(0.8)
    assert fam.score(item, key[:2]) == pytest.approx(0.4)  # не дошёл до конца — остальное 0
    assert fam.score(item, [*key, 0]) == 0.0
    assert fam.score(item, "ответ") == 0.0
    assert fam.score(item, None) == 0.0


@pytest.mark.parametrize("domain", DOMAINS)
def test_metrics_step_has_single_anomaly(domain):
    for seed in SEEDS:
        item, world = build("incident_chain_outage", seed, domain)
        step = item.steps[0]
        rows = re.findall(r"^- (.+?) \(.+?\): (.+)$", step.stem, flags=re.M)
        outliers = []
        for title, vals in rows:
            v = [float(x) for x in vals.split(", ")]
            ref = statistics.mean(v[:-1])
            if abs(v[-1] - ref) / ref > 0.15:
                outliers.append(title)
        assert outliers == [step.options[step.key]], (domain, seed, rows)


@pytest.mark.parametrize("domain", DOMAINS)
def test_outage_chain_is_consistent(domain):
    for seed in SEEDS:
        item, world = build("incident_chain_outage", seed, domain)
        root, bug = item.meta["root"], item.meta["knobs"]["bug"]
        metrics, logs, code, arch, fix = item.steps
        # логи: своя (не upstream) ошибка — только у первопричины
        own = {
            m.group(1)
            for m in re.finditer(r"ERROR (\w+): (.+)", logs.stem)
            if "timeout" not in m.group(2) and "invalid field" not in m.group(2)
        }
        assert own == {root} and logs.options[logs.key] == root
        # код: дефект соответствует причине из логов, имени первопричины в коде нет
        lines = {int(n): s for n, s in re.findall(r"^\s*(\d+)  (.*)$", code.stem, flags=re.M)}
        bad = " ".join(lines[i] for i in code.key)
        assert ("return None" in bad) if bug == 0 else ("request_id" in bad)
        assert not any(named(root, s.stem) for s in (code, arch, fix))
        # архитектура: число входов gateway, задетых первопричиной
        assert arch.key == entries_hit(world, root) >= 1
        assert ("пул" if bug == 0 else "кеш") in fix.options[fix.key]


@pytest.mark.parametrize("domain", DOMAINS)
def test_latency_chain_is_consistent(domain):
    for seed in SEEDS:
        item, world = build("incident_chain_latency", seed, domain)
        src, cause = item.meta["root"], item.meta["knobs"]["cause"]
        metrics, logs, code, arch, fix = item.steps
        # метрики: у источника наибольший абсолютный рост p95
        growth = {
            s: int(b) - int(a)
            for s, a, b in re.findall(r"^- (\w+): (\d+) → (\d+)$", metrics.stem, flags=re.M)
        }
        assert max(growth, key=growth.get) == src == metrics.options[metrics.key]
        # логи → код → исправление согласованы по причине
        assert ("N+1" if cause == 0 else "без индекса") in logs.options[logs.key]
        lines = {int(n): s for n, s in re.findall(r"^\s*(\d+)  (.*)$", code.stem, flags=re.M)}
        bad = lines[code.key[0]]
        assert (
            ("SELECT" in bad and "for" in lines[code.key[0] - 1])
            if cause == 0
            else ("DROP INDEX" in bad)
        )
        assert ("одним запросом" if cause == 0 else "индекс") in fix.options[fix.key]
        # архитектура: запросы в секунду = RPS источника × запросов на вызов из журнала
        statements = logs.stem.count("statement:")
        assert arch.key == world.service(src).rps * statements
        assert not any(named(src, s.stem) for s in (logs, code, arch, fix))


def test_key_never_public_and_steps_reach_api():
    for fam in FAMILIES:
        item = check.build(fam, 7)
        pub = item.public()
        assert "key" not in pub and "meta" not in pub
        assert all("key" not in s and "meta" not in s for s in pub["steps"])
        out = NextOut(response_id=uuid.uuid4(), seq=1, **pub)
        assert out.steps is not None and len(out.steps) == 5
        ex = PlanExampleOut(skill=fam.skill, skill_type="thinking", family=fam.slug, level=4, **pub)
        assert ex.steps == pub["steps"]


def test_plain_items_have_no_steps():
    pub = check.build(registry.get("arch_blast_radius"), 7).public()
    assert "steps" not in pub


def test_bank_check_covers_chain_kind():
    assert check.check_bank(list(registry.REGISTRY.values()), check.TAXONOMY) == []
    no_chain = [f for f in registry.REGISTRY.values() if f.kind != Kind.chain]
    assert "нет семейства kind=chain" in check.check_bank(no_chain, None)


def test_spec_rejects_chain():
    with pytest.raises(ValidationError):
        FamilySpec.model_validate(
            {"title": "Цепочка", "skill": "python", "level": 3, "kind": "chain", "stem": "x"}
        )
