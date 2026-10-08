"""E22-1: каркас assessment — семейства, мир, пересборка, попытка через API (assessment.md §3–4)."""

import uuid
from pathlib import Path
from random import Random

import pytest
from app.assessment import attempts
from app.assessment import families as registry
from app.assessment.families.base import (
    Item,
    Kind,
    score_estimate,
    score_exact,
    score_find_bug,
    score_order,
)
from app.assessment.models import Attempt, FamilyRow, Response
from app.assessment.world import World
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from core_helpers import assert_foreign_is_404, register
from fsp_platform.db import session_scope
from sqlalchemy import func, select

PUBLIC_FIELDS = {"done", "response_id", "seq", "kind", "stem", "options", "time_limit_s", "steps"}
TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"

# --- чистые функции ---------------------------------------------------------------------------


def test_world_is_deterministic_and_varies():
    assert World.from_seed(42) == World.from_seed(42)
    assert World.from_seed(7, "fintech").domain == "fintech"
    assert len({World.from_seed(s).company for s in range(50)}) > 3


def test_item_rebuild_is_deterministic():
    for fam in registry.REGISTRY.values():
        for seed in range(30):
            a = attempts.build_item(fam, seed, "ecommerce")
            b = attempts.build_item(fam, seed, "ecommerce")
            assert a == b
            assert fam.score(a, a.key) == 1.0
            assert "key" not in a.public() and "meta" not in a.public()


def test_seed_formula_stable():
    c, a, f = uuid.uuid4(), uuid.uuid4(), attempts.family_id("py_loop_sum")
    s = attempts.item_seed(c, a, f)
    assert s == attempts.item_seed(c, a, f) and 0 <= s < 2**63
    assert s != attempts.item_seed(c, uuid.uuid4(), f)
    assert attempts.family_id("py_loop_sum") == attempts.family_id("py_loop_sum")


def test_scorers_match_doc():
    assert score_exact(" Hello  World", "hello world") == 1.0
    assert score_exact(42, "42") == 1.0 and score_exact(42, None) == 0.0
    assert score_estimate(1000, 1500) == 1.0  # |log10 1.5| = 0.18
    assert score_estimate(1000, 3000) == 0.5  # 0.48
    assert score_estimate(1000, 5000) == 0.0  # 0.70
    assert score_estimate(1000, "abc") == 0.0
    assert score_order([0, 1, 2, 3], [0, 1, 2, 3]) == 1.0
    assert score_order([0, 1, 2, 3], [3, 2, 1, 0]) == 0.0  # D = D_max = 8
    assert score_order([0, 1, 2, 3], [1, 0, 2, 3]) == pytest.approx(1 - 2 / 8)
    assert score_find_bug([3, 7], [3, 7]) == 1.0
    assert score_find_bug([3, 7], [3]) == 0.5
    assert score_find_bug([3, 7], [3, 9]) == 0.0


def test_registry_rejects_duplicates_and_bad_level():
    fam = next(iter(registry.REGISTRY.values()))
    with pytest.raises(ValueError):
        registry.register(fam)

    class Bad:
        slug, kind, skill, skill_type, level = "bad", Kind.exact, "python", "hard", 9

        def generate(self, rng: Random, world: World) -> Item: ...

        def score(self, item, answer) -> float:
            return 0.0

    with pytest.raises(ValueError):
        registry.register(Bad())


# --- API --------------------------------------------------------------------------------------


@pytest.fixture
async def taxonomy_loaded(factory):
    async with session_scope(factory) as s:
        await tax.sync(s, load_taxonomy(TAXONOMY))


def _start(api, h, profession="backend", grade="middle"):
    return api.post(
        "/assessment/attempts", json={"profession": profession, "declared_grade": grade}, headers=h
    )


async def _key(factory, response_id: str):
    """Ключ пересобирается из `(family_id, seed)` — так же, как на сервере при проверке."""
    async with session_scope(factory) as s:
        resp = await s.get(Response, uuid.UUID(response_id))
        att = await s.get(Attempt, resp.attempt_id)
        row = await s.get(FamilyRow, resp.family_id)
    return attempts.build_item(registry.get(row.slug), resp.seed, att.plan["domain"]).key


