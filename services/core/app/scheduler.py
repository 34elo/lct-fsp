"""core-scheduler: cron-команды в RabbitMQ (messaging.md §4). Запуск: `python -m app.scheduler`.

Условия вида «если были изменения» проверяет обработчик команды, а не расписание.
"""

from __future__ import annotations

import asyncio
import contextlib

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from faststream.rabbit import RabbitBroker
from fsp_contracts.commands import COMMANDS
from fsp_contracts.registry import new_command
from fsp_platform.logging import configure_logging
from fsp_platform.messaging import declare_topology, make_broker, publish_envelope

from app.config import Settings

log = structlog.get_logger()
PRODUCER = "core-scheduler"

# команда → период, секунды
SCHEDULE: dict[str, int] = {
    "offers.expire": 5 * 60,
    "active_status.expire": 60 * 60,
    "market.refresh": 2 * 60,
    "fsp.sync_all": 60 * 60,
    "company.rating": 60 * 60,
    "candidate_links.refresh": 10 * 60,
    "cleanup": 24 * 60 * 60,
    # >>> block1 (assessment, taxonomy, identity, candidates, graph, resumes)
    "taxonomy.professions.suggest": 7 * 24 * 60 * 60,  # E41-17
    # <<< block1
    # >>> block2 (matching, offers, vacancies, companies, consents, fsp, telegram, analytics)
    # <<< block2
}


async def send_job(broker: RabbitBroker, command: str) -> None:
    envelope, _ = new_command(command, PRODUCER, COMMANDS[command].model())
    try:
        await publish_envelope(broker, envelope)
    except Exception as exc:
        log.warning("job_publish_failed", command=command, error=type(exc).__name__)
        return
    log.info("job_sent", command=command)


def build_scheduler(broker: RabbitBroker) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    for command, seconds in SCHEDULE.items():
        scheduler.add_job(
            send_job,
            IntervalTrigger(seconds=seconds),
            args=(broker, command),
            id=command,
            coalesce=True,
            max_instances=1,
        )
    return scheduler


async def main() -> None:
    settings = Settings(service_name="core-scheduler")
    configure_logging(settings.service_name, settings.log_level)
    broker = make_broker(settings.rabbitmq_url)
    await broker.connect()
    await declare_topology(broker)
    scheduler = build_scheduler(broker)
    scheduler.start()
    log.info("core_scheduler_started", jobs=list(SCHEDULE))
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)
        await broker.stop()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
