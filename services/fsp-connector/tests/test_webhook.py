import json
from datetime import UTC, datetime
from uuid import uuid4

import fakeredis
import httpx
import pytest
from fastapi import FastAPI
from fsp_connector.config import Settings
from fsp_connector.models import FspLink, WebhookLog, metadata
from fsp_connector.sync import SyncService
from fsp_connector.webhook import router, sign
from fsp_platform.app import create_app
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import func, select

SECRET = "s3"


@pytest.fixture
async def env(tmp_path, adapter):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    factory = make_session_factory(engine)
    app: FastAPI = create_app("fsp-connector-test")
    app.include_router(router)
    app.state.settings = Settings(fsp_webhook_secret=SECRET)
    app.state.session_factory = factory
    app.state.redis = fakeredis.FakeAsyncRedis()
    app.state.sync = SyncService(adapter, factory)
    cid = uuid4()
    async with session_scope(factory) as s:
        s.add(FspLink(candidate_id=cid, participant_id="p-anya", verified=True, method="oauth"))
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    yield client, factory
    await client.aclose()
    await engine.dispose()


def _body(event_id="e1", participant="p-anya") -> bytes:
    return json.dumps(
        {
            "event_id": event_id,
            "type": "result.published",
            "participant_id": participant,
            "competition_id": "c1",
            "occurred_at": datetime.now(UTC).isoformat(),
        }
    ).encode()


async def _post(client, body, sig=None):
    return await client.post(
        "/integrations/fsp/webhook",
        content=body,
        headers={"X-Signature": sig if sig is not None else sign(SECRET, body)},
    )


async def _outbox(factory) -> int:
    async with factory() as s:
        return await s.scalar(select(func.count()).select_from(OutboxRecord))


async def test_bad_or_missing_signature_is_rejected(env):
    client, factory = env
    body = _body()
    assert (await _post(client, body, "sha256=deadbeef")).status_code == 401
    r = await client.post("/integrations/fsp/webhook", content=body)
    assert r.status_code == 401
    assert await _outbox(factory) == 0
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(WebhookLog)) == 0


async def test_valid_webhook_syncs_linked_participant(env):
    client, factory = env
    r = await _post(client, _body())
    assert r.status_code == 200 and r.json()["status"] == "processed"
    assert await _outbox(factory) > 0
    async with factory() as s:
        row = await s.get(WebhookLog, "e1")
        assert row is not None and row.processed_at is not None


async def test_redelivery_is_idempotent(env):
    client, factory = env
    body = _body()
    await _post(client, body)
    count = await _outbox(factory)
    r = await _post(client, body)
    assert r.json() == {"status": "duplicate"}
    assert await _outbox(factory) == count


async def test_unknown_participant_is_acknowledged_without_events(env):
    client, factory = env
    r = await _post(client, _body("e2", "p-nobody"))
    assert r.status_code == 200 and r.json()["synced"] is False
    assert await _outbox(factory) == 0


async def test_invalid_body_422(env):
    client, _ = env
    body = b'{"x": 1}'
    assert (await _post(client, body)).status_code == 422
