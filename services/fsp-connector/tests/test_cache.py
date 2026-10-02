from datetime import date

import fakeredis
from fsp_connector.cache import CachedFspAdapter, part_key, results_key


class Counting:
    def __init__(self, inner):
        self.inner, self.calls = inner, []

    def __getattr__(self, name):
        fn = getattr(self.inner, name)

        async def wrapped(*a, **k):
            self.calls.append(name)
            return await fn(*a, **k)

        return wrapped


async def test_participant_and_results_cached(adapter):
    redis = fakeredis.FakeAsyncRedis()
    inner = Counting(adapter)
    c = CachedFspAdapter(inner, redis, ttl_seconds=600)
    p1 = await c.get_participant("p-anya")
    p2 = await c.get_participant("p-anya")
    assert p1 == p2 and inner.calls.count("get_participant") == 1
    assert await redis.ttl(part_key("p-anya")) > 0
    r1 = await c.get_results("p-anya")
    r2 = await c.get_results("p-anya")
    assert r1 == r2 and r1 and inner.calls.count("get_results") == 1
    await c.get_ranks("p-anya")  # из кеша карточки
    assert inner.calls.count("get_participant") == 1


async def test_since_bypasses_cache_and_invalidate(adapter):
    redis = fakeredis.FakeAsyncRedis()
    inner = Counting(adapter)
    c = CachedFspAdapter(inner, redis)
    await c.get_results("p-anya", since=date(2000, 1, 1))
    await c.get_results("p-anya", since=date(2000, 1, 1))
    assert inner.calls.count("get_results") == 2
    assert not await redis.exists(results_key("p-anya"))
    await c.get_results("p-anya")
    await c.get_participant("p-anya")
    await c.invalidate("p-anya")
    assert not await redis.exists(results_key("p-anya"), part_key("p-anya"))
