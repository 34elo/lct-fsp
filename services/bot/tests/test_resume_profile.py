import io
import zipfile
from datetime import UTC, datetime

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.methods import EditMessageText, GetFile, SendMessage
from aiogram.types import Chat, Document, File, Message, Update, User
from fsp_bot.core_client import CoreClient
from fsp_bot.handlers import build_router, file_kind
from fsp_bot.templates.render import profile_summary

PDF = b"%PDF-1.7\nhello"


def docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
    return buf.getvalue()


class Session(BaseSession):
    def __init__(self, content: bytes):
        super().__init__()
        self.calls: list = []
        self.content = content

    async def make_request(self, bot, method, timeout=None):  # noqa: ASYNC109
        self.calls.append(method)
        if isinstance(method, GetFile):
            return File(file_id="f", file_unique_id="u", file_path="p")
        if isinstance(method, SendMessage | EditMessageText):
            return Message(
                message_id=7,
                date=datetime.now(UTC),
                chat=Chat(id=5, type="private"),
                text=getattr(method, "text", ""),
            ).as_(bot)
        return True

    async def stream_content(self, url, *args, **kwargs):
        yield self.content

    async def close(self):
        pass

    def texts(self, kind):
        return [c for c in self.calls if isinstance(c, kind)]


class Core:
    """Подставной сервер core: запоминает запросы."""

    def __init__(self, statuses=("queued", "parsed")):
        self.statuses = list(statuses)
        self.requests: list[httpx.Request] = []

    def __call__(self, req: httpx.Request):
        self.requests.append(req)
        path = req.url.path
        if path == "/internal/tg/resumes" and req.method == "POST":
            return httpx.Response(202, json={"resume_id": "r1", "job_id": "j1"})
        if path == "/internal/tg/resumes/r1":
            st = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return httpx.Response(
                200, json={"status": st, "skills": ["Python"], "experience_months": 20}
            )
        if path == "/internal/tg/resumes/r1/confirm":
            return httpx.Response(200, json={"status": "confirmed"})
        if path == "/internal/auth/magic-link":
            return httpx.Response(200, json={"url": "https://web.test/auth/magic?token=t"})
        if path == "/internal/tg/profile":
            return httpx.Response(
                200,
                json={
                    "primary_role": "backend",
                    "grade": "middle",
                    "grade_preliminary": True,
                    "skills": [{"name": "Python", "level": 3, "claimed_only": False}],
                    "fsp": ["2 место, Кубок"],
                },
            )
        return httpx.Response(404, json={"code": "not_found"})

    def uploads(self):
        return [r for r in self.requests if r.url.path == "/internal/tg/resumes"]


async def noop_sleep(_):
    pass


def make(redis, core, content):
    session = Session(content)
    bot = Bot("1:TEST", session=session)
    dp = Dispatcher(storage=RedisStorage(redis))
    client = CoreClient("http://core", "tok", transport=httpx.MockTransport(core))
    dp.include_router(build_router(client, poll_interval=0, poll_timeout=5, sleep=noop_sleep))
    return bot, dp, session


def doc_update(size=100):
    msg = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=5, type="private"),
        from_user=User(id=5, is_bot=False, first_name="A"),
        document=Document(file_id="f", file_unique_id="u", file_name="cv.pdf", file_size=size),
    )
    return Update(update_id=1, message=msg)


def text_update(text, entities=None):
    msg = Message(
        message_id=2,
        date=datetime.now(UTC),
        chat=Chat(id=5, type="private"),
        from_user=User(id=5, is_bot=False, first_name="A"),
        text=text,
        entities=entities,
    )
    return Update(update_id=2, message=msg)


def test_file_kind_by_signature():
    assert file_kind(b"%PDF-1.4") == "pdf"
    assert file_kind(docx()[:8]) == "docx"
    assert file_kind(b"MZ\x90\x00") is None
    assert file_kind(b"") is None


async def test_pdf_uploaded_then_progress_edited_and_confirm_button(redis):
    core = Core()
    bot, dp, session = make(redis, core, PDF)
    await dp.feed_update(bot, doc_update())
    up = core.uploads()
    assert len(up) == 1 and b"%PDF-" in up[0].content and b'name="tg_user_id"' in up[0].content
    assert "Разбираю" in session.texts(SendMessage)[0].text
    final = session.texts(EditMessageText)[-1]
    assert "Вот что я понял" in final.text and "Python" in final.text
    buttons = [b for row in final.reply_markup.inline_keyboard for b in row]
    assert any(b.callback_data == "r:ok:r1" for b in buttons)
    assert any(b.url and "magic" in b.url for b in buttons)


async def test_not_pdf_is_rejected_without_calling_core(redis):
    core = Core()
    bot, dp, session = make(redis, core, b"MZ\x90\x00 exe")
    await dp.feed_update(bot, doc_update())
    assert core.requests == []
    assert "не PDF" in session.texts(SendMessage)[0].text


async def test_oversized_declared_file_is_rejected_before_download(redis):
    core = Core()
    bot, dp, session = make(redis, core, PDF)
    await dp.feed_update(bot, doc_update(size=10 * 1024 * 1024 + 1))
    assert core.requests == [] and not session.texts(GetFile)
    assert "10 МБ" in session.texts(SendMessage)[0].text


async def test_oversized_actual_file_is_rejected(redis):
    core = Core()
    bot, dp, session = make(redis, core, b"%PDF-" + b"0" * (10 * 1024 * 1024))
    await dp.feed_update(bot, doc_update(size=1))  # Telegram соврал про размер
    assert core.requests == []
    assert "10 МБ" in session.texts(SendMessage)[0].text


async def test_docx_accepted(redis):
    core = Core(statuses=("parsed",))
    bot, dp, _ = make(redis, core, docx())
    await dp.feed_update(bot, doc_update())
    assert len(core.uploads()) == 1


async def test_failed_resume_reported(redis):
    core = Core(statuses=("failed",))
    bot, dp, session = make(redis, core, PDF)
    await dp.feed_update(bot, doc_update())
    assert "Не удалось" in session.texts(EditMessageText)[-1].text


async def test_confirm_callback_calls_core(redis):
    from aiogram.types import CallbackQuery

    core = Core()
    bot, dp, session = make(redis, core, PDF)
    msg = Message(message_id=7, date=datetime.now(UTC), chat=Chat(id=5, type="private"), text="x")
    cq = CallbackQuery(
        id="1",
        from_user=User(id=5, is_bot=False, first_name="A"),
        chat_instance="c",
        data="r:ok:r1",
        message=msg,
    )
    await dp.feed_update(bot, Update(update_id=3, callback_query=cq))
    assert any(r.url.path == "/internal/tg/resumes/r1/confirm" for r in core.requests)
    assert "подтверждено" in session.texts(EditMessageText)[-1].text


async def test_profile_command_renders_summary(redis):
    core = Core()
    bot, dp, session = make(redis, core, PDF)
    await dp.feed_update(bot, text_update("👤 Профиль"))
    text = session.texts(SendMessage)[-1].text
    assert "Middle (предварительно)" in text and "Python ●●●○" in text and "2 место" in text


def test_profile_summary_empty_and_escaped():
    assert "Пока пусто" in profile_summary({"skills": [], "fsp": []})
    out = profile_summary({"skills": [{"name": "<b>", "level": 1}], "fsp": ["a&b"]})
    assert "&lt;b&gt;" in out and "a&amp;b" in out
