import pytest
from fsp_contracts import new_envelope
from fsp_platform.db import Base, make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord, add_to_outbox, claim_inbox, relay_once
from sqlalchemy import select


@pytest.fixture
async def factory(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield make_session_factory(engine)
    await engine.dispose()


async def test_outbox_written_with_transaction_and_relayed_once(factory):
    env = new_envelope("offer.sent", "core", {"a": 1})
    async with session_scope(factory) as s:
        await add_to_outbox(s, env)
    published = []

    async def publish(e):
        published.append(e)

    async with factory() as s:
        assert await relay_once(s, publish) == 1
    async with factory() as s:
        assert await relay_once(s, publish) == 0
    assert [e.message_id for e in published] == [env.message_id]


async def test_outbox_rolled_back_with_data(factory):
    with pytest.raises(RuntimeError):
        async with session_scope(factory) as s:
            await add_to_outbox(s, new_envelope("x", "core"))
            raise RuntimeError
    async with factory() as s:
        assert (await s.execute(select(OutboxRecord))).first() is None


async def test_failed_publish_keeps_unpublished(factory):
    async with session_scope(factory) as s:
        await add_to_outbox(s, new_envelope("x", "core"))

    async def boom(_):
        raise ConnectionError

    async with factory() as s:
        with pytest.raises(ConnectionError):
            await relay_once(s, boom)
    async with factory() as s:
        assert (await s.execute(select(OutboxRecord))).scalar_one().published_at is None


async def test_inbox_redelivery_is_skipped(factory):
    env = new_envelope("x", "core")
    async with session_scope(factory) as s:
        assert await claim_inbox(s, env.message_id, "h") is True
    async with session_scope(factory) as s:
        assert await claim_inbox(s, env.message_id, "h") is False
        assert await claim_inbox(s, env.message_id, "other") is True
