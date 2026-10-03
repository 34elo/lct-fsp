"""core-worker: подписчики очередей core + relay outbox.

Запуск: `python -m app.worker`. Обработчики регистрируют модули через `Worker.consumers`.
"""

from __future__ import annotations

import asyncio
import contextlib

import redis.asyncio
import structlog
from fsp_platform.db import make_engine, make_session_factory
from fsp_platform.logging import configure_logging
from fsp_platform.messaging import (
    QUEUES,
    Consumer,
    declare_topology,
    make_broker,
    publish_envelope,
    publish_ui,
)
from fsp_platform.outbox import OutboxRelay

from app.config import Settings
from app.graph import handlers as graph_handlers
from app.graph.embedding import MlEmbedder
from app.graph.trust import TrustConfig
from app.matching import handlers as matching_handlers
from app.matching.scoring import MatchConfig
from app.notifications import handlers as notification_handlers
from app.resumes import handlers as resume_handlers

log = structlog.get_logger()

CORE_QUEUES = (
    "core.ingest",
    "core.handlers",
    "core.recompute",
    "core.match",
    "core.jobs",
    "core.analytics",
)


class Worker:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.broker = make_broker(self.settings.rabbitmq_url)
        self.engine = make_engine(self.settings.database_url)
        self.session_factory = make_session_factory(self.engine)
        self.consumers = {name: Consumer(QUEUES[name]) for name in CORE_QUEUES}
        self.embedder = (
            MlEmbedder(
                self.settings.ml_api_url,
                model=self.settings.embed_model,
                dim=self.settings.embed_dim,
                timeout=self.settings.embed_timeout_seconds,
                redis=redis.asyncio.from_url(self.settings.redis_url),
            )
            if self.settings.ml_api_url
            else None
        )
        trust = TrustConfig.load(self.settings.scoring_config_path or None)
        graph_handlers.register(
            self.consumers,
            self.session_factory,
            trust,
            embedder=self.embedder,
        )
        matching_handlers.register(
            self.consumers,
            self.session_factory,
            MatchConfig.load(self.settings.scoring_config_path or None),
            trust,
        )
        resume_handlers.register(
            self.consumers, self.session_factory, lambda m: publish_ui(self.broker, m)
        )
        notification_handlers.register(
            self.consumers, self.session_factory, lambda m: publish_ui(self.broker, m)
        )
        self.relay = OutboxRelay(
            self.session_factory,
            lambda env: publish_envelope(self.broker, env),
            listen_dsn=self.settings.database_url,
        )
        self._relay_task: asyncio.Task | None = None

    async def start(self) -> None:
        for consumer in self.consumers.values():
            consumer.attach(self.broker)
        await self.broker.connect()
        await declare_topology(self.broker)
        await self.broker.start()
        self._relay_task = asyncio.create_task(self.relay.run(), name="outbox-relay")
        log.info("core_worker_started", queues=list(self.consumers))

    async def stop(self) -> None:
        if self._relay_task:
            self._relay_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._relay_task
        await self.broker.stop()
        if self.embedder is not None:
            await self.embedder.aclose()
        await self.engine.dispose()


async def main() -> None:
    settings = Settings(service_name="core-worker")
    configure_logging(settings.service_name, settings.log_level)
    worker = Worker(settings)
    await worker.start()
    try:
        await asyncio.Event().wait()
    finally:
        await worker.stop()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
