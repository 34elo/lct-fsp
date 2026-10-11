"""«Объясни ответ» — причины по правилам, шаблон без LLM, доступ после завершения."""

import uuid
from pathlib import Path

import httpx
import pytest
from app.assessment import explain
from app.assessment.families.base import Item, Kind
from app.config import Settings
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from core_helpers import assert_foreign_is_404, register
from fsp_platform.db import session_scope

TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"


def _item(kind: Kind, key, **kw) -> Item:
    return Item(kind=kind, stem="Условие", key=key, time_limit_s=100, **kw)


def test_classify_rules():
    c = explain.classify
    assert c(_item(Kind.exact, 42), "42", 1.0, 9000).code == "correct"
    assert c(_item(Kind.exact, 42), None, 0.0, 9000).code == "skipped"
    assert c(_item(Kind.exact, 42), "7", 0.0, 500).code == "rushed"  # < 10 % лимита
    assert c(_item(Kind.exact, 42), "43", 0.0, 50_000).code == "off_by_one"
    assert c(_item(Kind.exact, 42), "50", 0.0, 50_000).code == "calc_error"
    assert c(_item(Kind.estimate, 1000), 3000, 0.5, 50_000).code == "close_estimate"
    assert c(_item(Kind.estimate, 1000), 50_000, 0.0, 50_000).code == "order_of_magnitude"
    assert c(_item(Kind.choice, 1, options=["a", "b"]), 0, 0.0, 50_000).code == "misconception"
    assert c(_item(Kind.find_bug, [3, 7]), [3], 0.5, 50_000).code == "partial"
    assert c(_item(Kind.find_bug, [3]), [4], 0.0, 50_000).code == "off_by_one"
    assert c(_item(Kind.find_bug, [3]), [9], 0.0, 50_000).code == "wrong_place"
    assert c(_item(Kind.order, [0, 1, 2]), [2, 1, 0], 0.0, 50_000).code == "order_mistake"
    steps = (_item(Kind.choice, 0, options=["a"]), _item(Kind.choice, 1, options=["a", "b"]))
    r = c(_item(Kind.chain, [0, 1], steps=steps), [0, 0], 0.5, 50_000)
    assert (r.code, r.detail) == ("chain_step", "шаг 2")


def test_misconception_is_deterministic_and_only_for_knowledge_reasons():
    r = explain.Reason("misconception")
    a = explain.misconception_for("python", 7, r)
    assert a and a == explain.misconception_for("python", 7, r)
    assert explain.misconception_for("python", 7, explain.Reason("rushed")) is None
    assert explain.misconception_for("no-such-skill", 7, r) is None
    text = explain.template_text(r, a)
    assert a["claim"] in text and a["truth"] in text


async def test_llm_text_fallbacks_and_success():
    item = _item(Kind.choice, 0, options=["a", "b"])
    r = explain.Reason("misconception")
    off = Settings(llm_enabled=False, ml_api_url="http://ml")
    assert await explain.llm_text(off, item, "python", r, None) is None
    on = Settings(llm_enabled=True, ml_api_url="http://ml")
    seen = {}

    def ok(req: httpx.Request) -> httpx.Response:
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"text": "Объяснение", "model": "qwen"})

    got = await explain.llm_text(on, item, "python", r, None, transport=httpx.MockTransport(ok))
    assert got and got.text == "Объяснение"
    assert "correct" not in seen["body"] and '"key"' not in seen["body"]  # ключа в запросе нет
    down = httpx.MockTransport(lambda req: httpx.Response(503))
    assert await explain.llm_text(on, item, "python", r, None, transport=down) is None


# --- API --------------------------------------------------------------------------------------


@pytest.fixture
async def taxonomy_loaded(factory):
    async with session_scope(factory) as s:
        await tax.sync(s, load_taxonomy(TAXONOMY))


def _start(api, h):
    return api.post(
        "/assessment/attempts",
        json={"profession": "backend", "declared_grade": "middle"},
        headers=h,
    ).json()["id"]


def _finish_wrong(api, h, aid) -> list[str]:
    ids = []
    for _ in range(40):
        body = api.get(f"/assessment/attempts/{aid}/next", headers=h).json()
        if body["done"]:
            return ids
        ids.append(body["response_id"])
        r = api.post(
            f"/assessment/attempts/{aid}/answers",
            json={"response_id": body["response_id"], "answer": "zzz"},
            headers=h,
        )
        assert r.status_code == 200
    raise AssertionError("попытка не завершилась")


