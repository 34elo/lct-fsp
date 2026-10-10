"""E43-9: заказ заданий из админки через очередь `ml.llm` (`ml.families.generate`)."""

from uuid import uuid4

from fsp_contracts import new_command, parse_payload
from fsp_contracts.commands import COMMANDS, MlFamiliesGenerate
from fsp_contracts.ml import FamilyGenerateResponse
from fsp_ml.handlers import families_generate_llm, handle
from fsp_ml.llm import LlmError


def _cmd(n: int = 7, kind: str = "choice"):
    p = MlFamiliesGenerate(order_id=uuid4(), skill="python", kind=kind, level=3, n=n)
    env, _ = new_command("ml.families.generate", "core", p)
    return env, p


def test_lowest_priority_in_llm_queue():
    llm = [s.priority or 0 for s in COMMANDS.values() if s.queue == "ml.llm"]
    assert COMMANDS["ml.families.generate"].priority == min(llm) == 0


def test_fake_returns_started_then_n_distinct_specs():
    env, p = _cmd(n=7)
    started, done = handle(env)
    assert (started.type, done.type) == ("ml.families.started", "ml.families.generated")
    res = parse_payload(done)
    assert res.order_id == p.order_id and res.error is None
    assert len(res.specs) == 7
    assert len({s["stem"] for s in res.specs}) == 7  # заглушка не даёт дублей
    assert all(s["kind"] == "choice" and s["skill"] == "python" for s in res.specs)


async def test_llm_chunks_by_five_and_keeps_partial_on_error():
    env, p = _cmd(n=7)
    calls = []

    async def gen(req):
        calls.append(req.n)
        if len(calls) == 2:
            raise LlmError("llm_unavailable", "нет")
        return FamilyGenerateResponse(specs=[{"stem": str(i)} for i in range(req.n)], model="q")

    res = parse_payload(await families_generate_llm(env, p, generate=gen))
    assert calls == [5, 2]
    assert len(res.specs) == 5 and res.error is None and res.model == "q"


async def test_llm_disabled_or_failed_gives_error():
    env, p = _cmd(n=3)
    res = parse_payload(await families_generate_llm(env, p, generate=None))
    assert res.error == "llm_disabled" and res.specs == []

    async def boom(req):
        raise LlmError("llm_invalid", "x")

    res = parse_payload(await families_generate_llm(env, p, generate=boom))
    assert res.error == "llm_invalid" and res.specs == []
