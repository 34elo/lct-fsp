"""ФСП, категория, статус и настройки в боте (E9-4)."""

import json
from datetime import UTC, datetime

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from fsp_bot.account import category_status, fsp_overview, parse_salary, settings_text
from fsp_bot.core_client import CoreClient
from fsp_bot.handlers import build_router


class Session(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls: list = []

    async def make_request(self, bot, method, timeout=None):  # noqa: ASYNC109
        self.calls.append(method)
        if isinstance(method, SendMessage | EditMessageText):
            return Message(
                message_id=7,
                date=datetime.now(UTC),
                chat=Chat(id=5, type="private"),
                text=getattr(method, "text", ""),
            ).as_(bot)
        return True

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        pass

    def texts(self, kind):
        return [c for c in self.calls if isinstance(c, kind)]


class Core:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.settings = {"salary_min": None, "formats": [], "search_status": "open"}
        self.fsp = {"linked": False, "verified": False, "achievements": [], "teams": []}
        self.link_result = httpx.Response(
            200, json={"method": "code", "masked_contact": "a***@x.ru"}
        )
        self.verified = True
        self.sync_error = None

    def __call__(self, req: httpx.Request):
        self.requests.append(req)
        path, body = req.url.path, json.loads(req.content) if req.content else {}
        if path == "/internal/auth/magic-link":
            return httpx.Response(200, json={"url": "https://web.test/auth/magic?token=t"})
        if path == "/internal/tg/settings":
            if req.method == "PATCH":
                self.settings.update({k: v for k, v in body.items() if k != "tg_user_id"})
            return httpx.Response(200, json=self.settings)
        if path == "/internal/tg/status":
            self.settings["search_status"] = body["status"]
            return httpx.Response(200, json=self.settings)
        if path == "/internal/tg/fsp":
            return httpx.Response(200, json=self.fsp)
        if path == "/internal/tg/fsp/link":
            return self.link_result
        if path == "/internal/tg/fsp/verify":
            return httpx.Response(200, json={"verified": self.verified})
        if path == "/internal/tg/fsp/sync":
            return self.sync_error or httpx.Response(202, json={"status": "accepted"})
        if path == "/internal/tg/category":
            return httpx.Response(
                200,
                json={
                    "categories": [
                        {
                            "profession": "backend",
                            "title": "Backend",
                            "grade": "middle",
                            "needs_confirmation": False,
                            "valid_until": "2027-01-01T00:00:00+00:00",
                        }
                    ],
                    "claims": [
                        {
                            "profession": "backend",
                            "title": "Backend",
                            "status": "overclaimed",
                            "declared_grade": "senior",
                            "confirmed_grade": "middle",
                        }
                    ],
                },
            )
        return httpx.Response(404, json={"code": "not_found"})

    def paths(self, method=None):
        return [r.url.path for r in self.requests if method in (None, r.method)]

    def body(self, path):
        return [json.loads(r.content) for r in self.requests if r.url.path == path and r.content][
            -1
        ]


def make(redis, core):
    session = Session()
    bot = Bot("1:TEST", session=session)
    dp = Dispatcher(storage=RedisStorage(redis))
    client = CoreClient("http://core", "tok", transport=httpx.MockTransport(core))
    dp.include_router(build_router(client, poll_interval=0, poll_timeout=1))
    return bot, dp, session


_n = [100]


def say(text):
    _n[0] += 1
    msg = Message(
        message_id=_n[0],
        date=datetime.now(UTC),
        chat=Chat(id=5, type="private"),
        from_user=User(id=5, is_bot=False, first_name="A"),
        text=text,
    )
    return Update(update_id=_n[0], message=msg)


def tap(data):
    _n[0] += 1
    msg = Message(message_id=7, date=datetime.now(UTC), chat=Chat(id=5, type="private"), text="x")
    cq = CallbackQuery(
        id="1",
        from_user=User(id=5, is_bot=False, first_name="A"),
        chat_instance="c",
        data=data,
        message=msg,
    )
    return Update(update_id=_n[0], callback_query=cq)


def buttons(method):
    kb = method.reply_markup
    return [b for row in kb.inline_keyboard for b in row]


def test_parse_salary():
    assert parse_salary("230000") == 230000
    assert parse_salary("230 000") == 230000
    assert parse_salary("230к") == 230000
    assert parse_salary("нет") is None and parse_salary("0") is None
    assert parse_salary("abc") is False
    assert parse_salary("999999999999") is False


def test_texts():
    assert "не привязан" in fsp_overview({"linked": False})
    text = fsp_overview(
        {"linked": True, "verified": True, "achievements": ["2 место"], "teams": ["Т"]}
    )
    assert "подтверждено" in text and "2 место" in text and "Т" in text
    assert "230 000" in settings_text({"salary_min": 230000, "formats": ["remote"]})
    assert "<" not in settings_text({"formats": []}).replace("<b>", "").replace("</b>", "")


async def test_fsp_not_linked_offers_link_and_flow(redis):
    core = Core()
    bot, dp, session = make(redis, core)
    await dp.feed_update(bot, say("🏆 ФСП"))
    sent = session.texts(SendMessage)[-1]
    assert "не привязан" in sent.text
    assert any(b.callback_data == "f:l" for b in buttons(sent))
    assert any(b.url and "magic" in b.url for b in buttons(sent))
    await dp.feed_update(bot, tap("f:l"))
    await dp.feed_update(bot, say("p-anya"))
    assert core.body("/internal/tg/fsp/link") == {"tg_user_id": 5, "participant_id": "p-anya"}
    assert "Пришли 6 цифр" in session.texts(SendMessage)[-1].text
    await dp.feed_update(bot, say("12ab"))
    assert "6 цифр" in session.texts(SendMessage)[-1].text
    assert "/internal/tg/fsp/verify" not in core.paths()
    await dp.feed_update(bot, say("123456"))
    assert core.body("/internal/tg/fsp/verify")["code"] == "123456"
    assert "подтверждена" in session.texts(SendMessage)[-1].text


async def test_fsp_link_by_email_and_errors(redis):
    core = Core()
    core.link_result = httpx.Response(404, json={"code": "fsp_not_found"})
    bot, dp, session = make(redis, core)
    await dp.feed_update(bot, tap("f:l"))
    await dp.feed_update(bot, say("a@b.ru"))
    assert core.body("/internal/tg/fsp/link") == {"tg_user_id": 5, "email": "a@b.ru"}
    assert "не найден" in session.texts(SendMessage)[-1].text
    # после «не найден» состояние остаётся: можно ввести другой ID
    core.link_result = httpx.Response(200, json={"method": "manual"})
    await dp.feed_update(bot, say("p-2"))
    assert "привязан" in session.texts(SendMessage)[-1].text


async def test_wrong_code_keeps_state(redis):
    core = Core()
    core.verified = False
    bot, dp, session = make(redis, core)
    await dp.feed_update(bot, tap("f:l"))
    await dp.feed_update(bot, say("p-anya"))
    await dp.feed_update(bot, say("000000"))
    assert "неверный" in session.texts(SendMessage)[-1].text
    core.verified = True
    await dp.feed_update(bot, say("123456"))
    assert "подтверждена" in session.texts(SendMessage)[-1].text


async def test_fsp_linked_sync(redis):
    core = Core()
    core.fsp = {"linked": True, "verified": True, "achievements": ["1 место, Кубок"], "teams": []}
    bot, dp, session = make(redis, core)
    await dp.feed_update(bot, say("/fsp"))
    sent = session.texts(SendMessage)[-1]
    assert "1 место" in sent.text and any(b.callback_data == "f:s" for b in buttons(sent))
    await dp.feed_update(bot, tap("f:s"))
    assert "/internal/tg/fsp/sync" in core.paths()
    core.sync_error = httpx.Response(429, json={"code": "sync_too_often"})
    await dp.feed_update(bot, tap("f:s"))
    assert "раз в 10 минут" in session.texts(AnswerCallbackQuery)[-1].text


async def test_category_status_with_test_stub(redis):
    core = Core()
    bot, dp, session = make(redis, core)
    await dp.feed_update(bot, say("🎯 Категория"))
    sent = session.texts(SendMessage)[-1]
    assert "Backend · Middle" in sent.text
    assert "заявлено Senior, подтверждено Middle" in sent.text
    assert "скоро" in sent.text
    assert any(b.url and "magic" in b.url for b in buttons(sent))
    assert "Подтверждённой категории пока нет" in category_status({"categories": [], "claims": []})


async def test_status_buttons(redis):
    core = Core()
    bot, dp, session = make(redis, core)
    await dp.feed_update(bot, say("🔥 Статус"))
    sent = session.texts(SendMessage)[-1]
    assert {b.callback_data for b in buttons(sent)} == {"s:active", "s:open", "s:dnd"}
    await dp.feed_update(bot, tap("s:dnd"))
    assert core.body("/internal/tg/status") == {"tg_user_id": 5, "status": "dnd"}
    assert "не беспокоить" in session.texts(EditMessageText)[-1].text
    await dp.feed_update(bot, tap("s:evil"))
    assert core.paths("PATCH") == ["/internal/tg/status"]


async def test_settings_salary_and_formats(redis):
    core = Core()
    bot, dp, session = make(redis, core)
    await dp.feed_update(bot, say("⚙️ Настройки"))
    sent = session.texts(SendMessage)[-1]
    assert "не указана" in sent.text
    await dp.feed_update(bot, tap("g:sal"))
    await dp.feed_update(bot, say("мало"))
    assert "Не понял" in session.texts(SendMessage)[-1].text
    assert core.paths("PATCH") == []
    await dp.feed_update(bot, say("230к"))
    assert core.body("/internal/tg/settings")["salary_min"] == 230000
    assert "230 000" in session.texts(SendMessage)[-1].text
    await dp.feed_update(bot, tap("g:f:remote"))
    assert core.body("/internal/tg/settings")["formats"] == ["remote"]
    assert "salary_min" not in core.body("/internal/tg/settings")
    await dp.feed_update(bot, tap("g:f:remote"))
    assert core.body("/internal/tg/settings")["formats"] == []
    await dp.feed_update(bot, tap("g:f:moon"))
    assert len(core.paths("PATCH")) == 3


async def test_clear_salary_sends_null(redis):
    core = Core()
    core.settings["salary_min"] = 100000
    bot, dp, _ = make(redis, core)
    await dp.feed_update(bot, tap("g:sal"))
    await dp.feed_update(bot, say("нет"))
    assert core.body("/internal/tg/settings") == {"tg_user_id": 5, "salary_min": None}


async def test_menu_text_inside_state_is_not_taken_as_salary(redis):
    core = Core()
    bot, dp, _ = make(redis, core)
    await dp.feed_update(bot, tap("g:sal"))
    await dp.feed_update(bot, say("🔥 Статус"))
    assert core.paths("PATCH") == []
    assert "/internal/tg/settings" in core.paths("GET")  # меню статуса прочитало настройки
