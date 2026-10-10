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
        if req.url.path == "/internal/tg/linked":
            return httpx.Response(200, json={"linked": True})
        return httpx.Response(404, json={"code": "not_found", "detail": "x"})

    core = core_with(handler)
    assert await core.is_linked(1) is True
    assert seen["auth"] == "Service tok"
    with pytest.raises(CoreError) as e:
        await core.profile(1)
    assert e.value.code == "not_found" and e.value.status == 404


async def test_core_client_maps_transport_errors_to_core_error():
    def handler(req: httpx.Request):
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(CoreError) as e:
        await core_with(handler).is_linked(1)
    assert e.value.status == 503 and e.value.code == "core_unreachable"


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


async def run_start(redis, handler, text="/start", web="https://dash.test"):
    session = FakeSession()
    bot = Bot("1:TEST", session=session)
    dp = Dispatcher(storage=RedisStorage(redis))
    dp.include_router(build_router(core_with(handler), web_base_url=web))
    msg = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=5, type="private"),
        from_user=User(id=5, is_bot=False, first_name="A", username="ann"),
        text=text,
        entities=[{"type": "bot_command", "offset": 0, "length": 6}],
    )
    await dp.feed_update(bot, Update(update_id=1, message=msg))
    return [c for c in session.calls if isinstance(c, SendMessage)]


def kb_urls(call) -> list[str]:
    kb = call.reply_markup
    rows = getattr(kb, "inline_keyboard", None) or []
    return [b.url for row in rows for b in row if b.url]


async def test_start_without_code_unlinked_points_to_site(redis):
    paths = []

    def handler(req: httpx.Request):
        paths.append((req.method, req.url.path))
        return httpx.Response(200, json={"linked": False})

    sent = await run_start(redis, handler)
    assert len(sent) == 1 and "Зарегистрируйся на сайте" in sent[0].text
    assert kb_urls(sent[0]) == ["https://dash.test/me/profile"]
    assert paths == [("GET", "/internal/tg/linked")]  # аккаунт не создаётся


async def test_start_without_code_linked_says_already(redis):
    def handler(req: httpx.Request):
        return httpx.Response(200, json={"linked": True})

    sent = await run_start(redis, handler)
    assert len(sent) == 1 and "уже привязан" in sent[0].text


async def test_start_with_link_code_links_account(redis):
    seen = {}

    def handler(req: httpx.Request):
        assert req.url.path == "/internal/tg/link"
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"user_id": "u", "linked": True})

    sent = await run_start(redis, handler, "/start link_abc")
    assert seen["token"] == "abc" and seen["tg_user_id"] == 5 and seen["chat_id"] == 5
    assert len(sent) == 1 and "привязан" in sent[0].text


async def test_start_link_expired_410_says_link_outdated(redis):
    def handler(req: httpx.Request):
        if req.url.path == "/internal/tg/link":
            return httpx.Response(410, json={"code": "link_token_invalid", "detail": "x"})
        return httpx.Response(200, json={"linked": False})

    sent = await run_start(redis, handler, "/start link_old")
    assert len(sent) == 1
    assert "Ссылка устарела" in sent[0].text and "недоступен" not in sent[0].text


async def test_repeated_start_after_linking_says_already_linked(redis):
    def handler(req: httpx.Request):
        if req.url.path == "/internal/tg/link":  # токен уже израсходован первым тапом
            return httpx.Response(410, json={"code": "link_token_invalid", "detail": "x"})
        return httpx.Response(200, json={"linked": True})

    sent = await run_start(redis, handler, "/start link_used")
    assert len(sent) == 1 and "уже привязан" in sent[0].text


async def test_start_link_conflict_and_outage_are_distinguished(redis):
    def conflict(req: httpx.Request):
        return httpx.Response(409, json={"code": "telegram_already_linked", "detail": "x"})

    def down(req: httpx.Request):
        raise httpx.ConnectTimeout("t", request=req)

    sent = await run_start(redis, conflict, "/start link_x")
    assert "уже привязан к другому" in sent[0].text
    sent = await run_start(redis, down, "/start link_x")
    assert "недоступен" in sent[0].text


def test_bot_has_no_registration_handlers():
    from fsp_bot import handlers, states

    assert not hasattr(states, "Onboarding")
    assert not hasattr(handlers, "CONSENT_KB")
    core = core_with(lambda r: httpx.Response(200))
    assert not hasattr(core, "consents") and not hasattr(core, "start")
    router = handlers.build_router(core)

    def callbacks(r):
        for h in r.callback_query.handlers:
            yield repr(h.filters)
        for sub in r.sub_routers:
            yield from callbacks(sub)

    assert not any("c:ok" in c or "c:no" in c for c in callbacks(router))


async def test_magic_link_returns_url():
    def handler(req: httpx.Request):
        assert req.url.path == "/internal/auth/magic-link"
        assert json.loads(req.content) == {"tg_user_id": 5, "redirect": "/me"}
        return httpx.Response(200, json={"url": "https://web.test/auth/magic?token=t"})

    assert await core_with(handler).magic_link(5, "/me") == "https://web.test/auth/magic?token=t"
