"""Короткий тест и регулярные задания в боте: через фейковый core."""

import json
from datetime import UTC, datetime

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.methods import EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from fsp_bot.assessment import parse_text_answer, result_text, unit_mode, units_of
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


AID = "aaaaaaaa-0000-0000-0000-000000000001"
TID = "bbbbbbbb-0000-0000-0000-000000000002"

ITEMS = [
    {"response_id": "r1", "seq": 1, "kind": "choice", "stem": "Q1", "options": ["a", "b", "c"]},
    {"response_id": "r2", "seq": 2, "kind": "sjt", "stem": "Q2", "options": ["x", "y", "z"]},
    {"response_id": "r3", "seq": 3, "kind": "find_bug", "stem": "Q3 код"},
    {
        "response_id": "r4",
        "seq": 4,
        "kind": "chain",
        "stem": "Цепочка",
        "steps": [
            {"kind": "choice", "stem": "S1", "options": ["p", "q"]},
            {"kind": "exact", "stem": "S2"},
        ],
    },
]


class Core:
    def __init__(self, survey=None, start_error=None):
        self.requests: list[httpx.Request] = []
        self.survey = survey or {"profession": "backend", "declared_grade": "middle"}
        self.start_error = start_error
        self.idx = 0
        self.answers: list[dict] = []
        self.task_submitted = False

    def __call__(self, req: httpx.Request):
        self.requests.append(req)
        path = req.url.path
        body = json.loads(req.content) if req.content else {}
        if path == "/internal/auth/magic-link":
            return httpx.Response(200, json={"url": "https://web.test/m"})
        if path == "/internal/tg/token":
            return httpx.Response(200, json={"access_token": "user-jwt", "expires_in": 300})
        assert req.headers["authorization"] == "Bearer user-jwt", path
        if path == "/assessment/survey":
            return httpx.Response(200, json=self.survey)
        if path == "/taxonomy/professions":
            return httpx.Response(
                200, json={"professions": [{"slug": "backend", "title": "Backend"}]}
            )
        if path == "/assessment/attempts" and req.method == "POST":
            if self.start_error:
                return self.start_error
            return httpx.Response(201, json={"id": AID, "target": 4, "mode": body["mode"]})
        if path == f"/assessment/attempts/{AID}/next":
            if self.idx >= len(ITEMS):
                return httpx.Response(200, json={"done": True})
            return httpx.Response(200, json=ITEMS[self.idx])
        if path == f"/assessment/attempts/{AID}/answers":
            self.answers.append(body)
            self.idx += 1
            return httpx.Response(
                200, json={"response_id": body["response_id"], "accepted": True, "done": False}
            )
        if path == f"/assessment/attempts/{AID}":
            return httpx.Response(
                200,
                json={
                    "id": AID,
                    "status": "passed",
                    "result": {"grade": "middle", "by_skill": [{"skill": "python", "share": 0.5}]},
                    "invited_grade": "senior",
                },
            )
        if path == "/assessment/tasks":
            row = {"id": TID, "title": "Разбор инцидента", "submitted": self.task_submitted}
            return httpx.Response(200, json=[row])
        if path == f"/assessment/tasks/{TID}/answer":
            self.answers.append(body)
            self.task_submitted = True
            return httpx.Response(200, json={"id": TID, "submitted": True, "score": None})
        if path == f"/assessment/tasks/{TID}":
            return httpx.Response(
                200,
                json={
                    "id": TID,
                    "title": "Разбор инцидента",
                    "submitted": self.task_submitted,
                    "item": {"kind": "open", "stem": "Опиши разбор"},
                },
            )
        return httpx.Response(404, json={"code": "not_found"})


def make(redis, core):
    session = Session()
    bot = Bot("1:TEST", session=session)
    dp = Dispatcher(storage=RedisStorage(redis))
    client = CoreClient("http://core", "tok", transport=httpx.MockTransport(core))
    dp.include_router(build_router(client, poll_interval=0, poll_timeout=1))
    return bot, dp, session


def last(session):
    return session.texts(SendMessage)[-1]


def n_of(method):
    return int(buttons(method)[0].callback_data.split(":")[2])


