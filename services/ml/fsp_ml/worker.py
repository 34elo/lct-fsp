"""ml-worker-llm (очередь ml.llm, prefetch=1) и ml-worker-code (ml.code).

Запуск: `python -m fsp_ml.worker llm|code`. `ML_FAKE=true` — фикстуры (`fsp_ml/fake.py`).
`ML_FAKE=false` — реальные обработчики, где они уже есть (`ml.resume.parse` через LLM, E3-3);
остальные команды до своих задач (E10-* и др.) отвечают фикстурами с предупреждением в логе.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from datetime import UTC, datetime

import structlog
from fsp_contracts import Envelope, parse_payload
from fsp_contracts.ui import JobProgress, new_ui_message
from fsp_platform.logging import configure_logging
from fsp_platform.messaging import (
    QUEUES,
    Consumer,
    declare_topology,
    make_broker,
    publish_envelope,
    publish_ui,
)
from fsp_platform.storage import ObjectStorage

from fsp_ml.config import Settings
from fsp_ml.handlers import HANDLERS, handle, resume_parse_llm
from fsp_ml.llm import LlmClient, OpenAiLlm
from fsp_ml.taxonomy import TaxonomyProvider

log = structlog.get_logger()

ROLE_QUEUE = {"llm": "ml.llm", "code": "ml.code"}


class MlWorker:
    def __init__(
        self,
        role: str,
        settings: Settings | None = None,
        *,
        llm: LlmClient | None = None,
        storage: ObjectStorage | None = None,
        taxonomy: TaxonomyProvider | None = None,
    ):
        s = self.settings = settings or Settings()
        self.fake = s.ml_fake
        if not self.fake and llm is None and not s.llm_base_url:
            raise RuntimeError("ML_FAKE=false: задайте LLM_BASE_URL или запускайте с ML_FAKE=true")
        self.queue = ROLE_QUEUE[role]
        self.broker = make_broker(s.rabbitmq_url)
        self.consumer = Consumer(QUEUES[self.queue])
        for type_, _ in _commands_for(self.queue):
            self.consumer.on(type_)(self._on_command)
        self.llm: LlmClient | None = None
        if not self.fake:
            self.llm = llm or OpenAiLlm(
                s.llm_base_url,
                s.llm_api_key,
                s.llm_model,
                timeout=s.llm_timeout,
                max_tokens=s.llm_max_tokens,
            )
            self.storage = storage or ObjectStorage(
                s.s3_endpoint, s.s3_access_key, s.s3_secret_key, s.s3_bucket
            )
            self.taxonomy = taxonomy or TaxonomyProvider(s.core_url, s.service_token_ml)

    async def _on_command(self, envelope: Envelope) -> None:
        if not self.fake and envelope.type == "ml.resume.parse":
            results = await self._resume_parse(envelope)
        else:
            if not self.fake:
                log.warning("ml_fake_fallback", type=envelope.type)
            results = handle(envelope)
        for result in results:
            await publish_envelope(self.broker, result)
        log.info("ml_command_done", type=envelope.type, fake=self.fake)

    async def _resume_parse(self, envelope: Envelope) -> list[Envelope]:
        p = parse_payload(envelope)
        assert self.llm is not None

        async def progress(stage: str, pct: int, message: str) -> None:
            data = JobProgress(
                job_id=p.resume_id, kind="resume", stage=stage, pct=pct, message=message
            )
            await publish_ui(self.broker, new_ui_message(p.candidate_id, "job.progress", data))

        return await resume_parse_llm(
            envelope,
            p,
            load=self.storage.get,
            llm=self.llm,
            taxonomy=self.taxonomy,
            model=self.settings.llm_model,
            today=datetime.now(UTC).date(),
            progress=progress,
        )

    async def start(self) -> None:
        self.consumer.attach(self.broker)
        await self.broker.connect()
        await declare_topology(self.broker)
        await self.broker.start()
        log.info("ml_worker_started", queue=self.queue, fake=self.fake)

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
