from types import SimpleNamespace
from uuid import uuid4

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage
from fsp_bot.limiter import SendLimiter
from fsp_bot.main import build_consumer
from fsp_bot.sender import Sender
from fsp_contracts import new_command
from fsp_contracts.notify import NotifyTelegram, TgButton, TgTemplate


class FakeBot:
    def __init__(self):
        self.sent: list[tuple] = []
        self.edited: list[tuple] = []
        self.fail_send: list[Exception] = []
        self.fail_edit: list[Exception] = []
        self._id = 100

    async def send_message(self, chat_id, text, **kw):
        if self.fail_send:
            raise self.fail_send.pop(0)
        self._id += 1
        self.sent.append((chat_id, text, kw))
        return SimpleNamespace(message_id=self._id)

    async def edit_message_text(self, text, *, chat_id, message_id, **kw):
        if self.fail_edit:
            raise self.fail_edit.pop(0)
        self.edited.append((chat_id, message_id, text))
        return SimpleNamespace(message_id=message_id)


class NoLimit(SendLimiter):
    async def acquire(self, chat_id):
        return


def make(redis, bot=None):
    bot = bot or FakeBot()
    naps: list[float] = []

    async def sleep(s):
        naps.append(s)

    return bot, naps, Sender(bot, redis, NoLimit(), sleep=sleep)


def envelope(**payload):
    payload.setdefault("chat_id", 7)
    payload.setdefault("template", TgTemplate.fsp_imported)
    env, _ = new_command("notify.telegram", "core", NotifyTelegram(**payload))
    return env


async def test_redelivery_sends_once(redis):
    bot, _, sender = make(redis)
    env = envelope(data={"count": 3})
    await sender.handle(env)
    await sender.handle(env)
    assert len(bot.sent) == 1


async def test_edit_of_edits_then_sends_new_if_missing(redis):
    bot, _, sender = make(redis)
    p = {"template": TgTemplate.resume_progress, "edit_of": "resume:1"}
    await sender.handle(envelope(**p))
    await sender.handle(envelope(**p))
    assert len(bot.sent) == 1 and len(bot.edited) == 1
    assert bot.edited[0][1] == 101
    # сообщение удалено в чате → редактирование падает, шлём новое
    bot.fail_edit.append(TelegramBadRequest(SendMessage(chat_id=1, text="x"), "message not found"))
    await sender.handle(envelope(**p))
    assert len(bot.sent) == 2


async def test_not_modified_is_ok(redis):
    bot, _, sender = make(redis)
    p = {"template": TgTemplate.resume_progress, "edit_of": "k"}
    await sender.handle(envelope(**p))
    bot.fail_edit.append(
        TelegramBadRequest(SendMessage(chat_id=1, text="x"), "message is not modified")
    )
    await sender.handle(envelope(**p))
    assert len(bot.sent) == 1


async def test_retry_after_waits_and_retries(redis):
    bot, naps, sender = make(redis)
    bot.fail_send.append(TelegramRetryAfter(SendMessage(chat_id=1, text="x"), "flood", 4))
    await sender.handle(envelope())
    assert naps == [4] and len(bot.sent) == 1


async def test_retry_after_gives_up(redis):
    bot, _, sender = make(redis)
    bot.fail_send.extend(
        TelegramRetryAfter(SendMessage(chat_id=1, text="x"), "flood", 1) for _ in range(5)
    )
    with pytest.raises(TelegramRetryAfter):
        await sender.handle(envelope())
    assert not await redis.exists(f"bot:sent:{uuid4()}")


async def test_blocked_user_is_dropped_not_retried(redis):
    bot, _, sender = make(redis)
    bot.fail_send.append(TelegramForbiddenError(SendMessage(chat_id=1, text="x"), "blocked"))
    await sender.handle(envelope())  # не бросает → сообщение будет подтверждено
    assert bot.sent == []


async def test_buttons_become_keyboard(redis):
    bot, _, sender = make(redis)
    await sender.handle(envelope(buttons=[[TgButton(text="Принять", callback_data="o:a:1")]]))
    kb = bot.sent[0][2]["reply_markup"]
    assert kb.inline_keyboard[0][0].callback_data == "o:a:1"


def test_consumer_subscribes_to_notify_telegram(redis):
    _, _, sender = make(redis)
    consumer = build_consumer(sender)
    assert consumer.spec.name == "bot.telegram" and consumer.spec.prefetch == 10
    assert set(consumer.handlers) == {"notify.telegram"}