async def test_explain_flow_template_without_llm(api, factory, taxonomy_loaded):
    h = register(api)
    aid = _start(api, h)
    first = api.get(f"/assessment/attempts/{aid}/next", headers=h).json()["response_id"]
    url = f"/assessment/attempts/{aid}/responses/{first}/explain"
    api.post(
        f"/assessment/attempts/{aid}/answers",
        json={"response_id": first, "answer": "zzz"},
        headers=h,
    )
    active = api.post(url, json={}, headers=h)  # попытка идёт: ключ не раскрываем
    assert active.status_code == 409 and active.json()["code"] == "attempt_active"

    _finish_wrong(api, h, aid)
    r = api.post(url, json={"self_reason": "guess"}, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["source"] == "template" and out["text"] and out["reason"]["code"] != "correct"
    assert out["self_reason"] == "guess" and out["self_reason_matches"] in (True, False)
    assert set(out) == {
        "response_id", "seq", "skill", "score", "reason", "misconception", "text",
        "source", "model", "self_reason", "self_reason_matches",
    }  # fmt: skip
    assert api.post(url, headers=h).status_code == 200  # тело необязательно
    bad = api.post(url, json={"self_reason": "evil"}, headers=h)
    assert bad.status_code == 422


async def test_explain_foreign_and_unknown_are_404(api, factory, taxonomy_loaded):
    owner, intruder = register(api), register(api)
    aid = _start(api, owner)
    rid = api.get(f"/assessment/attempts/{aid}/next", headers=owner).json()["response_id"]
    _finish_wrong(api, owner, aid)
    url = f"/assessment/attempts/{aid}/responses/{rid}/explain"
    assert_foreign_is_404(api, "POST", url, intruder)
    own = f"/assessment/attempts/{aid}/responses/{uuid.uuid4()}/explain"
    assert api.post(own, headers=owner).status_code == 404
    other = _start(api, intruder)
    other_rid = api.get(f"/assessment/attempts/{other}/next", headers=intruder).json()[
        "response_id"
    ]
    cross = f"/assessment/attempts/{aid}/responses/{other_rid}/explain"
    assert api.post(cross, headers=owner).status_code == 404  # ответ из другой попытки


async def test_explain_unanswered_and_rate_limit(api, factory, taxonomy_loaded):
    h = register(api)
    aid = _start(api, h)
    ids = _finish_wrong(api, h, aid)
    final = api.get(f"/assessment/attempts/{aid}", headers=h).json()["result"]
    assert [a["response_id"] for a in final["answers"]] == ids
    assert set(final["answers"][0]) == {"response_id", "seq", "skill", "score"}
    url = f"/assessment/attempts/{aid}/responses/{ids[0]}/explain"
    for _ in range(30):
        assert api.post(url, headers=h).status_code == 200
    limited = api.post(url, headers=h)
    assert limited.status_code == 429


async def test_review_hidden_while_active_and_own_only(api, factory, taxonomy_loaded):
    owner, intruder = register(api), register(api)
    aid = _start(api, owner)
    api.get(f"/assessment/attempts/{aid}/next", headers=owner)
    url = f"/assessment/attempts/{aid}/review"
    active = api.get(url, headers=owner)
    assert active.status_code == 409 and active.json()["code"] == "attempt_active"
    ids = _finish_wrong(api, owner, aid)
    assert_foreign_is_404(api, "GET", url, intruder)
    r = api.get(url, headers=owner)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [i["response_id"] for i in body["items"]] == ids
    first = body["items"][0]
    assert first["why"]
    # ни верных ответов, ни вариантов — ни в ответе, ни в шагах цепочки
    for it in body["items"]:
        assert "correct" not in it and "options" not in it
        for st in it["steps"] or []:
            assert "correct" not in st and "options" not in st
    assert first["reason"]["code"] != "correct" and first["skill_type"]


def test_review_part_has_no_key_or_options():
    item = _item(Kind.choice, 1, options=["секретный A", "секретный B"])
    part = explain._review_part(item, 0, 0.0, 5000)
    assert set(part) == {"kind", "stem", "yours", "reason"}
    assert part["yours"] == "секретный A" and "секретный B" not in str(part)
