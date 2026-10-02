from app.config import Settings
from app.scheduler import SCHEDULE, build_scheduler, send_job
from app.worker import CORE_QUEUES, Worker
from faststream.rabbit import TestRabbitBroker
from fsp_contracts.commands import COMMANDS
from fsp_platform.messaging import COMMANDS_EXCHANGE, durable_queue, make_broker


def test_schedule_matches_messaging_doc():
    assert set(SCHEDULE) <= set(COMMANDS)
    assert SCHEDULE["offers.expire"] == 300 and SCHEDULE["cleanup"] == 86400
    jobs = {j.id for j in build_scheduler(make_broker("amqp://x/")).get_jobs()}
    assert jobs == set(SCHEDULE)


async def test_send_job_goes_to_core_jobs_and_fsp_sync():
    broker = make_broker("amqp://guest:guest@localhost:5672/")
    got: dict[str, list[str]] = {"core.jobs": [], "fsp.sync": []}

    @broker.subscriber(durable_queue("core.jobs"), COMMANDS_EXCHANGE)
    async def jobs(msg: dict):
        got["core.jobs"].append(msg["type"])

    @broker.subscriber(durable_queue("fsp.sync"), COMMANDS_EXCHANGE)
    async def fsp(msg: dict):
        got["fsp.sync"].append(msg["type"])

    async with TestRabbitBroker(broker):
        await send_job(broker, "offers.expire")
        await send_job(broker, "fsp.sync_all")
    assert got == {"core.jobs": ["offers.expire"], "fsp.sync": ["fsp.sync_all"]}


def test_worker_consumes_all_core_queues():
    w = Worker(Settings(database_url="sqlite+aiosqlite:///:memory:"))
    assert set(w.consumers) == set(CORE_QUEUES)
    assert w.consumers["core.recompute"].spec.prefetch == 4
