import json
from datetime import UTC, datetime

import httpx
import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message, Update, User
from fsp_bot.core_client import CoreClient, CoreError
from fsp_bot.handlers import build_router


def core_with(handler):
    return CoreClient("http://core", "tok", transport=httpx.MockTransport(handler))


async def test_core_client_sends_service_token_and_parses_problem():
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"] = req.headers["authorization"]
        if req.url.path == "/internal/tg/start":
            return httpx.Response(200, json={"missing_consents": ["pd"]})
        return httpx.Response(404, json={"code": "not_found", "detail": "x"})

    core = core_with(handler)
    assert (await core.start(1, 1, "u", None))["missing_consents"] == ["pd"]
    assert seen["auth"] == "Service tok"
    with pytest.raises(CoreError) as e:
        await core.profile(1)
    assert e.value.code == "not_found" and e.value.status == 404


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls: list = []

    async def make_request(self, bot, method, timeout=None):  # noqa: ASYNC109
        self.calls.append(method)
        if isinstance(method, SendMessage):
            return Message(
                message_id=1,
                date=datetime.now(UTC),
                chat=Chat(id=5, type="private"),
                text=method.text,
            )
        return True

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        pass


async def test_start_asks_missing_consents_and_stores_state(redis):
    calls = []

    def handler(req: httpx.Request):
        calls.append(req.url.path)
        if req.url.path == "/internal/tg/start":
            return httpx.Response(200, json={"missing_consents": ["pd"], "linked": False})
        return httpx.Response(204)

    session = FakeSession()
    bot = Bot("1:TEST", session=session)
    dp = Dispatcher(storage=RedisStorage(redis))
    dp.include_router(build_router(core_with(handler)))
    user = User(id=5, is_bot=False, first_name="A")
    msg = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=5, type="private"),
        from_user=user,
        text="/start ref_x",
        entities=[{"type": "bot_command", "offset": 0, "length": 6}],
    )
    await dp.feed_update(bot, Update(update_id=1, message=msg))
    texts = [c.text for c in session.calls if isinstance(c, SendMessage)]
    assert len(texts) == 2 and "согласие" in texts[1]
    assert calls == ["/internal/tg/start"]
    assert any("fsm:" in k.decode() for k in await redis.keys("*"))


async def test_magic_link_returns_url():
    def handler(req: httpx.Request):
        assert req.url.path == "/internal/auth/magic-link"
        assert json.loads(req.content) == {"tg_user_id": 5, "redirect": "/me"}
        return httpx.Response(200, json={"url": "https://web.test/auth/magic?token=t"})

    assert await core_with(handler).magic_link(5, "/me") == "https://web.test/auth/magic?token=t"