def test_pure_helpers():
    assert unit_mode({"kind": "choice", "options": ["a"]}) == "choice"
    assert unit_mode({"kind": "sjt", "options": ["a", "b"]}) == "order"
    assert unit_mode({"kind": "find_bug"}) == "text"
    assert [u["stem"] for u in units_of(ITEMS[3])] == ["S1", "S2"]
    assert units_of(ITEMS[0]) == [ITEMS[0]]
    assert parse_text_answer({"kind": "find_bug"}, "5, 2 и 5") == [2, 5]
    assert parse_text_answer({"kind": "estimate"}, "1,5") == "1.5"
    assert parse_text_answer({"kind": "exact"}, " abc ") == "abc"
    done = {"status": "passed", "invited_grade": "senior", "result": {"grade": "middle"}}
    assert "Senior" in result_text(done)


async def test_full_express_test_and_idempotent_tap(redis):
    core = Core()
    bot, dp, session = make(redis, core)
    await dp.feed_update(bot, say("/test"))
    start = next(r for r in core.requests if r.url.path == "/assessment/attempts")
    assert json.loads(start.content) == {
        "profession": "backend",
        "declared_grade": "middle",
        "mode": "express",
    }
    q1 = last(session)
    assert "Q1" in q1.text and "1. a" in q1.text
    n = n_of(q1)
    await dp.feed_update(bot, tap(f"t:c:{n}:1"))
    await dp.feed_update(bot, tap(f"t:c:{n}:1"))  # повтор той же кнопки не дублирует ответ
    assert len(core.answers) == 1
    assert core.answers[0]["response_id"] == "r1" and core.answers[0]["answer"] == 1
    # порядок (sjt): три нажатия, затем отправка списка индексов
    q2 = last(session)
    assert "Q2" in q2.text
    n = n_of(q2)
    for i in (2, 0, 1):
        await dp.feed_update(bot, tap(f"t:r:{n}:{i}"))
    assert core.answers[1]["answer"] == [2, 0, 1]
    # find_bug: текст
    assert "Q3" in last(session).text
    await dp.feed_update(bot, say("строка 4"))
    assert core.answers[2]["answer"] == [4]
    # цепочка: два шага, один ответ списком
    q4 = last(session)
    assert "шаг 1/2" in q4.text
    await dp.feed_update(bot, tap(f"t:c:{n_of(q4)}:0"))
    assert "шаг 2/2" in last(session).text
    await dp.feed_update(bot, say("42"))
    assert core.answers[3]["answer"] == [0, "42"]
    done = last(session)
    assert "Короткий тест завершён" in done.text and "Middle" in done.text
    assert any(b.callback_data == f"t:u:{AID}" for b in buttons(done))


async def test_start_errors_and_resume_active(redis):
    err = httpx.Response(409, json={"code": "cooldown", "detail": "до 1 января"})
    bot, dp, session = make(redis, Core(start_error=err))
    await dp.feed_update(bot, say("/test"))
    assert "пауза" in last(session).text
    active = httpx.Response(409, json={"code": "attempt_active", "detail": AID})
    bot, dp, session = make(redis, Core(start_error=active))
    await dp.feed_update(bot, say("/test"))
    assert "Продолжаем" in session.texts(SendMessage)[-2].text
    assert "Q1" in last(session).text


async def test_survey_missing_asks_profession_then_grade(redis):
    core = Core(survey={"profession": None})
    bot, dp, session = make(redis, core)
    await dp.feed_update(bot, tap("t:s"))
    assert any(b.callback_data == "t:p:backend" for b in buttons(last(session)))
    await dp.feed_update(bot, tap("t:p:backend"))
    await dp.feed_update(bot, tap("t:g:backend:senior"))
    start = next(r for r in core.requests if r.url.path == "/assessment/attempts")
    assert json.loads(start.content)["declared_grade"] == "senior"


async def test_regular_tasks_flow_and_repeat(redis):
    core = Core()
    bot, dp, session = make(redis, core)
    await dp.feed_update(bot, say("📋 Задания"))
    listing = last(session)
    assert "Разбор инцидента" in listing.text and "ждёт ответа" in listing.text
    await dp.feed_update(bot, tap(f"t:t:{TID}"))
    assert "Опиши разбор" in last(session).text
    await dp.feed_update(bot, say("Сначала откатил релиз"))
    assert core.answers == [{"answer": "Сначала откатил релиз"}]
    assert "Ответ принят" in last(session).text
    # повторное открытие и лишний текст не отправляют второй ответ
    await dp.feed_update(bot, tap(f"t:t:{TID}"))
    await dp.feed_update(bot, say("ещё раз"))
    assert len(core.answers) == 1
    assert "ответ принят" in last(session).text
