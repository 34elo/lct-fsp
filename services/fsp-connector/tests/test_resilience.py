import httpx
import pytest
from fsp_connector.errors import FspBadResponse, FspNotFound, FspUnavailable
from fsp_connector.http_adapter import HttpFspAdapter
from fsp_connector.resilience import CircuitBreaker


async def no_sleep(_):
    return None


def make(handler, **kw):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://x")
    return HttpFspAdapter("http://x", "k", client=client, sleep=no_sleep, **kw)


PART = {"id": "p1", "last_name": "И", "first_name": "О"}


async def test_retries_then_success():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json=PART)

    a = make(handler, retries=3)
    assert (await a.get_participant("p1")).id == "p1"
    assert len(calls) == 3


async def test_exponential_backoff_and_exhaustion():
    sleeps = []

    async def sleep(d):
        sleeps.append(d)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(500)), base_url="http://x"
    )
    a = HttpFspAdapter("http://x", "k", client=client, sleep=sleep, retries=4, retry_base=0.1)
    with pytest.raises(FspUnavailable):
        await a.get_participant("p1")
    assert sleeps == [0.1, 0.2, 0.4]


async def test_no_retry_on_404_and_bad_schema():
    calls = []

    def nf(req):
        calls.append(1)
        return httpx.Response(404)

    with pytest.raises(FspNotFound):
        await make(nf).get_participant("p1")
    assert len(calls) == 1
    with pytest.raises(FspBadResponse):
        await make(lambda r: httpx.Response(200, json={"id": 1})).get_participant("p1")


async def test_transport_error_is_transient():
    def boom(req):
        raise httpx.ConnectError("down")

    with pytest.raises(FspUnavailable):
        await make(boom, retries=2).get_participant("p1")


async def test_circuit_breaker_opens_and_recovers():
    now = [0.0]
    breaker = CircuitBreaker(failures=5, open_seconds=30, clock=lambda: now[0])
    calls = []
    state = {"ok": False}

    def handler(req):
        calls.append(1)
        return httpx.Response(200, json=PART) if state["ok"] else httpx.Response(500)

    a = make(handler, retries=3, breaker=breaker)
    for _ in range(2):  # 3 + 2 сбоя = 5 подряд -> разомкнулся
        with pytest.raises(FspUnavailable):
            await a.get_participant("p1")
    n = len(calls)
    assert n == 5 and breaker.is_open
    with pytest.raises(FspUnavailable):  # источник не дёргаем
        await a.get_participant("p1")
    assert len(calls) == n
    now[0] = 31
    state["ok"] = True
    assert (await a.get_participant("p1")).id == "p1"
    assert not breaker.is_open
