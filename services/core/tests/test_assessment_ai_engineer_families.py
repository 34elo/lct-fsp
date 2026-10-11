"""Семейства для AI Engineer (витрина): LLM, RAG, промпты, ИИ в продукте."""

import uuid
from pathlib import Path
from random import Random

import pytest
from app.assessment import families as registry
from app.assessment import plan_preview
from app.assessment import selection as sel
from app.assessment.config import load_config
from app.assessment.families import ai_engineer, check
from app.assessment.models import Attempt
from app.assessment.world import DOMAINS, World
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from core_helpers import register
from fsp_contracts.assessment import TestGrade
from fsp_platform.db import session_scope

FAMILIES = ai_engineer.FAMILIES
SEEDS = check.seeds(60)
CFG = load_config()
TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"
CORE = {"llm", "rag", "prompt_engineering", "ai_product_sense"}


def build(slug: str, seed: int, domain: str = "rag_service"):
    world = World.from_seed(seed, domain)
    return registry.get(slug).generate(Random(seed), world), world


def test_registered_and_cover_core_skills():
    for fam in FAMILIES:
        assert registry.get(fam.slug) is fam and 1 <= fam.level <= 3
    assert {f.skill for f in FAMILIES} == CORE
    assert len({f.kind for f in FAMILIES}) >= 5


@pytest.mark.parametrize("domain", DOMAINS)
@pytest.mark.parametrize("fam", FAMILIES, ids=lambda f: f.slug)
def test_passes_check_in_every_domain(fam, domain):
    for seed in SEEDS:
        world = World.from_seed(seed, domain)
        item = fam.generate(Random(seed), world)
        assert check.check_item(fam, item) == [], (fam.slug, domain, seed)
        assert fam.generate(Random(seed), World.from_seed(seed, domain)) == item
        assert world.company in item.stem


def test_rag_domain_uses_rag_services():
    item, _ = build("llm_context_budget", 1)
    assert "generator" in item.stem
    item, _ = build("rag_retriever_find_bug", 1)
    assert "retriever" in item.stem


def test_chunk_config_key_is_best_feasible():
    for seed in SEEDS:
        item, _ = build("rag_chunk_config", seed)
        rows = []
        for opt in item.options:
            parts = opt.replace(",", "").split()
            chunk, k, recall = int(parts[1]), int(parts[4]), float(parts[6])
            rows.append((chunk * k <= item.meta["budget"], recall))
        feasible = [i for i, (ok, _) in enumerate(rows) if ok]
        assert item.key == max(feasible, key=lambda i: rows[i][1])
        # лучший recall в таблице нарушает ограничение — ловушка «просто взять максимум»
        assert not rows[max(range(len(rows)), key=lambda i: rows[i][1])][0]


def test_retriever_find_bug_mutant_changes_output():
    seen = set()
    for seed in SEEDS:
        item, _ = build("rag_retriever_find_bug", seed)
        assert check.run_python(item.meta["exec_ok"]) != check.run_python(item.meta["exec_bug"])
        seen.add(item.meta["mutant"])
    assert seen == {"skip_first", "sum", "asc", "off_by_one", "no_add", "break", "assign"}


def test_prompt_find_bug_partial_credit():
    fam = registry.get("prompt_rag_find_bug")
    for seed in SEEDS:
        item, _ = build("prompt_rag_find_bug", seed)
        if len(item.key) == 2:
            assert fam.score(item, item.key[:1]) == 0.5
            assert fam.score(item, [1]) == 0.0  # строка-приветствие верна всегда
            break
    else:  # pragma: no cover
        pytest.fail("нет варианта с двумя дефектами")


@pytest.mark.parametrize("grade", list(TestGrade))
def test_plan_for_ai_engineer_has_core_sections(grade):
    role = next(r for r in load_taxonomy(TAXONOMY).roles if r.slug == "ai_engineer")
    types = {s: t.value for s, t in load_taxonomy(TAXONOMY).skill_types.items()}
    available = {f.skill for f in registry.REGISTRY.values() if sel.level_ok(f.level, grade, CFG)}
    sections = sel.build_plan(role.skills, types, grade, CFG, available=available)
    assert CORE <= {s.skill for s in sections}
    out = plan_preview.preview(role.skills, types, grade, CFG, "rag_service")
    assert out["examples"] and all("key" not in ex for ex in out["examples"])


async def test_ai_engineer_attempt_starts(api, factory):
    async with session_scope(factory) as s:
        await tax.sync(s, load_taxonomy(TAXONOMY))
    h = register(api)
    r = api.post(
        "/assessment/attempts",
        json={"profession": "ai_engineer", "declared_grade": "middle"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    async with session_scope(factory) as s:
        att = await s.get(Attempt, uuid.UUID(aid))
        assert CORE <= {sec["skill"] for sec in att.plan["sections"]}
        assert att.plan["domain"] == "rag_service"
    body = api.get(f"/assessment/attempts/{aid}/next", headers=h).json()
    assert body["done"] is False and body["stem"]
