"""publish_ui → обменник ui → эксклюзивная очередь UiHub → соединение пользователя.

Нужен FSP_TEST_AMQP_URL (поднимает `make test-integration`), иначе skip.
"""

import asyncio
import os
from uuid import uuid4

import pytest
from app.events_stream import UiHub
from fsp_contracts.ui import JobProgress, new_ui_message
from fsp_platform.messaging import make_broker, publish_ui

AMQP = os.getenv("FSP_TEST_AMQP_URL")
pytestmark = pytest.mark.skipif(not AMQP, reason="нет FSP_TEST_AMQP_URL")


def _msg(user_id):
    return new_ui_message(
        user_id,
        "job.progress",
        JobProgress(job_id=uuid4(), kind="resume", stage="parse", pct=5, message="тест"),
    )


async def test_ui_message_reaches_only_owner_and_queue_is_exclusive():
    hub = UiHub(AMQP)
    other_hub = UiHub(AMQP)
    await hub.start()
    await other_hub.start()
    publisher = make_broker(AMQP)
    await publisher.start()
    user, stranger = uuid4(), uuid4()
    q_user, q_stranger = hub.subscribe(user), hub.subscribe(stranger)
    q_other_instance = other_hub.subscribe(user)
    try:
        await publish_ui(publisher, _msg(user))
        seq, event, data = await asyncio.wait_for(q_user.get(), 5)
        assert event == "job.progress" and data["pct"] == 5
        # другой экземпляр core-api со своей очередью тоже получает копию (fan-out)
        await asyncio.wait_for(q_other_instance.get(), 5)
        assert q_stranger.empty()
    finally:
        await publisher.stop()
        await hub.stop()
        await other_hub.stop()
