"""ФСП, категория и статус теста, статус поиска, настройки (telegram.md §2, E9-4).

Без бизнес-логики: данные и действия идут через core `/internal/tg/*`. Тест — в `assessment.py`.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from html import escape

import structlog
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from fsp_bot.core_client import CoreClient, CoreError
from fsp_bot.states import Fsp, Settings

log = structlog.get_logger()

BTN_FSP, BTN_CATEGORY = "🏆 ФСП", "🎯 Категория"
BTN_STATUS, BTN_SETTINGS = "🔥 Статус", "⚙️ Настройки"
ACCOUNT_BUTTONS = (BTN_FSP, BTN_CATEGORY, BTN_STATUS, BTN_SETTINGS)

CORE_DOWN = "Сервис временно недоступен, попробуй чуть позже."
ERRORS = {
    "telegram_unknown": "Telegram не привязан: зарегистрируйся на сайте и привяжи его в профиле.",
    "forbidden": "Это доступно кандидатам.",
    "consent_required": "Нужно согласие на обработку данных: дай его в профиле на сайте.",
    "fsp_not_found": "Участник с такими данными в ФСП не найден.",
    "fsp_already_linked": "Этот участник ФСП уже привязан к другому аккаунту.",
    "candidate_already_linked": "К твоему аккаунту уже привязан другой участник ФСП.",
    "fsp_ambiguous": "Нашлось несколько участников. Укажи ID, а не email.",
    "code_expired": "Код устарел. Начни привязку заново: 🏆 ФСП.",
    "too_many_attempts": "Слишком много неверных попыток. Начни заново через 10 минут.",
    "fsp_not_linked": "Сначала привяжи ФСП: 🏆 ФСП.",
    "sync_too_often": "Обновлять результаты можно раз в 10 минут.",
    "fsp_unavailable": "Интеграция с ФСП сейчас недоступна.",
}

FORMATS = (("remote", "🏠 Удалёнка"), ("hybrid", "🔀 Гибрид"), ("office", "🏢 Офис"))
STATUSES = (("active", "🔥 Активно ищу 7 дней"), ("open", "👀 Открыт"), ("dnd", "🔕 Не беспокоить"))
STATUS_TEXT = {
    "active": "🔥 активно ищу",
    "open": "👀 открыт к предложениям",
    "dnd": "🔕 не беспокоить",
}
_GRADES = {"junior": "Junior", "middle": "Middle", "senior": "Senior"}
_CLAIM_TEXT = {
    "overclaimed": "заявлено {declared}, подтверждено {confirmed}",
    "underclaimed": "заявлено {declared}, подтверждено {confirmed}",
    "unconfirmed": "заявлено {declared}, подтверждения теста пока нет",
}
MAX_SALARY = 100_000_000
CODE_RE = re.compile(r"^\d{6}$")

TEST_HINT = "🧪 Категорию подтверждает тест: короткий (6–8 заданий) можно пройти прямо здесь."


def _e(value: object) -> str:
    return escape(str(value), quote=False)


def _money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def error_text(exc: CoreError) -> str:
    if exc.status == 429 and exc.code not in ERRORS:
        return "Слишком часто, попробуй чуть позже."
    return ERRORS.get(exc.code, CORE_DOWN)


def parse_salary(text: str) -> int | None | bool:
    """`230000`, `230 000`, `230к` → число; `0` и `нет` → `None` (очистить); мусор → `False`."""
    raw = text.strip().lower().replace(" ", "").replace(" ", "").replace("₽", "")
    if raw in ("0", "нет", "-"):
        return None
    mult = 1
    if raw.endswith(("к", "k")):
        raw, mult = raw[:-1], 1000
    if not raw.isdigit():
        return False
    value = int(raw) * mult
    return value if 0 < value <= MAX_SALARY else False


# --- тексты -----------------------------------------------------------------------------


def fsp_overview(d: dict) -> str:
    if not d.get("linked"):
        return (
            "🏆 <b>ФСП</b>\n"
            "Аккаунт ФСП не привязан. "
            "Привяжи его, чтобы результаты соревнований попали в профиль."
        )
    mark = "подтверждено" if d.get("verified") else "ждёт подтверждения"
    lines = [f"🏆 <b>ФСП</b>: аккаунт привязан ({mark})"]
    for label in d.get("achievements") or []:
        lines.append(f"• {_e(label)}")
    if not d.get("achievements"):
        lines.append("Результатов пока нет. Обновить: кнопка ниже.")
    teams = d.get("teams") or []
    if teams:
        lines.append("Команды: " + ", ".join(_e(t) for t in teams))
    return "\n".join(lines)


def category_status(d: dict) -> str:
    lines = ["🎯 <b>Категория</b>"]
    cats = d.get("categories") or []
    for c in cats:
        grade = _GRADES.get(c["grade"], c["grade"])
        tail = " · требует подтверждения" if c.get("needs_confirmation") else ""
        lines.append(f"✔︎ {_e(c['title'])} · {grade}{tail}")
    confirmed = {c["profession"] for c in cats}
    for claim in d.get("claims") or []:
        tpl = _CLAIM_TEXT.get(claim["status"])
        if tpl is None or (claim["status"] == "unconfirmed" and claim["profession"] in confirmed):
            continue
        declared = _GRADES.get(claim.get("declared_grade") or "", "")
        confirmed_grade = _GRADES.get(claim.get("confirmed_grade") or "", "")
        if claim["status"] == "unconfirmed" and not declared:
            continue
        lines.append(
            f"• {_e(claim['title'])}: " + tpl.format(declared=declared, confirmed=confirmed_grade)
        )
    if not cats:
        lines.append("Категория определяется тестом. Подтверждённой категории пока нет.")
    lines.append("")
    lines.append(TEST_HINT)
    return "\n".join(lines)


def settings_text(d: dict) -> str:
    salary = f"от {_money(d['salary_min'])} ₽" if d.get("salary_min") else "не указана"
    names = dict(FORMATS)
    fmts = ", ".join(names[f].split(" ", 1)[1] for f in d.get("formats") or [] if f in names)
    return (
        "⚙️ <b>Настройки</b>\n"
        f"Минимальная зарплата: {salary}\n"
        f"Формат: {fmts or 'любой'}\n"
        f"Статус: {STATUS_TEXT.get(d.get('search_status'), 'открыт')}\n"
        "Остальное (город, релокация, видимость) — на сайте."
    )


def status_keyboard(current: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=("✓ " if code == current else "") + label, callback_data=f"s:{code}"
                )
            ]
            for code, label in STATUSES
        ]
    )


def settings_keyboard(d: dict) -> InlineKeyboardMarkup:
    chosen = set(d.get("formats") or [])
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Минимальная зарплата", callback_data="g:sal")],
            [
                InlineKeyboardButton(
                    text=("✓ " if code in chosen else "") + label, callback_data=f"g:f:{code}"
                )
                for code, label in FORMATS
            ],
        ]
    )


# --- обработчики ------------------------------------------------------------------------

SiteButton = Callable[[int, str, str], Awaitable[list[InlineKeyboardButton]]]


def build_account_router(core: CoreClient, site_button: SiteButton) -> Router:
    router = Router()

    async def edit(msg: Message, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
        try:
            await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except TelegramBadRequest as exc:
            log.info("edit_skipped", reason=str(exc)[:60])

    async def with_site(uid: int, kb_rows: list[list[InlineKeyboardButton]], text: str, path: str):
        row = await site_button(uid, text, path)
        return InlineKeyboardMarkup(inline_keyboard=[*kb_rows, *([row] if row else [])])

    # ФСП ------------------------------------------------------------------------------
    @router.message(Command("fsp"))
    @router.message(F.text == BTN_FSP)
    async def fsp_menu(message: Message, state: FSMContext) -> None:
        user = message.from_user
        if user is None:
            return
        await state.clear()
        try:
            data = await core.fsp(user.id)
        except CoreError as exc:
            await message.answer(error_text(exc))
            return
        if data.get("linked"):
            rows = [[InlineKeyboardButton(text="🔄 Обновить результаты", callback_data="f:s")]]
        else:
            rows = [[InlineKeyboardButton(text="🔗 Ввести ID или email", callback_data="f:l")]]
        kb = await with_site(
            user.id,
            rows,
            "🔑 Войти через ФСП" if not data.get("linked") else "🌐 Открыть профиль",
            "/me",
        )
        await message.answer(fsp_overview(data), parse_mode="HTML", reply_markup=kb)

    @router.callback_query(F.data == "f:l")
    async def fsp_link_ask(call: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(Fsp.awaiting_id)
        await call.answer()
        if isinstance(call.message, Message):
            await call.message.answer("Пришли ID участника или email из ФСП. Отмена: /cancel")

    @router.message(Fsp.awaiting_id, F.text, ~F.text.startswith("/"), ~F.text.in_(ACCOUNT_BUTTONS))
    async def fsp_link(message: Message, state: FSMContext) -> None:
        user = message.from_user
        value = (message.text or "").strip()
        if user is None or not value:
            return
        try:
            res = await core.fsp_link(user.id, value)
        except CoreError as exc:
            if exc.code not in ("fsp_not_found", "fsp_ambiguous") and exc.status != 429:
                await state.clear()
            await message.answer(error_text(exc))
            return
        if res.get("method") == "code":
            await state.set_state(Fsp.awaiting_code)
            contact = f" на {_e(res['masked_contact'])}" if res.get("masked_contact") else ""
            await message.answer(
                f"Отправили код подтверждения{contact}. Пришли 6 цифр. Отмена: /cancel",
                parse_mode="HTML",
            )
        else:
            await state.clear()
            await message.answer("Аккаунт привязан, подтверждение ФСП придёт позже.")

    @router.message(
        Fsp.awaiting_code, F.text, ~F.text.startswith("/"), ~F.text.in_(ACCOUNT_BUTTONS)
    )
    async def fsp_code(message: Message, state: FSMContext) -> None:
        user = message.from_user
        code = (message.text or "").strip()
        if user is None:
            return
        if not CODE_RE.match(code):
            await message.answer("Нужны 6 цифр. Отмена: /cancel")
            return
        try:
            res = await core.fsp_verify(user.id, code)
        except CoreError as exc:
            if exc.status != 429 or exc.code == "too_many_attempts":
                await state.clear()
            await message.answer(error_text(exc))
            return
        if not res.get("verified"):
            await message.answer("Код неверный. Попробуй ещё раз или /cancel.")
            return
        await state.clear()
        await message.answer("✅ ФСП подтверждена. Результаты скоро появятся в профиле.")

    @router.callback_query(F.data == "f:s")
    async def fsp_sync(call: CallbackQuery) -> None:
        try:
            await core.fsp_sync(call.from_user.id)
        except CoreError as exc:
            await call.answer(error_text(exc), show_alert=True)
            return
        await call.answer("Обновляю результаты, пришлю уведомление", show_alert=True)

    # Категория и статус теста ------------------------------------------------------------
    @router.message(Command("category"))
    @router.message(F.text == BTN_CATEGORY)
    async def category(message: Message, state: FSMContext) -> None:
        user = message.from_user
        if user is None:
            return
        await state.clear()
        try:
            data = await core.category(user.id)
        except CoreError as exc:
            await message.answer(error_text(exc))
            return
        rows = [[InlineKeyboardButton(text="🧪 Короткий тест в боте", callback_data="t:s")]]
        kb = await with_site(user.id, rows, "🌐 Полный тест на сайте", "/me/assessment")
        await message.answer(category_status(data), parse_mode="HTML", reply_markup=kb)

    # Статус поиска -----------------------------------------------------------------------
    @router.message(Command("status"))
    @router.message(F.text == BTN_STATUS)
    async def status_menu(message: Message, state: FSMContext) -> None:
        user = message.from_user
        if user is None:
            return
        await state.clear()
        try:
            current = (await core.settings(user.id)).get("search_status")
        except CoreError as exc:
            await message.answer(error_text(exc))
            return
        text = f"🔥 <b>Статус поиска</b>: {STATUS_TEXT.get(current, 'открыт')}"
        await message.answer(text, parse_mode="HTML", reply_markup=status_keyboard(current))

    @router.callback_query(F.data.regexp(r"^s:(active|open|dnd)$"))
    async def status_set(call: CallbackQuery) -> None:
        code = (call.data or "").split(":")[1]
        try:
            res = await core.set_status(call.from_user.id, code)
        except CoreError as exc:
            await call.answer(error_text(exc), show_alert=True)
            return
        await call.answer("Готово")
        if isinstance(call.message, Message):
            current = res.get("search_status", code)
            text = f"🔥 <b>Статус поиска</b>: {STATUS_TEXT.get(current, 'открыт')}"
            await edit(call.message, text, status_keyboard(current))

    # Настройки ---------------------------------------------------------------------------
    @router.message(Command("settings"))
    @router.message(F.text == BTN_SETTINGS)
    async def settings_menu(message: Message, state: FSMContext) -> None:
        user = message.from_user
        if user is None:
            return
        await state.clear()
        try:
            data = await core.settings(user.id)
        except CoreError as exc:
            await message.answer(error_text(exc))
            return
        kb = settings_keyboard(data)
        row = await site_button(user.id, "🌐 Все настройки на сайте", "/me")
        if row:
            kb.inline_keyboard.append(row)
        await message.answer(settings_text(data), parse_mode="HTML", reply_markup=kb)

    @router.callback_query(F.data.startswith("g:f:"))
    async def toggle_format(call: CallbackQuery) -> None:
        code = (call.data or "").removeprefix("g:f:")
        if code not in dict(FORMATS):
            await call.answer()
            return
        try:
            cur = await core.settings(call.from_user.id)
            chosen = set(cur.get("formats") or [])
            chosen ^= {code}
            data = await core.update_settings(call.from_user.id, formats=sorted(chosen))
        except CoreError as exc:
            await call.answer(error_text(exc), show_alert=True)
            return
        await call.answer()
        if isinstance(call.message, Message):
            await edit(call.message, settings_text(data), settings_keyboard(data))

    @router.callback_query(F.data == "g:sal")
    async def salary_ask(call: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(Settings.awaiting_salary)
        await call.answer()
        if isinstance(call.message, Message):
            await call.message.answer(
                "Пришли минимальную зарплату в ₽/мес на руки, например 230000 или 230к. "
                "«нет» — убрать. Отмена: /cancel"
            )

    @router.message(
        Settings.awaiting_salary, F.text, ~F.text.startswith("/"), ~F.text.in_(ACCOUNT_BUTTONS)
    )
    async def salary_set(message: Message, state: FSMContext) -> None:
        user = message.from_user
        if user is None:
            return
        value = parse_salary(message.text or "")
        if value is False:
            await message.answer("Не понял сумму. Пример: 230000 или 230к. Отмена: /cancel")
            return
        try:
            data = await core.update_settings(user.id, salary_min=value)
        except CoreError as exc:
            if exc.status != 429:
                await state.clear()
            await message.answer(error_text(exc))
            return
        await state.clear()
        await message.answer(
            settings_text(data), parse_mode="HTML", reply_markup=settings_keyboard(data)
        )

    return router
