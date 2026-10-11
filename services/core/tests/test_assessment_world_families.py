"""Семейства по миру — архитектура, данные, логи, SQL, SJT."""

import re
import statistics
from random import Random

import pytest
from app.assessment import families as registry
from app.assessment.families import check, world_tasks
from app.assessment.world import DOMAINS, World

FAMILIES = world_tasks.FAMILIES
SEEDS = check.seeds(60)


def build(slug: str, seed: int, domain: str):
    fam = registry.get(slug)
    world = World.from_seed(seed, domain)
    return fam.generate(Random(seed), world), world


def test_registered():
    for fam in FAMILIES:
        assert registry.get(fam.slug) is fam


@pytest.mark.parametrize("domain", DOMAINS)
@pytest.mark.parametrize("fam", FAMILIES, ids=lambda f: f.slug)
def test_passes_check_in_every_domain(fam, domain):
    for seed in SEEDS:
        world = World.from_seed(seed, domain)
        item = fam.generate(Random(seed), world)
        assert check.check_item(fam, item) == [], (fam.slug, domain, seed)
        assert fam.generate(Random(seed), World.from_seed(seed, domain)) == item
        assert world.company in item.stem


@pytest.mark.parametrize("domain", DOMAINS)
def test_blast_radius_counts_transitive_app_callers(domain):
    for seed in SEEDS:
        item, world = build("arch_blast_radius", seed, domain)
        down = item.meta["down"]
        app = {n.name for n in world.nodes if n.kind in ("api", "worker")}
        assert item.key == len(app & set(world.impacted_by(down))) >= 1


@pytest.mark.parametrize("domain", DOMAINS)
def test_start_order_is_dependency_chain(domain):
    for seed in SEEDS:
        item, world = build("arch_start_order", seed, domain)
        chain = [item.options[i] for i in item.key]
        for later, earlier in zip(chain[1:], chain, strict=False):
            # каждый следующий узел транзитивно зависит от предыдущего → порядок единственный
            assert later in world.impacted_by(earlier)


@pytest.mark.parametrize("domain", DOMAINS)
def test_sql_key_equals_sqlite(domain):
    for slug in ("sql_join_filter", "sql_left_join", "data_table_aggregate"):
        for seed in SEEDS[:20]:
            item, _ = build(slug, seed, domain)
            assert float(check.run_python(item.meta["exec"])) == item.key


@pytest.mark.parametrize("domain", DOMAINS)
def test_kpi_anomaly_is_unique_outlier(domain):
    for seed in SEEDS:
        item, _ = build("kpi_anomaly_day", seed, domain)
        series = {d: float(v) for d, v in re.findall(r"^(2026-09-\d\d): (\S+)$", item.stem, re.M)}
        med = statistics.median(series.values())
        worst = max(series, key=lambda d: abs(series[d] - med))
        assert item.options[item.key] == worst
        if "(доля)" in item.stem:  # выброс доли — только вниз
            assert series[worst] < med


@pytest.mark.parametrize("domain", DOMAINS)
def test_incident_root_cause_is_only_own_error(domain):
    for seed in SEEDS:
        item, world = build("incident_log_root_cause", seed, domain)
        logs = item.stem.split("Логи:\n")[1]
        own = {
            m.group(1)
            for m in re.finditer(r"ERROR (\w+): (.*)", logs)
            if "timeout" not in m.group(2) and not m.group(2).startswith("400")
        }
        assert own == {item.options[item.key]}
        assert world.impacted_by(item.options[item.key])


@pytest.mark.parametrize("slug", ["sjt_teamwork", "sjt_mentoring"])
def test_team_sjt_uses_team_and_orders_by_rating(slug):
    for seed in SEEDS:
        item, world = build(slug, seed, DOMAINS[seed % len(DOMAINS)])
        assert world.team[0].name in item.stem
        ratings = item.meta["ratings"]
        assert [ratings[i] for i in item.key] == sorted(ratings, reverse=True)
        assert "{" not in item.stem and all("{" not in o for o in item.options)


def test_key_never_public():
    for fam in FAMILIES:
        pub = check.build(fam, 7).public()
        assert "key" not in pub and "meta" not in pub
