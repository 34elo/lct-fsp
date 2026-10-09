"""«Что требует вас» на главной админки (E39-29): счётчики очередей, права, недоступный ФСП."""

import asyncio
import sqlite3
import uuid

import httpx
from app.assessment.models import FamilyRow
from app.fsp.client import ConnectorClient
from core_helpers import register
from fsp_platform.db import make_engine, make_session_factory, session_scope

PENDING = [{"id": str(uuid.uuid4()), "status": "pending"} for _ in range(3)]


def admin(api):
    h = register(api, "employer")
    with sqlite3.connect(api.db_path) as con:
        con.execute("update users set role='fsp_admin'")
    return h


def counts(api, h) -> dict[str, int | None]:
    r = api.get("/admin/summary", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    out = {q["id"]: q["count"] for q in body["queues"]}
    assert body["total"] == sum(v or 0 for v in out.values())
    return out


def add_pilot_family(api):
    async def go():
        engine = make_engine(f"sqlite+aiosqlite:///{api.db_path}")
        async with session_scope(make_session_factory(engine)) as s:
            s.add(
                FamilyRow(
                    slug=f"t-{uuid.uuid4().hex[:8]}", kind="code", source="spec",
                    skill_id=uuid.uuid4(), skill_type="hard", level=1, b=0.0, status="pilot",
                )
            )  # fmt: skip
        await engine.dispose()

    asyncio.run(go())


def test_requires_fsp_admin(api):
    assert api.get("/admin/summary").status_code == 401
    for role in ("candidate", "employer"):
        assert api.get("/admin/summary", headers=register(api, role)).status_code == 403


def test_queues_order_and_fsp_unavailable(api):
    body = api.get("/admin/summary", headers=admin(api)).json()
    ids = [q["id"] for q in body["queues"]]
    assert ids == ["fsp_requests", "families", "skills", "companies", "complaints"]
    # connector не настроен — счётчик неизвестен, страница всё равно отвечает
    assert body["queues"][0]["count"] is None


def test_counts_follow_queues(api):
    h = admin(api)
    before = counts(api, h)
    emp = register(api, "employer")
    assert api.post("/companies", json={"name": "Acme Labs"}, headers=emp).status_code == 201
    add_pilot_family(api)
    after = counts(api, h)
    assert after["companies"] == before["companies"] + 1
    assert after["families"] == before["families"] + 1
    assert after["complaints"] == before["complaints"] == 0


def test_fsp_requests_from_connector(api):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        assert request.url.path == "/internal/registry/requests"
        return httpx.Response(200, json=PENDING)

    api.app.state.fsp_client = ConnectorClient(
        "http://fspc", "tok", transport=httpx.MockTransport(handler)
    )
    assert counts(api, admin(api))["fsp_requests"] == 3
    assert seen == [{"status": "pending"}]
