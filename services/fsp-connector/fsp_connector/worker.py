"""fsp-connector worker: обработчики очереди `fsp.sync` + relay outbox → RabbitMQ."""

from __future__ import annotations

import asyncio
import contextlib

from fsp_platform.db import make_engine, make_session_factory
from fsp_platform.logging import configure_logging
from fsp_platform.messaging import QUEUES, Consumer, declare_topology, make_broker, publish_envelope
from fsp_platform.outbox import OutboxRelay
from redis.asyncio import Redis

from fsp_connector import handlers
from fsp_connector.config import Settings
from fsp_connector.factory import build_adapter
from fsp_connector.sync import SyncService


async def main() -> None:
    settings = Settings(service_name="fsp-connector-worker")
    configure_logging(settings.service_name, settings.log_level)
    broker = make_broker(settings.rabbitmq_url)
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    redis = Redis.from_url(settings.redis_url)
    adapter = build_adapter(settings, redis)
    consumers = {"fsp.sync": Consumer(QUEUES["fsp.sync"])}
    handlers.register(consumers, factory, SyncService(adapter, factory), redis)
    for consumer in consumers.values():
        consumer.attach(broker)
    relay = OutboxRelay(
        factory,
        lambda env: publish_envelope(broker, env),
        listen_dsn=settings.database_url,
    )
    await broker.connect()
    await declare_topology(broker)
    await broker.start()
    task = asyncio.create_task(relay.run(), name="outbox-relay")
    try:
        await asyncio.Event().wait()
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await broker.stop()
        await getattr(adapter, "inner", adapter).aclose()
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
