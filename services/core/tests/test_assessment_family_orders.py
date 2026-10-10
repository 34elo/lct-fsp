"""E43-9: «Сгенерировать задания» в «Допуске заданий» — заказ → очередь `ml.llm` → черновики."""

import sqlite3
import uuid
from pathlib import Path

import pytest
from app.assessment.models import FamilyOrder, FamilyRow
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from core_helpers import PASSWORD, register
from fsp_contracts import Envelope, parse_payload
from fsp_contracts.assessment import FamilyOrderGenerated
from fsp_contracts.commands import MlFamiliesGenerate
from fsp_contracts.registry import new_event
from fsp_platform.db import session_scope
from fsp_platform.messaging import QUEUES, Consumer
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import func, select

TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"
URL = "/admin/assessment/generate"


def _spec(i: int) -> dict:
    """Форма `exact` с ключом, как от генератора (мок LLM): `i` даёт разные формы."""
    return {
        "title": f"RPS #{i}",
        "kind": "exact",
        "stem": f"Сервис получает {{{{rps}}}} запросов в секунду. Сколько за {i + 1} мин?",
        "params": {"rps": {"min": 10, "max": 200, "step": 10}},
        "answer": f"rps * 60 * {i + 1}",
        "precision": 0,
    }


@pytest.fixture
async def seeded(factory):
    async with session_scope(factory) as s:
        await tax.sync(s, load_taxonomy(TAXONOMY))


def _admin(api) -> dict[str, str]:
    email = f"root-{uuid.uuid4().hex[:6]}@example.test"
    r = api.post("/auth/register", json={"email": email, "password": PASSWORD, "role": "candidate"})
    with sqlite3.connect(api.db_path) as con:
        con.execute("update users set role='fsp_admin' where email=?", (email,))
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _commands(api) -> list[Envelope]:
    with sqlite3.connect(api.db_path) as con:
        rows = con.execute(
            "select payload from outbox where type='ml.families.generate' order by id"
        ).fetchall()
    return [Envelope.model_validate_json(r[0]) for r in rows]


def _generated(order_id, specs, error=None) -> Envelope:
    return new_event(
        "ml.families.generated",
        "ml",
        FamilyOrderGenerated(order_id=order_id, specs=specs, model="mock", error=error),
    )


def _consumers(factory):
    from app.assessment import orders
    from app.assessment.config import load_config

    consumers = {"core.ingest": Consumer(QUEUES["core.ingest"])}
    orders.register(consumers, factory, load_config())
    return consumers["core.ingest"]


async def test_roles_required(api, seeded):
    body = {"skill": "python", "kind": "exact", "level": 3, "count": 3}
    assert api.post(URL, json=body).status_code == 401
    cand = register(api)
    assert api.post(URL, json=body, headers=cand).status_code == 403
    assert api.get(URL, headers=cand).status_code == 403
    assert _commands(api) == []


async def test_order_of_three_creates_three_drafts_and_redelivery_is_noop(api, factory, seeded):
    adm = _admin(api)
    body = {"skill": "python", "kind": "exact", "level": 3, "count": 3}
    r = api.post(URL, json=body, headers=adm)
    assert r.status_code == 202, r.text
    order = r.json()
    assert order["status"] == "queued" and order["duplicate"] is False

    # повторный клик: тот же заказ, вторая команда в очередь не уходит
    again = api.post(URL, json=body, headers=adm)
    assert again.status_code == 202 and again.json()["id"] == order["id"]
    assert again.json()["duplicate"] is True
    (cmd,) = _commands(api)
    p = parse_payload(cmd)
    assert isinstance(p, MlFamiliesGenerate) and p.n == 3 and p.skill_type
    assert str(p.order_id) == order["id"]

    consumer = _consumers(factory)
    oid = uuid.UUID(order["id"])
    await consumer.dispatch(new_event("ml.families.started", "ml", _started(oid)))
    assert api.get(URL, headers=adm).json()["items"][0]["status"] == "running"

    event = _generated(oid, [_spec(i) for i in range(3)])
    await consumer.dispatch(event)
    await consumer.dispatch(Envelope.model_validate(event.model_dump(mode="json")))  # повтор
    await consumer.dispatch(_generated(oid, [_spec(i) for i in range(3, 6)]))  # опоздавший ответ

    async with session_scope(factory) as s:
        rows = list(await s.scalars(select(FamilyRow).where(FamilyRow.source == "llm")))
        assert len(rows) == 3
        assert all(r.status == "draft" and r.key_status == "draft" for r in rows)
        assert {r.spec["llm"]["order_id"] for r in rows} == {order["id"]}
    out = api.get(URL, headers=adm).json()
    assert out["items"][0]["status"] == "done" and out["items"][0]["created"] == 3
    assert out["used_today"] == 1 and out["limit"] == 20
    # черновики видны в «Допуске заданий» во вкладке «Черновики»
    drafts = api.get("/admin/families", params={"status": "draft"}, headers=adm).json()
    assert sum(1 for f in drafts if f["source"] == "llm") == 3


def _started(oid):
    from fsp_contracts.assessment import FamilyOrderStarted

    return FamilyOrderStarted(order_id=oid)


async def test_rejections_and_failure_counted(api, factory, seeded):
    adm = _admin(api)
    a = api.post(
        URL, json={"skill": "python", "kind": "exact", "level": 2, "count": 3}, headers=adm
    )
    b = api.post(URL, json={"skill": "sql", "kind": "choice", "level": 2, "count": 2}, headers=adm)
    consumer = _consumers(factory)
    dup = _spec(0)
    bad = {**_spec(1), "kind": "choice"}
    await consumer.dispatch(_generated(uuid.UUID(a.json()["id"]), [dup, dup, bad]))
    await consumer.dispatch(_generated(uuid.UUID(b.json()["id"]), [], error="llm_disabled"))
    items = {i["id"]: i for i in api.get(URL, headers=adm).json()["items"]}
    done = items[a.json()["id"]]
    assert done["status"] == "done" and done["created"] == 1
    assert done["rejected"] == {"duplicate": 1, "kind_mismatch": 1}
    failed = items[b.json()["id"]]
    assert failed["status"] == "failed" and failed["error"] == "llm_disabled"


async def test_validation_unknown_skill_and_daily_limit(api, factory, seeded):
    adm = _admin(api)
    body = {"skill": "python", "kind": "exact", "level": 3, "count": 11}
    assert api.post(URL, json=body, headers=adm).status_code == 422
    assert api.post(URL, json={**body, "count": 1, "level": 6}, headers=adm).status_code == 422
    r = api.post(URL, json={**body, "skill": "no_such_skill", "count": 1}, headers=adm)
    assert r.status_code == 422 and r.json()["code"] == "unknown_skill"

    api.app.state.settings.family_orders_per_day = 2
    for lvl in (1, 2):
        assert (
            api.post(URL, json={**body, "count": 1, "level": lvl}, headers=adm).status_code == 202
        )
    r = api.post(URL, json={**body, "count": 1, "level": 3}, headers=adm)
    assert r.status_code == 429 and r.json()["code"] == "daily_limit"
    out = api.get(URL, headers=adm).json()
    assert (out["used_today"], out["limit"], out["max_count"]) == (2, 2, 10)
    async with session_scope(factory) as s:
        assert await s.scalar(select(func.count()).select_from(FamilyOrder)) == 2
        n = await s.scalar(
            select(func.count())
            .select_from(OutboxRecord)
            .where(OutboxRecord.type == "ml.families.generate")
        )
        assert n == 2
