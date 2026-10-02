import fakeredis
import pytest
from fastapi.testclient import TestClient
from fsp_platform.app import ProblemError, create_app
from fsp_platform.locks import LockNotAcquired, acquire, redis_lock, release
from fsp_platform.ratelimit import RateLimiter


@pytest.fixture
def redis():
    return fakeredis.FakeAsyncRedis()


async def test_limit_blocks_after_n_and_reports_retry_after(redis):
    rl = RateLimiter(redis)
    for i in range(3):
        r = await rl.hit("login:ip1", 3, 60)
        assert r.allowed and r.remaining == 2 - i
    r = await rl.hit("login:ip1", 3, 60)
    assert not r.allowed and 1 <= r.retry_after <= 61
    assert (await rl.hit("login:ip2", 3, 60)).allowed  # другой ключ независим


async def test_window_slides(redis, monkeypatch):
    import fsp_platform.ratelimit as m

    t = [1000.0]
    monkeypatch.setattr(m.time, "time", lambda: t[0])
    rl = RateLimiter(redis)
    assert (await rl.hit("k", 1, 10)).allowed
    assert not (await rl.hit("k", 1, 10)).allowed
    t[0] += 11
    assert (await rl.hit("k", 1, 10)).allowed


def test_check_raises_429_problem(redis):
    app = create_app("t")
    rl = RateLimiter(redis)

    @app.get("/x")
    async def x():
        await rl.check("x", 1, 60, code="login_rate_limited")
        return {}

    c = TestClient(app)
    assert c.get("/x").status_code == 200
    r = c.get("/x")
    assert r.status_code == 429 and r.json()["code"] == "login_rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    assert isinstance(ProblemError(429, "a", "b"), Exception)


async def test_lock_exclusive_and_owner_only_release(redis):
    token = await acquire(redis, "market_refresh", 30)
    assert token and await acquire(redis, "market_refresh", 30) is None
    assert not await release(redis, "market_refresh", "чужой")
    assert await release(redis, "market_refresh", token)
    assert await acquire(redis, "market_refresh", 30)


async def test_lock_context_releases_even_on_error(redis):
    with pytest.raises(RuntimeError):
        async with redis_lock(redis, "x", 30):
            with pytest.raises(LockNotAcquired):
                async with redis_lock(redis, "x", 30):
                    pass
            raise RuntimeError
    assert await acquire(redis, "x", 30)
