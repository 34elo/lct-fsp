"""ml-worker-llm (очередь ml.llm, prefetch=1) и ml-worker-code (ml.code).

Запуск: `python -m fsp_ml.worker llm|code`. Сейчас работает только `ML_FAKE=true`
(фикстуры, `fsp_ml/fake.py`); реальные модели подключаются задачами E3-*, E10-*.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys

import structlog
from fsp_contracts import Envelope
from fsp_platform.logging import configure_logging
from fsp_platform.messaging import QUEUES, Consumer, declare_topology, make_broker, publish_envelope

from fsp_ml.config import Settings
from fsp_ml.handlers import HANDLERS, handle

log = structlog.get_logger()

ROLE_QUEUE = {"llm": "ml.llm", "code": "ml.code"}


class MlWorker:
    def __init__(self, role: str, settings: Settings | None = None):
        self.settings = settings or Settings()
        if not self.settings.ml_fake:
            raise RuntimeError("Реальные модели ещё не подключены: запускайте с ML_FAKE=true")
        self.queue = ROLE_QUEUE[role]
        self.broker = make_broker(self.settings.rabbitmq_url)
        self.consumer = Consumer(QUEUES[self.queue])
        for type_, _ in _commands_for(self.queue):
            self.consumer.on(type_)(self._on_command)

    async def _on_command(self, envelope: Envelope) -> None:
        for result in handle(envelope):
            await publish_envelope(self.broker, result)
        log.info("ml_command_done", type=envelope.type, fake=True)

    async def start(self) -> None:
        self.consumer.attach(self.broker)
        await self.broker.connect()
        await declare_topology(self.broker)
        await self.broker.start()
        log.info("ml_worker_started", queue=self.queue, fake=True)

    async def stop(self) -> None:
        await self.broker.stop()


def _commands_for(queue: str):
    from fsp_contracts.commands import COMMANDS

    return [(t, s) for t, s in COMMANDS.items() if s.queue == queue and t in HANDLERS]


async def main(role: str) -> None:
    settings = Settings(service_name=f"ml-worker-{role}")
    configure_logging(settings.service_name, settings.log_level)
    worker = MlWorker(role, settings)
    await worker.start()
    try:
        await asyncio.Event().wait()
    finally:
        await worker.stop()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "llm"))
