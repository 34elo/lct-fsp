"""Офферы в боте: список, кнопки, причины отказа, вопрос (FSM). Токен и core подменены."""

import json
from datetime import UTC, datetime

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.methods import EditMessageReplyMarkup, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from fsp_bot.core_client import CoreClient
from fsp_bot.handlers import build_router

OID = "11111111-1111-1111-1111-111111111111"
OFFER = {
    "offer_id": OID,
    "status": "sent",
    "company_name": "Север",
    "company_responsibility": 4.6,
    "vacancy_title": "Backend",
    "formats": ["remote"],
    "employment_type": "full",
    "salary_from": 200000,
    "salary_to": 250000,
    "message": None,
    "match_score": 0.9,
    "explanation": [],
    "below_candidate_min": False,
    "expires_at": "2026-10-12T09:00:00+00:00",
}


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

    def of(self, kind):
        return [c for c in self.calls if isinstance(c, kind)]


class Core:
    def __init__(self, fail: dict | None = None):
        self.requests: list[tuple[str, str, dict]] = []
        self.fail = fail or {}

    def __call__(self, req: httpx.Request):
        body = json.loads(req.content) if req.content else {}
        self.requests.append((req.method, req.url.path, body))
        if req.url.path in self.fail:
            status, code = self.fail[req.url.path]
            return httpx.Response(status, json={"code": code})
        path = req.url.path
        if path == "/internal/tg/offers":
            return httpx.Response(200, json=[OFFER, {**OFFER, "status": "accepted"}])
        if path.endswith("/view"):
            return httpx.Response(200, json={**OFFER, "status": "viewed"})
        if path.endswith("/accept") or path.endswith("/decline"):
            return httpx.Response(200, json=OFFER)
        if path.endswith("/messages"):
            return httpx.Response(201, json={"id": "m1"})
        return httpx.Response(404, json={"code": "not_found"})


async def make(redis, core: Core):
    session = Session()
    bot = Bot("1:TEST", session=session)
    dp = Dispatcher(storage=RedisStorage(redis))
    client = CoreClient("http://core", "tok", transport=httpx.MockTransport(core))
    dp.include_router(build_router(client))
    return bot, dp, session


USER = User(id=5, is_bot=False, first_name="A")
_n = 0


def _msg(text: str, **kw) -> Message:
    global _n
    _n += 1
    return Message(
        message_id=_n,
        date=datetime.now(UTC),
        chat=Chat(id=5, type="private"),
        from_user=USER,
        text=text,
        **kw,
    )


async def say(dp, bot, text: str):
    kw = {}
    if text.startswith("/"):
        kw["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
    await dp.feed_update(bot, Update(update_id=1, message=_msg(text, **kw)))


async def press(dp, bot, data: str):
    call = CallbackQuery(id="c", from_user=USER, chat_instance="x", data=data, message=_msg("old"))
    await dp.feed_update(bot, Update(update_id=2, callback_query=call))


async def test_list_offers_shows_fork_and_status_buttons(redis):
    core = Core()
    bot, dp, session = await make(redis, core)
    await say(dp, bot, "💼 Офферы")
    sent = session.of(SendMessage)
    assert len(sent) == 2 and "200 000 – 250 000 ₽" in sent[0].text
    first = [b.callback_data for row in sent[0].reply_markup.inline_keyboard for b in row]
    assert first == [f"o:{a}:{OID}" for a in "adv"]
    assert sent[1].reply_markup is None  # принятый: кнопок нет, чата нет
    assert core.requests == [("GET", "/internal/tg/offers", {})]


async def test_no_offers(redis):
    bot, dp, session = await make(redis, lambda req: httpx.Response(200, json=[]))
    await say(dp, bot, "/offers")
    assert "Активных офферов пока нет" in session.of(SendMessage)[0].text


async def test_details_accept_and_decline_flow(redis):
    core = Core()
    bot, dp, session = await make(redis, core)
    await press(dp, bot, f"o:v:{OID}")
    assert core.requests[-1][1] == f"/internal/tg/offers/{OID}/view"
    assert core.requests[-1][2] == {"tg_user_id": 5}
    assert "Новый оффер" in session.of(EditMessageText)[-1].text

    await press(dp, bot, f"o:d:{OID}")  # только клавиатура причин, core не трогаем
    kb = session.of(EditMessageReplyMarkup)[-1].reply_markup.inline_keyboard
    codes = [b.callback_data for row in kb for b in row]
    assert [c for c in codes if c.startswith("o:r:")] == [
        f"o:r:{OID}:{x}" for x in ("ls", "ws", "wf", "wg", "nl", "ot")
    ]
    assert all(len(c.encode()) <= 64 for c in codes)
    assert len(core.requests) == 1

    await press(dp, bot, f"o:r:{OID}:ws")
    assert core.requests[-1] == (
        "POST",
        f"/internal/tg/offers/{OID}/decline",
        {"tg_user_id": 5, "reason": "wrong_stack"},
    )
    assert "отклонили оффер" in session.of(EditMessageText)[-1].text

    await press(dp, bot, f"o:a:{OID}")
    assert core.requests[-1][1] == f"/internal/tg/offers/{OID}/accept"
    assert "Вы приняли оффер" in session.of(EditMessageText)[-1].text


async def test_unknown_reason_does_not_call_core(redis):
    core = Core()
    bot, dp, _ = await make(redis, core)
    await press(dp, bot, f"o:r:{OID}:zz")
    assert core.requests == []


async def test_core_error_is_shown_not_raised(redis):
    core = Core(fail={f"/internal/tg/offers/{OID}/accept": (409, "invalid_transition")})
    bot, dp, session = await make(redis, core)
    await press(dp, bot, f"o:a:{OID}")
    assert session.of(EditMessageText) == []  # сообщение не менялось
