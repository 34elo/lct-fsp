"""fsp-connector worker: relay outbox → RabbitMQ. Обработчики `fsp.sync` — E5-5."""

from __future__ import annotations

import asyncio
import contextlib

from fsp_platform.db import make_engine, make_session_factory
from fsp_platform.logging import configure_logging
from fsp_platform.messaging import declare_topology, make_broker, publish_envelope
from fsp_platform.outbox import OutboxRelay

from fsp_connector.config import Settings


async def main() -> None:
    settings = Settings(service_name="fsp-connector-worker")
    configure_logging(settings.service_name, settings.log_level)
    broker = make_broker(settings.rabbitmq_url)
    engine = make_engine(settings.database_url)
    relay = OutboxRelay(
        make_session_factory(engine),
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
        await engine.dispose()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
