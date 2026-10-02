"""Входящие обновления Telegram. Без бизнес-логики: каждое действие — вызов core."""

from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from fsp_bot.core_client import CoreClient, CoreError
from fsp_bot.states import Onboarding

log = structlog.get_logger()

WELCOME = (
    "Привет! Я бот <b>ФСП Карьера</b>.\n"
    "1. Загрузи резюме или привяжи ФСП и GitHub.\n"
    "2. Мы соберём профиль, где каждый навык подтверждён доказательствами.\n"
    "3. Работодатели находят тебя анонимно и присылают офферы с вилкой прямо сюда."
)
CONSENTS_ASK = "Для продолжения нужно согласие на обработку данных профиля."
CORE_DOWN = "Сервис временно недоступен, попробуй чуть позже."

CONSENT_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Согласен", callback_data="c:ok"),
            InlineKeyboardButton(text="Отказаться", callback_data="c:no"),
        ]
    ]
)


def build_router(core: CoreClient) -> Router:
    router = Router()

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
            await call.message.edit_text("✅ Согласия сохранены. Пришли резюме PDF или DOCX.")

    @router.callback_query(F.data == "c:no")
    async def consent_no(call: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await call.answer()
        if isinstance(call.message, Message):
            await call.message.edit_text("Без согласий продолжить нельзя. Вернуться: /start")

    return router
