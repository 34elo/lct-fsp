"""Входящие обновления Telegram. Без бизнес-логики: каждое действие — вызов core."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Awaitable, Callable

import structlog
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from fsp_bot.core_client import CoreClient, CoreError
from fsp_bot.states import Offer, Onboarding, Resume
from fsp_bot.templates.render import (
    DECLINE_CODES,
    decline_keyboard,
    offer_accepted,
    offer_keyboard,
    offer_new,
    profile_summary,
    resume_parsed,
    resume_progress,
)

log = structlog.get_logger()

WELCOME = (
    "Привет! Я бот <b>ФСП Карьера</b>.\n"
    "1. Загрузи резюме или привяжи ФСП и GitHub.\n"
    "2. Мы соберём профиль, где каждый навык подтверждён доказательствами.\n"
    "3. Работодатели находят тебя анонимно и присылают офферы с вилкой прямо сюда."
)
CONSENTS_ASK = "Для продолжения нужно согласие на обработку данных профиля."
CORE_DOWN = "Сервис временно недоступен, попробуй чуть позже."

NOT_RESUME = "Это не PDF и не DOCX. Пришли резюме в одном из этих форматов."
MAX_RESUME_BYTES = 10 * 1024 * 1024  # telegram.md §3
RESUME_PROMPT = "Пришли резюме файлом: PDF или DOCX, до 10 МБ."
BTN_RESUME, BTN_PROFILE, BTN_OFFERS = "📄 Резюме", "👤 Профиль", "💼 Офферы"
POLL_INTERVAL = 3.0
POLL_TIMEOUT = 180.0
STAGES = {"queued": "В очереди на разбор", "parsing": "Читаю текст и ищу навыки"}

MENU_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_RESUME), KeyboardButton(text=BTN_PROFILE)],
        [KeyboardButton(text=BTN_OFFERS)],
    ],
    resize_keyboard=True,
)

CONSENT_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Согласен", callback_data="c:ok"),
            InlineKeyboardButton(text="Отказаться", callback_data="c:no"),
        ]
    ]
)


OFFER_ERRORS = {
    "offer_not_found": "Оффер не найден.",
    "invalid_transition": "Оффер уже закрыт, ответить на него нельзя.",
    "offer_expired": "Срок действия оффера истёк.",
    "offer_closed": "Переписка по этому офферу закрыта.",
    "empty_message": "Напиши вопрос текстом.",
    "telegram_unknown": "Сначала нажми /start.",
    "forbidden": "Офферы доступны кандидатам.",
}
ASK_QUESTION = "Напиши вопрос работодателю одним сообщением. Отмена: /cancel"
NO_OFFERS = "Активных офферов пока нет. Они появятся здесь, как только работодатель ответит."
MENU_TEXTS = (BTN_RESUME, BTN_PROFILE, BTN_OFFERS)


def offer_error(exc: CoreError) -> str:
    if exc.status == 429:
        return "Слишком часто, попробуй чуть позже."
    return OFFER_ERRORS.get(exc.code, CORE_DOWN)


def file_kind(head: bytes) -> str | None:
    """Тип по сигнатуре, а не по имени и mime из Telegram (security.md §3). Содержимое не читаем."""
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return "docx"  # окончательная проверка структуры — в core
    return None


def build_router(
    core: CoreClient,
    *,
    poll_interval: float = POLL_INTERVAL,
    poll_timeout: float = POLL_TIMEOUT,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> Router:
    router = Router()

    async def site_button(tg_user_id: int, text: str, redirect: str) -> list[InlineKeyboardButton]:
        try:
            url = await core.magic_link(tg_user_id, redirect)
        except CoreError:
            return []
        return [InlineKeyboardButton(text=text, url=url)]

    async def edit(msg: Message, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
        try:
            await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except TelegramBadRequest as exc:  # «message is not modified», недопустимый URL кнопки
            log.info("edit_skipped", reason=str(exc)[:60])
            if kb is not None:
                await msg.edit_text(text, parse_mode="HTML")

    @router.message(CommandStart())
    async def start(message: Message, command: CommandObject, state: FSMContext) -> None:
        user = message.from_user
        if user is None:
            return
        param = command.args
        try:
            info = await core.start(user.id, message.chat.id, user.username, param)
            if param and param.startswith("link_"):
                await core.link(user.id, param.removeprefix("link_"))
        except CoreError as exc:
            log.warning("core_error", code=exc.code, status=exc.status)
            await message.answer(CORE_DOWN)
            return
        await message.answer(WELCOME, parse_mode="HTML")
        if info.get("missing_consents"):
            await state.set_state(Onboarding.consents)
            await state.update_data(missing=info["missing_consents"])
            await message.answer(CONSENTS_ASK, reply_markup=CONSENT_KB)
        else:
            await state.clear()
            await message.answer("Выбери действие в меню.", reply_markup=MENU_KB)

    @router.callback_query(F.data == "c:ok")
    async def consent_ok(call: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        try:
            await core.consents(call.from_user.id, data.get("missing", []))
        except CoreError:
            await call.answer(CORE_DOWN, show_alert=True)
            return
        await state.clear()
        await call.answer("Спасибо!")
        if isinstance(call.message, Message):
            await call.message.edit_text("✅ Согласия сохранены.")
            await call.message.answer(RESUME_PROMPT, reply_markup=MENU_KB)
        await state.set_state(Resume.awaiting_file)

    @router.callback_query(F.data == "c:no")
    async def consent_no(call: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await call.answer()
        if isinstance(call.message, Message):
            await call.message.edit_text("Без согласий продолжить нельзя. Вернуться: /start")

    # --- Офферы (telegram.md §2, §3, §5) ---------------------------------------------------

    @router.message(Command("offers"))
    @router.message(F.text == BTN_OFFERS)
    async def offers_list(message: Message, state: FSMContext) -> None:
        user = message.from_user
        if user is None:
            return
        await state.clear()
        try:
            rows = await core.offers(user.id)
        except CoreError as exc:
            await message.answer(offer_error(exc))
            return
        if not rows:
            await message.answer(NO_OFFERS)
            return
        for row in rows:
            await message.answer(
                offer_new(row),
                parse_mode="HTML",
                reply_markup=offer_keyboard(str(row["offer_id"]), row["status"]),
            )

    def _offer_id(call: CallbackQuery, prefix: str) -> str:
        return (call.data or "").removeprefix(prefix).split(":")[0]

    @router.callback_query(F.data.startswith("o:v:"))
    async def offer_details(call: CallbackQuery) -> None:
        offer_id = _offer_id(call, "o:v:")
        try:
            row = await core.offer_view(call.from_user.id, offer_id)
        except CoreError as exc:
            await call.answer(offer_error(exc), show_alert=True)
            return
        await call.answer()
        if isinstance(call.message, Message):
            await edit(call.message, offer_new(row), offer_keyboard(offer_id, row["status"]))

    @router.callback_query(F.data.startswith("o:a:"))
    async def offer_accept(call: CallbackQuery, state: FSMContext) -> None:
        offer_id = _offer_id(call, "o:a:")
        try:
            await core.offer_accept(call.from_user.id, offer_id)
        except CoreError as exc:
            await call.answer(offer_error(exc), show_alert=True)
            return
        await state.clear()
        await call.answer("Оффер принят")
        if isinstance(call.message, Message):
            await edit(call.message, offer_accepted({}), offer_keyboard(offer_id, "accepted"))

    @router.callback_query(F.data.startswith("o:d:"))
    async def offer_decline_ask(call: CallbackQuery) -> None:
        offer_id = _offer_id(call, "o:d:")
        await call.answer()
        if isinstance(call.message, Message):
            try:
                await call.message.edit_reply_markup(reply_markup=decline_keyboard(offer_id))
            except TelegramBadRequest as exc:
                log.info("edit_skipped", reason=str(exc)[:60])

    @router.callback_query(F.data.startswith("o:b:"))
    async def offer_decline_back(call: CallbackQuery) -> None:
        offer_id = _offer_id(call, "o:b:")
        await call.answer()
        if isinstance(call.message, Message):
            try:
                await call.message.edit_reply_markup(
                    reply_markup=offer_keyboard(offer_id, "viewed")
                )
            except TelegramBadRequest as exc:
                log.info("edit_skipped", reason=str(exc)[:60])

    @router.callback_query(F.data.startswith("o:r:"))
    async def offer_decline(call: CallbackQuery) -> None:
        _, _, offer_id, *rest = (call.data or "").split(":")
        reason = DECLINE_CODES.get(rest[0]) if rest else None
        if reason is None:
            await call.answer("Неизвестная причина.", show_alert=True)
            return
        try:
            await core.offer_decline(call.from_user.id, offer_id, reason)
        except CoreError as exc:
            await call.answer(offer_error(exc), show_alert=True)
            return
        await call.answer("Готово")
        if isinstance(call.message, Message):
            await edit(
                call.message, "❌ Вы отклонили оффер. Спасибо за ответ, мы передали причину."
            )

    @router.callback_query(F.data.startswith("o:q:"))
    async def offer_question_ask(call: CallbackQuery, state: FSMContext) -> None:
        offer_id = _offer_id(call, "o:q:")
        await state.set_state(Offer.awaiting_question)
        await state.update_data(offer_id=offer_id)
        await call.answer()
        if isinstance(call.message, Message):
            await call.message.answer(ASK_QUESTION)

    @router.message(Command("cancel"))
    async def cancel(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Отменено.", reply_markup=MENU_KB)

    @router.message(
        Offer.awaiting_question, F.text, ~F.text.startswith("/"), ~F.text.in_(MENU_TEXTS)
    )
    async def offer_question(message: Message, state: FSMContext) -> None:
        user = message.from_user
        data = await state.get_data()
        offer_id = data.get("offer_id")
        if user is None or not offer_id or not message.text:
            await state.clear()
            return
        try:
            await core.offer_message(user.id, str(offer_id), message.text)
        except CoreError as exc:
            if exc.status != 429:  # при лимите состояние остаётся: можно повторить позже
                await state.clear()
            await message.answer(offer_error(exc))
            return
        await state.clear()
        await message.answer("✉️ Вопрос отправлен работодателю. Ответ придёт сюда.")

    @router.message(Command("resume"))
    @router.message(F.text == BTN_RESUME)
    async def resume_ask(message: Message, state: FSMContext) -> None:
        await state.set_state(Resume.awaiting_file)
        await message.answer(RESUME_PROMPT)

    @router.message(F.document)
    async def resume_file(message: Message, state: FSMContext) -> None:
        user, doc = message.from_user, message.document
        if user is None or doc is None or message.bot is None:
            return
        if doc.file_size is not None and doc.file_size > MAX_RESUME_BYTES:
            await message.answer("Файл больше 10 МБ. Сожми или пришли другой.")
            return
        buf = io.BytesIO()
        await message.bot.download(doc, destination=buf)
        data = buf.getvalue()
        if len(data) > MAX_RESUME_BYTES:
            await message.answer("Файл больше 10 МБ. Сожми или пришли другой.")
            return
        if not data or file_kind(data[:8]) is None:
            await message.answer(NOT_RESUME)
            return
        try:
            accepted = await core.upload_resume(user.id, doc.file_name or "resume", data)
        except CoreError as exc:
            await message.answer(_upload_error(exc))
            return
        finally:
            del data, buf  # файл не храним
        await state.clear()
        resume_id = str(accepted["resume_id"])
        progress = await message.answer(
            resume_progress({"steps": [{"done": True, "text": "Файл получен"}]})
        )
        await _watch_resume(progress, user.id, resume_id)

    def _upload_error(exc: CoreError) -> str:
        return {
            "unsupported_file_type": NOT_RESUME,
            "file_too_large": "Файл больше 10 МБ. Сожми или пришли другой.",
            "empty_file": "Файл пустой.",
            "consent_required": "Сначала нужно согласие на обработку данных: /start",
        }.get(
            exc.code,
            "Много загрузок за сутки, попробуй завтра." if exc.status == 429 else CORE_DOWN,
        )

    async def _watch_resume(progress: Message, tg_user_id: int, resume_id: str) -> None:
        """Одно сообщение «Разбираю…» редактируется по этапам, пока core не вернёт итог."""
        waited, shown = 0.0, ""
        while waited <= poll_timeout:
            await sleep(poll_interval)
            waited += poll_interval
            try:
                st = await core.resume_status(tg_user_id, resume_id)
            except CoreError:
                continue
            status = st["status"]
            if status == "failed":
                await edit(progress, "😕 Не удалось разобрать файл. Пришли другой: 📄 Резюме.")
                return
            if status in ("parsed", "confirmed"):
                months = st.get("experience_months")
                exp = f"{months // 12} г {months % 12} мес" if months else None
                text = resume_parsed({"experience": exp, "skills": st.get("skills") or []})
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="✅ Всё верно", callback_data=f"r:ok:{resume_id}"
                            )
                        ],
                        await site_button(tg_user_id, "✏️ Исправить на сайте", "/me"),
                    ]
                )
                kb.inline_keyboard = [row for row in kb.inline_keyboard if row]
                await edit(progress, text, kb)
                return
            if status != shown and status in STAGES:
                shown = status
                steps = [
                    {"done": True, "text": "Файл получен"},
                    {"done": False, "text": STAGES[status]},
                ]
                await edit(progress, resume_progress({"steps": steps}))
        await edit(progress, "⏳ Разбор занимает дольше обычного. Результат появится на сайте.")

    @router.callback_query(F.data.startswith("r:ok:"))
    async def resume_confirm(call: CallbackQuery) -> None:
        resume_id = (call.data or "").removeprefix("r:ok:")
        try:
            await core.confirm_resume(call.from_user.id, resume_id)
        except CoreError as exc:
            msg = "Резюме ещё не разобрано." if exc.code == "resume_not_parsed" else CORE_DOWN
            await call.answer(msg, show_alert=True)
            return
        await call.answer("Готово")
        if isinstance(call.message, Message):
            row = await site_button(call.from_user.id, "🌐 Открыть профиль", "/me")
            kb = InlineKeyboardMarkup(inline_keyboard=[row]) if row else None
            await edit(call.message, "✅ Резюме подтверждено. Профиль пересчитывается.", kb)

    @router.message(Command("profile"))
    @router.message(F.text == BTN_PROFILE)
    async def profile(message: Message) -> None:
        user = message.from_user
        if user is None:
            return
        try:
            data = await core.profile(user.id)
        except CoreError as exc:
            await message.answer(
                "Сначала нажми /start." if exc.code == "telegram_unknown" else CORE_DOWN
            )
            return
        row = await site_button(user.id, "🌐 Открыть профиль", "/me")
        kb = InlineKeyboardMarkup(inline_keyboard=[row]) if row else None
        try:
            await message.answer(profile_summary(data), parse_mode="HTML", reply_markup=kb)
        except TelegramBadRequest:
            await message.answer(profile_summary(data), parse_mode="HTML")

    return router
