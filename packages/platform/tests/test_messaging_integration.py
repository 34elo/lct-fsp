"""Интеграция outbox → RabbitMQ → inbox на настоящих PostgreSQL и RabbitMQ.

Нужны FSP_TEST_PG_URL и FSP_TEST_AMQP_URL (поднимает `make test-integration`), иначе skip.
"""

import asyncio
import contextlib
import os
import time
import uuid

import pytest
from fsp_contracts import new_envelope
from fsp_platform.db import Base, make_engine, make_session_factory, session_scope
from fsp_platform.messaging import (
    EVENTS_EXCHANGE,
    RETRY_HEADER,
    Consumer,
    QueueSpec,
    declare_topology,
    idempotent,
    make_broker,
    publish_envelope,
)
from fsp_platform.outbox import (
    OUTBOX_NOTIFY_DDL,
    InboxRecord,
    OutboxRelay,
    add_to_outbox,
)
from sqlalchemy import Column, MetaData, String, Table, Uuid, func, insert, select, text

PG = os.getenv("FSP_TEST_PG_URL")
AMQP = os.getenv("FSP_TEST_AMQP_URL")
pytestmark = pytest.mark.skipif(not (PG and AMQP), reason="нет FSP_TEST_PG_URL/AMQP_URL")

meta = MetaData()
facts = Table("it_facts", meta, Column("id", Uuid, primary_key=True), Column("kind", String))
effects = Table("it_effects", meta, Column("id", Uuid, primary_key=True), Column("src", Uuid))


@pytest.fixture
async def factory():
    engine = make_engine(PG)
    async with engine.begin() as conn:
        for m in (Base.metadata, meta):
            await conn.run_sync(m.drop_all)
            await conn.run_sync(m.create_all)
        for stmt in OUTBOX_NOTIFY_DDL:
            await conn.execute(text(stmt))
    yield make_session_factory(engine)
    await engine.dispose()


@contextlib.asynccontextmanager
async def running(broker, specs, factory=None):
    await broker.connect()
    await declare_topology(broker, specs)
    await broker.start()
    task = None
    if factory is not None:
        relay = OutboxRelay(factory, lambda e: publish_envelope(broker, e), listen_dsn=PG)
        task = asyncio.create_task(relay.run())
    try:
        yield
    finally:
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for spec in specs:
            retries = [spec.retry_queue(i) for i in range(len(spec.retry_delays))]
            for name in (spec.name, spec.dlq, *retries):
                with contextlib.suppress(Exception):
                    queue = await broker.declare_queue(passive(name))
                    await queue.delete(if_unused=False, if_empty=False)
        await broker.stop()


def passive(name):
    from faststream.rabbit import RabbitQueue

    return RabbitQueue(name, declare=False)


def make_spec(key: str, **kw) -> QueueSpec:
    return QueueSpec(f"it.{uuid.uuid4().hex[:8]}", EVENTS_EXCHANGE, (key,), 4, **kw)


async def wait_for(pred, limit=5.0):
    deadline = time.monotonic() + limit
    while not pred():
        assert time.monotonic() < deadline, "не дождались"
        await asyncio.sleep(0.02)


async def test_event_from_transaction_reaches_handler_fast_and_once(factory):
    spec = make_spec("it.fact.created")
    broker = make_broker(AMQP)
    consumer = Consumer(spec)
    seen: list[float] = []

    @consumer.on("it.fact.created")
    @idempotent(factory, "it.effects")
    async def handler(env, session):
        await session.execute(
            insert(effects).values(id=uuid.uuid4(), src=uuid.UUID(env.payload["id"]))
        )
        seen.append(time.monotonic())

    consumer.attach(broker)
    async with running(broker, [spec], factory):
        await asyncio.sleep(0.2)  # relay подписался на LISTEN
        fact_id = uuid.uuid4()
        env = new_envelope("it.fact.created", "core", {"id": str(fact_id)})
        t0 = time.monotonic()
        async with session_scope(factory) as s:  # данные + outbox в одной транзакции
            await s.execute(insert(facts).values(id=fact_id, kind="x"))
            await add_to_outbox(s, env)
        await wait_for(lambda: seen, limit=2)
        assert seen[0] - t0 <= 1.0

        # повторная доставка того же конверта не меняет результат
        await publish_envelope(broker, env)
        await publish_envelope(broker, env)
        await asyncio.sleep(0.5)

    async with factory() as s:
        assert (await s.execute(select(func.count()).select_from(effects))).scalar() == 1
        assert (await s.execute(select(func.count()).select_from(InboxRecord))).scalar() == 1


async def test_failed_handler_is_retried_without_double_effect(factory):
    spec = make_spec("it.flaky", retry_delays=(("a", 50), ("b", 50), ("c", 50)))
    broker = make_broker(AMQP)
    consumer = Consumer(spec)
    calls = []

    @consumer.on("it.flaky")
    @idempotent(factory, "it.flaky")
    async def handler(env, session):
        calls.append(1)
        await session.execute(insert(effects).values(id=uuid.uuid4(), src=env.message_id))
        if len(calls) == 1:
            raise RuntimeError("сбой после записи — транзакция откатится")

    consumer.attach(broker)
    async with running(broker, [spec]):
        await publish_envelope(broker, new_envelope("it.flaky", "core"))
        await wait_for(lambda: len(calls) == 2)
        await asyncio.sleep(0.3)

    assert len(calls) == 2
    async with factory() as s:
        assert (await s.execute(select(func.count()).select_from(effects))).scalar() == 1


async def test_after_retries_message_lands_in_dlq(factory):
    spec = make_spec("it.poison", retry_delays=(("a", 50), ("b", 50), ("c", 50)))
    broker = make_broker(AMQP)
    consumer = Consumer(spec)
    calls = []

    @consumer.on("it.poison")
    async def handler(env):
        calls.append(1)
        raise RuntimeError

    consumer.attach(broker)
    async with running(broker, [spec]):
        await publish_envelope(broker, new_envelope("it.poison", "core"))
        await wait_for(lambda: len(calls) == 4)
        dlq = await broker.declare_queue(passive(spec.dlq))
        msg = None
        for _ in range(50):
            msg = await dlq.get(fail=False)
            if msg:
                break
            await asyncio.sleep(0.05)
        assert msg is not None and msg.headers[RETRY_HEADER] == 3
        await msg.ack()
    assert len(calls) == 4


async def test_priority_queue_serves_urgent_first():
    spec = QueueSpec(f"it.llm.{uuid.uuid4().hex[:8]}", EVENTS_EXCHANGE, ("it.llm",), 1, 10)
    broker = make_broker(AMQP)
    async with running(broker, [spec]):
        for prio in (1, 2, 9):
            await broker.publish(
                {"p": prio}, exchange=EVENTS_EXCHANGE, routing_key="it.llm", priority=prio
            )
        q = await broker.declare_queue(passive(spec.name))
        order = []
        for _ in range(3):
            m = await q.get(fail=False, timeout=2)
            order.append(m.priority)
            await m.ack()
    assert order == [9, 2, 1]