async def test_attempt_flow_through_api(api, factory, taxonomy_loaded):
    h = register(api)
    r = _start(api, h)
    assert r.status_code == 201, r.text
    att = r.json()
    assert att["status"] == "active" and att["target"] >= 3
    aid = att["id"]

    seen = 0
    while True:
        nxt = api.get(f"/assessment/attempts/{aid}/next", headers=h)
        assert nxt.status_code == 200, nxt.text
        body = nxt.json()
        if body["done"]:
            break
        assert set(body) <= PUBLIC_FIELDS
        # повторный GET не выдаёт новое задание
        assert api.get(f"/assessment/attempts/{aid}/next", headers=h).json() == body
        key = await _key(factory, body["response_id"])
        a = api.post(
            f"/assessment/attempts/{aid}/answers",
            json={"response_id": body["response_id"], "answer": key, "rt_ms": 5000},
            headers=h,
        )
        assert a.status_code == 200 and a.json()["accepted"]
        seen += 1
        assert seen <= 20

    final = api.get(f"/assessment/attempts/{aid}", headers=h).json()
    # длину задаёт SPRT (E22-3): минимум 6, если банк позволяет; иначе решение по EAP
    assert final["status"] == "passed" and final["answered"] == seen
    assert seen >= att["target"] or final["low_confidence"]
    assert final["finished_at"] is not None
    async with session_scope(factory) as s:
        fams = (await s.execute(select(func.count()).select_from(FamilyRow))).scalar_one()
        assert fams == len(registry.REGISTRY)
        scores = list(await s.scalars(select(Response.score)))
        assert scores and all(sc == 1.0 for sc in scores)


async def test_repeat_answer_is_idempotent(api, factory, taxonomy_loaded):
    h = register(api)
    aid = _start(api, h).json()["id"]
    item = api.get(f"/assessment/attempts/{aid}/next", headers=h).json()
    url = f"/assessment/attempts/{aid}/answers"
    first = api.post(url, json={"response_id": item["response_id"], "answer": "wrong"}, headers=h)
    key = await _key(factory, item["response_id"])
    again = api.post(url, json={"response_id": item["response_id"], "answer": key}, headers=h)
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    async with session_scope(factory) as s:
        resp = await s.get(Response, uuid.UUID(item["response_id"]))
        assert resp.answer == "wrong" and resp.score == 0.0
    nxt = api.get(f"/assessment/attempts/{aid}/next", headers=h).json()
    assert nxt["response_id"] != item["response_id"] and nxt["seq"] == 2


async def test_empty_answer_moves_to_new_item(api, factory, taxonomy_loaded):
    """E35-7a: «Не знаю» (answer=null) не оставляет то же задание: следующее — другое."""
    h = register(api)
    aid = _start(api, h).json()["id"]
    url = f"/assessment/attempts/{aid}/answers"
    ids, stems = set(), []
    for _ in range(3):
        item = api.get(f"/assessment/attempts/{aid}/next", headers=h).json()
        if item["done"]:
            break
        assert item["response_id"] not in ids
        ids.add(item["response_id"])
        stems.append(item["stem"])
        r = api.post(url, json={"response_id": item["response_id"], "answer": None}, headers=h)
        assert r.status_code == 200 and r.json()["accepted"]
    assert len(ids) >= 2


async def test_foreign_attempt_is_404(api, factory, taxonomy_loaded):
    owner = register(api)
    aid = _start(api, owner).json()["id"]
    item = api.get(f"/assessment/attempts/{aid}/next", headers=owner).json()
    intruder = register(api)
    assert_foreign_is_404(api, "GET", f"/assessment/attempts/{aid}", intruder)
    assert_foreign_is_404(api, "GET", f"/assessment/attempts/{aid}/next", intruder)
    assert_foreign_is_404(
        api,
        "POST",
        f"/assessment/attempts/{aid}/answers",
        intruder,
        json={"response_id": item["response_id"], "answer": 1},
    )
    other = _start(api, intruder).json()["id"]
    assert_foreign_is_404(
        api,
        "POST",
        f"/assessment/attempts/{other}/answers",
        intruder,
        json={"response_id": item["response_id"], "answer": 1},
    )


async def test_attempt_checks(api, taxonomy_loaded, monkeypatch):
    h = register(api)
    assert _start(api, h, profession="designer").json()["code"] == "unknown_profession"
    assert _start(api, h).status_code == 201
    dup = _start(api, h)
    assert dup.status_code == 409 and dup.json()["code"] == "attempt_active"
    emp = register(api, role="employer")
    assert _start(api, emp).status_code == 403
    monkeypatch.setenv("EMAIL_VERIFICATION_REQUIRED", "true")
    r = _start(api, register(api), profession="qa")
    assert r.status_code == 403 and r.json()["code"] == "email_not_verified"
