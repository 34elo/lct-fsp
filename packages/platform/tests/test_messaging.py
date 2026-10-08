import asyncio
from types import SimpleNamespace

import pytest
from fsp_contracts import new_envelope
from fsp_contracts.commands import COMMANDS, LLM_MAX_PRIORITY
from fsp_platform.db import Base, make_engine, make_session_factory, session_scope
from fsp_platform.messaging import (
    COMMANDS_EXCHANGE,
    EVENTS_EXCHANGE,
    QUEUES,
    RETRY_HEADER,
    Consumer,
    _retry_or_dead_letter,
    idempotent,
    route,
)
from fsp_platform.outbox import InboxRecord, OutboxRelay, add_to_outbox
from sqlalchemy import func, select


@pytest.fixture
async def factory(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield make_session_factory(engine)
    await engine.dispose()


def test_every_command_queue_is_declared():
    for spec in COMMANDS.values():
        q = QUEUES[spec.queue]
        assert q.exchange is COMMANDS_EXCHANGE and spec.queue in q.bindings


def test_llm_queue_priority_and_prefetch():
    q = QUEUES["ml.llm"]
    assert q.prefetch == 1 and q.arguments()["x-max-priority"] == LLM_MAX_PRIORITY
    assert q.arguments()["x-dead-letter-exchange"] == "dlx"
    assert [q.retry_queue(i) for i in range(3)] == [
        "ml.llm.retry.5s",
        "ml.llm.retry.30s",
        "ml.llm.retry.2m",
    ]
    assert q.dlq == "ml.llm.dlq"


def test_route_command_and_event():
    ex, key, prio = route(new_envelope("ml.resume.parse", "core"))
    assert (ex, key, prio) == (COMMANDS_EXCHANGE, "ml.llm", 9)
    ex, key, prio = route(new_envelope("offer.sent", "core"))
    assert (ex, key, prio) == (EVENTS_EXCHANGE, "offer.sent", None)


async def test_dispatch_by_type_and_skip_unknown():
    c = Consumer(QUEUES["core.handlers"])
    got = []

    @c.on("offer.sent", "offer.viewed")
    async def h(env):
        got.append(env.type)

    await c.dispatch(new_envelope("offer.sent", "core"))
    await c.dispatch(new_envelope("vacancy.closed", "core"))
    assert got == ["offer.sent"]


class FakeMessage:
    def __init__(self, retry=None):
        self.headers = {} if retry is None else {RETRY_HEADER: retry}
        self.body = b"{}"
        self.content_type = "application/json"
        self.message_id = "m"
        self.correlation_id = "c"
        self.raw_message = SimpleNamespace(priority=9, type="ml.resume.parse")
        self.acked = self.nacked = False

    async def ack(self):
        self.acked = True

    async def nack(self, requeue=True):
        self.nacked = not requeue


class FakeBroker:
    def __init__(self):
        self.published = []

    async def publish(self, body, **kw):
        self.published.append(kw)


@pytest.mark.parametrize("attempt,queue", [(None, "ml.llm.retry.5s"), (2, "ml.llm.retry.2m")])
async def test_failure_goes_to_retry_queue_with_counter(attempt, queue):
    b, m = FakeBroker(), FakeMessage(attempt)
    env = new_envelope("ml.resume.parse", "core")
    await _retry_or_dead_letter(b, QUEUES["ml.llm"], m, env, RuntimeError())
    assert m.acked and not m.nacked
    (kw,) = b.published
    assert kw["queue"] == queue and kw["headers"][RETRY_HEADER] == (attempt or 0) + 1
    assert kw["priority"] == 9 and kw["persist"] is True


async def test_after_three_retries_goes_to_dlq():
    b, m = FakeBroker(), FakeMessage(3)
    await _retry_or_dead_letter(b, QUEUES["ml.llm"], m, new_envelope("x", "core"), RuntimeError())
    assert m.nacked and not m.acked and b.published == []


async def test_idempotent_handler_redelivery_has_no_effect(factory):
    effects = []

    @idempotent(factory, "test.handler")
    async def handler(env, session):
        effects.append(env.message_id)

    env = new_envelope("offer.sent", "core")
    await handler(env)
    await handler(env)
    assert effects == [env.message_id]
    async with factory() as s:
        assert (await s.execute(select(func.count()).select_from(InboxRecord))).scalar() == 1


async def test_relay_loop_publishes_new_outbox_rows(factory):
    published = asyncio.Queue()

    async def publish(env):
        await published.put(env)

    relay = OutboxRelay(factory, publish, poll_interval=0.05)
    task = asyncio.create_task(relay.run())
    try:
        env = new_envelope("offer.sent", "core")
        async with session_scope(factory) as s:
            await add_to_outbox(s, env)
        got = await asyncio.wait_for(published.get(), 1)
        assert got.message_id == env.message_id
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
