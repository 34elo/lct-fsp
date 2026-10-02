from uuid import uuid4

import pytest
from faststream.rabbit import TestRabbitBroker
from fsp_contracts import commands as cmd
from fsp_contracts import new_command
from fsp_ml.config import Settings
from fsp_ml.worker import MlWorker
from fsp_platform.messaging import EVENTS_EXCHANGE, durable_queue


def test_worker_queues_and_prefetch():
    llm = MlWorker("llm", Settings(ml_fake=True))
    assert llm.consumer.spec.name == "ml.llm" and llm.consumer.spec.prefetch == 1
    assert set(llm.consumer.handlers) == {
        "ml.resume.parse",
        "ml.interview.grade",
        "ml.interview.generate",
        "ml.interview_kit.generate",
        "ml.skills.resolve",
        "ml.matches.explain",
        "ml.questions.generate",
    }
    assert set(MlWorker("code", Settings(ml_fake=True)).consumer.handlers) == {"ml.code.analyze"}


def test_worker_refuses_to_start_without_fake():
    with pytest.raises(RuntimeError):
        MlWorker("llm", Settings(ml_fake=False))


async def test_command_to_published_event():
    w = MlWorker("code", Settings(ml_fake=True))
    got: list[dict] = []

    @w.broker.subscriber(durable_queue("t.ml.code.completed", "ml.code.completed"), EVENTS_EXCHANGE)
    async def sink(msg: dict):
        got.append(msg)

    env, _ = new_command(
        "ml.code.analyze",
        "core",
        cmd.MlCodeAnalyze(analysis_id=uuid4(), candidate_id=uuid4(), github_login="demo"),
    )
    async with TestRabbitBroker(w.broker):
        await w.consumer.dispatch(env)  # как если бы команда пришла из ml.code
        await w.consumer.dispatch(env)  # повторная доставка
    assert [m["type"] for m in got] == ["ml.code.completed"] * 2
    assert got[0]["message_id"] == got[1]["message_id"]  # inbox получателя отбросит дубль
