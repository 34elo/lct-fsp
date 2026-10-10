"""Короткий тест и регулярные задания в боте (telegram.md §2, E25-3).

Без бизнес-логики: движок, шкала и оценка живут в core (`/assessment/*`, блок 1). Бот только
показывает задание, собирает ответ кнопками или текстом и отправляет его от имени кандидата
(короткий токен, `CoreClient.as_user`). Короткий тест = режим `express` того же движка.

Состояние в FSM (`Test.in_progress`, ключ `t` в данных): источник (попытка или задание), id,
текущее задание, шаги цепочки, накопленные ответы. Кнопки несут счётчик `n`: нажатие по
устаревшей кнопке (повтор, старое сообщение) ничего не отправляет и не дублирует ответ.
"""

from __future__ import annotations

import re
import time
from collections.abc import Awaitable, Callable
from html import escape
from typing import Any

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
from fsp_bot.states import Test

log = structlog.get_logger()

BTN_TASKS = "📋 Задания"
CORE_DOWN = "Сервис временно недоступен, попробуй чуть позже."
GRADES = {"junior": "Junior", "middle": "Middle", "senior": "Senior"}
ERRORS = {
    "telegram_unknown": "Telegram не привязан: зарегистрируйся на сайте и привяжи его в профиле.",
    "forbidden": "Тест доступен кандидатам.",
    "email_not_verified": "Сначала подтверди email на сайте, потом вернись к тесту.",
    "consent_required": "Нужно согласие на обработку данных: дай его в профиле на сайте.",
    "cooldown": "Сейчас этот грейд пройти нельзя: действует пауза между попытками.",
    "no_items": "Для этой профессии и грейда пока нет заданий.",
    "express_disabled": "Короткий тест сейчас выключен. Пройди тест на сайте.",
    "unknown_profession": "Неизвестное направление. Начни заново: /test",
    "attempt_not_active": "Эта попытка уже завершена.",
    "task_closed": "Приём ответов на это задание закрыт.",
    "no_invite": "Приглашения на тест больше нет.",
    "invite_expired": "Приглашение истекло (30 дней). Тест можно пройти заново на сайте.",
    "invite_stale": "Грейд уже не ниже приглашённого.",
}
MAX_TEXT = 3500  # лимит сообщения Telegram 4096, с запасом на заголовок и варианты
MAX_ANSWER = 4000
NUM_RE = re.compile(r"^-?\d+,\d+$")

SiteButton = Callable[[int, str, str], Awaitable[list[InlineKeyboardButton]]]


def _e(value: object) -> str:
    return escape(str(value), quote=False)


def error_text(exc: CoreError) -> str:
    if exc.status == 429:
        return "Слишком часто, попробуй чуть позже."
    return ERRORS.get(exc.code, CORE_DOWN)


# --- чистая логика: шаги, ответы, тексты ------------------------------------------------


def units_of(item: dict) -> list[dict]:
    """Шаги задания: у `chain` — его шаги, у остальных — само задание."""
    steps = item.get("steps")
    return list(steps) if item.get("kind") == "chain" and steps else [item]


def unit_mode(unit: dict) -> str:
    """Как собирать ответ: `choice` (кнопка), `order` (кнопки по порядку), `text`."""
    kind, options = unit.get("kind"), unit.get("options")
    if kind in ("order", "sjt") and options:
        return "order"
    if kind in ("find_bug", "exact", "estimate", "open") or not options:
        return "text"
    return "choice"


def parse_text_answer(unit: dict, raw: str) -> Any:
    """Текст → ответ задания. `find_bug` — номера строк; числа с запятой → с точкой."""
    text = raw.strip()
    if unit.get("kind") == "find_bug":
        return sorted({int(x) for x in re.findall(r"\d+", text)})
    if NUM_RE.match(text):
        return text.replace(",", ".")
    return text[:MAX_ANSWER]


def unit_text(header: str, unit: dict, *, picked: list[int] | None = None) -> str:
    stem = str(unit.get("stem") or "")
    if len(stem) > MAX_TEXT:
        stem = stem[:MAX_TEXT] + "…"
    lines = [header, "", _e(stem)]
    options = unit.get("options") or []
    mode = unit_mode(unit)
    if options:
        lines.append("")
        lines += [f"{i}. {_e(o)}" for i, o in enumerate(options, 1)]
    if mode == "order":
        lines += ["", "Нажимай номера по порядку: от первого места к последнему."]
        if picked:
            lines.append("Твой порядок: " + " → ".join(str(i + 1) for i in picked))
    elif mode == "text":
        hint = (
            "Пришли номера строк через пробел или запятую."
            if unit.get("kind") == "find_bug"
            else "Пришли ответ сообщением."
        )
        lines += ["", hint + " Отмена: /cancel"]
    if unit.get("time_limit_s"):
        lines += ["", f"⏱ ориентир по времени: {int(unit['time_limit_s'])} с"]
    return "\n".join(lines)


def unit_keyboard(
    unit: dict, n: int, picked: list[int] | None = None
) -> InlineKeyboardMarkup | None:
    mode, options = unit_mode(unit), unit.get("options") or []
    if mode == "text":
        return None
    picked = picked or []
    buttons = []
    for i in range(len(options)):
        if mode == "order":
            label = f"✓{picked.index(i) + 1}" if i in picked else str(i + 1)
            buttons.append(InlineKeyboardButton(text=label, callback_data=f"t:r:{n}:{i}"))
        else:
            buttons.append(InlineKeyboardButton(text=str(i + 1), callback_data=f"t:c:{n}:{i}"))
    rows = [buttons[i : i + 5] for i in range(0, len(buttons), 5)]
    if mode == "order" and picked:
        rows.append([InlineKeyboardButton(text="↩️ Сначала", callback_data=f"t:rx:{n}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def result_text(att: dict) -> str:
    res = att.get("result") or {}
    grade = GRADES.get(res.get("grade") or "")
    lines = ["🧪 <b>Короткий тест завершён</b>"]
    if att.get("status") == "passed" and grade:
        lines.append(f"✅ Подтверждён грейд: <b>{grade}</b> (экспресс-проверка)")
        lines.append("Этот результат уже виден в категории и профиле.")
    elif att.get("status") == "failed":
        lines.append("Заявленный грейд пока не подтверждён.")
        lines.append("Повторить можно позже, подробности по паузе — на сайте.")
    else:
        lines.append("Попытка закрыта.")
    if att.get("low_confidence") or res.get("needs_confirmation"):
        lines.append("Оценка предварительная: для надёжности нужен полный тест на сайте.")
    skills = sorted(res.get("by_skill") or [], key=lambda s: -float(s.get("share") or 0))
    if skills:
        lines.append("")
        lines.append(
            "По навыкам: "
            + ", ".join(f"{_e(s['skill'])} {round(float(s['share']) * 100)}%" for s in skills[:5])
        )
    if att.get("invited_grade"):
        name = GRADES.get(att["invited_grade"], att["invited_grade"])
        lines += ["", f"🎉 Приглашаем на тест грейда <b>{name}</b>. Он идёт без пауз."]
    return "\n".join(lines)


def task_line(t: dict) -> str:
    mark = "✅ ответ принят" if t.get("submitted") else "✍️ ждёт ответа"
    if t.get("submitted") and t.get("score") is not None:
        mark += f", балл {round(float(t['score']) * 100)}%"
    return f"• {_e(t['title'])} — {mark}"


# --- роутер -------------------------------------------------------------------------------


def build_assessment_router(
    core: CoreClient, site_button: SiteButton, menu_texts: tuple[str, ...]
) -> Router:
    router = Router()

    async def drop_keyboard(msg: Message | object | None) -> None:
        if isinstance(msg, Message):
            try:
                await msg.edit_reply_markup(reply_markup=None)
            except TelegramBadRequest:
                pass

    async def show_unit(msg: Message, state: FSMContext) -> None:
        t = (await state.get_data())["t"]
        unit = t["units"][t["i"]]
        steps = len(t["units"])
        head = t["head"] + (f" · шаг {t['i'] + 1}/{steps}" if steps > 1 else "")
        await msg.answer(
            unit_text(head, unit),
            parse_mode="HTML",
            reply_markup=unit_keyboard(unit, t["n"]),
        )

    async def begin(msg: Message, state: FSMContext, **t: Any) -> None:
        """Новое задание: шаги, счётчик `n`, время начала."""
        item = t.pop("item")
        t |= {"units": units_of(item), "i": 0, "answers": [], "picked": [], "t0": time.time()}
        t["n"] = int(t.get("n", 0)) + 1
        await state.set_state(Test.in_progress)
        await state.update_data(t=t)
        await show_unit(msg, state)

    async def finish_test(msg: Message, state: FSMContext, uid: int, attempt_id: str) -> None:
        await state.clear()
        att = await core.test_attempt(uid, attempt_id)
        rows: list[list[InlineKeyboardButton]] = []
        if att.get("invited_grade") and att.get("status") == "passed":
            rows.append(
                [
                    InlineKeyboardButton(
                        text="🔼 Пройти приглашённый тест", callback_data=f"t:u:{attempt_id}"
                    )
                ]
            )
        site = await site_button(uid, "🌐 Подробный разбор на сайте", "/me/assessment")
        if site:
            rows.append(site)
        kb = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
        await msg.answer(result_text(att), parse_mode="HTML", reply_markup=kb)

    async def next_question(msg: Message, state: FSMContext, uid: int, attempt_id: str) -> None:
        nxt = await core.test_next(uid, attempt_id)
        if nxt.get("done"):
            await finish_test(msg, state, uid, attempt_id)
            return
        prev = (await state.get_data()).get("t") or {}
        await begin(
            msg,
            state,
            src="attempt",
            id=attempt_id,
            rid=nxt["response_id"],
            head=f"🧪 <b>Задание {nxt.get('seq', '')}</b>",
            item=nxt,
            n=prev.get("n", 0),
        )

    async def submit(msg: Message, state: FSMContext, uid: int, t: dict) -> None:
        answers = t["answers"]
        final = answers if len(t["units"]) > 1 else answers[0]
        if t["src"] == "attempt":
            rt = min(int((time.time() - t["t0"]) * 1000), 86_400_000)
            res = await core.test_answer(uid, t["id"], t["rid"], final, rt)
            if res.get("done"):
                await finish_test(msg, state, uid, t["id"])
            else:
                await next_question(msg, state, uid, t["id"])
        else:
            done = await core.task_answer(uid, t["id"], final)
            await state.clear()
            score = done.get("score")
            tail = f" Балл: {round(float(score) * 100)}%." if score is not None else ""
            await msg.answer("✅ Ответ принят." + tail + " Следующее задание придёт в этот чат.")

    async def accept(msg: Message, state: FSMContext, uid: int, answer: Any) -> None:
        """Ответ на текущий шаг: следующий шаг цепочки или отправка в core."""
        t = (await state.get_data()).get("t")
        if not t:
            await msg.answer("Сессия устарела. Начни заново: /test или 📋 Задания.")
            await state.clear()
            return
        t["answers"].append(answer)
        t["i"] += 1
        t["n"] += 1
        t["picked"] = []
        try:
            if t["i"] < len(t["units"]):
                await state.update_data(t=t)
                await show_unit(msg, state)
            else:
                await submit(msg, state, uid, t)
        except CoreError as exc:
            if exc.status != 429:
                await state.clear()
            await msg.answer(error_text(exc))

    # Старт теста ----------------------------------------------------------------------------
    async def start_attempt(
        msg: Message, state: FSMContext, uid: int, prof: str, grade: str
    ) -> None:
        try:
            try:
                att = await core.test_start(uid, prof, grade)
                await msg.answer(
                    f"🧪 <b>Короткий тест</b>: около {att.get('target', 7)} заданий, "
                    "та же шкала, что на сайте. Прервать: /cancel",
                    parse_mode="HTML",
                )
                attempt_id = att["id"]
            except CoreError as exc:
                if exc.code != "attempt_active" or not exc.detail:
                    raise
                attempt_id = exc.detail  # незавершённая попытка: продолжаем с того же места
                await msg.answer("Продолжаем начатый тест.")
            await next_question(msg, state, uid, attempt_id)
        except CoreError as exc:
            await state.clear()
            await msg.answer(error_text(exc))

    async def begin_test(msg: Message, state: FSMContext, uid: int) -> None:
        await state.clear()
        try:
            survey = await core.test_survey(uid)
            if survey.get("profession") and survey.get("declared_grade"):
                await start_attempt(msg, state, uid, survey["profession"], survey["declared_grade"])
                return
            profs = await core.test_professions(uid)
        except CoreError as exc:
            await msg.answer(error_text(exc))
            return
        rows = [
            [InlineKeyboardButton(text=p["title"], callback_data=f"t:p:{p['slug']}")]
            for p in profs[:12]
        ]
        await msg.answer(
            "🧪 <b>Короткий тест</b>\nВыбери IT-направление:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    @router.message(Command("test"))
    async def test_cmd(message: Message, state: FSMContext) -> None:
        if message.from_user:
            await begin_test(message, state, message.from_user.id)

    @router.callback_query(F.data == "t:s")
    async def test_btn(call: CallbackQuery, state: FSMContext) -> None:
        await call.answer()
        await drop_keyboard(call.message)
        if isinstance(call.message, Message):
            await begin_test(call.message, state, call.from_user.id)

    @router.callback_query(F.data.regexp(r"^t:p:[a-z][a-z0-9_]{1,31}$"))
    async def pick_profession(call: CallbackQuery) -> None:
        slug = (call.data or "").split(":")[2]
        await call.answer()
        await drop_keyboard(call.message)
        if isinstance(call.message, Message):
            rows = [
                [InlineKeyboardButton(text=label, callback_data=f"t:g:{slug}:{g}")]
                for g, label in GRADES.items()
            ]
            await call.message.answer(
                "На какой грейд проверяем?",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )

    @router.callback_query(F.data.regexp(r"^t:g:[a-z][a-z0-9_]{1,31}:(junior|middle|senior)$"))
    async def pick_grade(call: CallbackQuery, state: FSMContext) -> None:
        _, _, slug, grade = (call.data or "").split(":")
        await call.answer()
        await drop_keyboard(call.message)
        if isinstance(call.message, Message):
            await start_attempt(call.message, state, call.from_user.id, slug, grade)

    @router.callback_query(F.data.regexp(r"^t:u:[0-9a-f-]{36}$"))
    async def upgrade(call: CallbackQuery, state: FSMContext) -> None:
        await call.answer()
        await drop_keyboard(call.message)
        if not isinstance(call.message, Message):
            return
        try:
            att = await core.test_upgrade(call.from_user.id, (call.data or "").split(":")[2])
            await call.message.answer("🔼 Начинаем тест приглашённого грейда.")
            await next_question(call.message, state, call.from_user.id, att["id"])
        except CoreError as exc:
            await call.message.answer(error_text(exc))

    # Ответы ---------------------------------------------------------------------------------
    async def current(call: CallbackQuery, state: FSMContext) -> tuple[dict, int] | None:
        """Состояние и номер варианта; устаревшая кнопка (`n` не совпал) — None."""
        parts = (call.data or "").split(":")
        t = (await state.get_data()).get("t")
        if not t or int(parts[2]) != t["n"]:
            await call.answer("Это задание уже закрыто")
            return None
        return t, int(parts[3]) if len(parts) > 3 else -1

    @router.callback_query(F.data.regexp(r"^t:c:\d+:\d+$"))
    async def answer_choice(call: CallbackQuery, state: FSMContext) -> None:
        cur = await current(call, state)
        if cur is None or not isinstance(call.message, Message):
            return
        await call.answer()
        await drop_keyboard(call.message)
        await accept(call.message, state, call.from_user.id, cur[1])

    @router.callback_query(F.data.regexp(r"^t:r:\d+:\d+$"))
    async def answer_order(call: CallbackQuery, state: FSMContext) -> None:
        cur = await current(call, state)
        if cur is None or not isinstance(call.message, Message):
            return
        t, idx = cur
        unit = t["units"][t["i"]]
        if idx in t["picked"] or idx >= len(unit.get("options") or []):
            await call.answer("Уже выбрано")
            return
        t["picked"].append(idx)
        await call.answer()
        if len(t["picked"]) == len(unit["options"]):
            await drop_keyboard(call.message)
            await accept(call.message, state, call.from_user.id, list(t["picked"]))
            return
        await state.update_data(t=t)
        try:
            kb = unit_keyboard(unit, t["n"], t["picked"])
            await call.message.edit_reply_markup(reply_markup=kb)
        except TelegramBadRequest:
            pass

    @router.callback_query(F.data.regexp(r"^t:rx:\d+$"))
    async def order_reset(call: CallbackQuery, state: FSMContext) -> None:
        cur = await current(call, state)
        if cur is None or not isinstance(call.message, Message):
            return
        t = cur[0]
        t["picked"] = []
        await state.update_data(t=t)
        await call.answer()
        try:
            kb = unit_keyboard(t["units"][t["i"]], t["n"])
            await call.message.edit_reply_markup(reply_markup=kb)
        except TelegramBadRequest:
            pass

    @router.message(Test.in_progress, F.text, ~F.text.startswith("/"), ~F.text.in_(menu_texts))
    async def answer_text(message: Message, state: FSMContext) -> None:
        user = message.from_user
        t = (await state.get_data()).get("t")
        if user is None or not t:
            return
        unit = t["units"][t["i"]]
        if unit_mode(unit) != "text":
            await message.answer("Выбери ответ кнопкой под заданием. Отмена: /cancel")
            return
        answer = parse_text_answer(unit, message.text or "")
        if unit.get("kind") == "find_bug" and not answer:
            await message.answer("Нужны номера строк, например: 3 или 2, 5.")
            return
        await accept(message, state, user.id, answer)

    # Регулярные задания -----------------------------------------------------------------------
    @router.message(Command("tasks"))
    @router.message(F.text == BTN_TASKS)
    async def tasks_menu(message: Message, state: FSMContext) -> None:
        user = message.from_user
        if user is None:
            return
        await state.clear()
        try:
            rows = await core.tasks(user.id)
        except CoreError as exc:
            await message.answer(error_text(exc))
            return
        if not rows:
            await message.answer(
                "📋 <b>Задания</b>\nОткрытых заданий пока нет. Они приходят от работодателей "
                "по твоей категории раз в 1–2 недели.",
                parse_mode="HTML",
            )
            return
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=("✅ " if r.get("submitted") else "✍️ ") + r["title"][:48],
                        callback_data=f"t:t:{r['id']}",
                    )
                ]
                for r in rows[:10]
            ]
        )
        text = "📋 <b>Регулярные задания</b>\n" + "\n".join(task_line(r) for r in rows[:10])
        await message.answer(text, parse_mode="HTML", reply_markup=kb)

    @router.callback_query(F.data.regexp(r"^t:t:[0-9a-f-]{36}$"))
    async def open_task(call: CallbackQuery, state: FSMContext) -> None:
        task_id = (call.data or "").split(":")[2]
        await call.answer()
        if not isinstance(call.message, Message):
            return
        try:
            detail = await core.task(call.from_user.id, task_id)
        except CoreError as exc:
            await call.message.answer(error_text(exc))
            return
        if detail.get("submitted"):
            score = detail.get("submission_score")
            tail = (
                f" Балл: {round(float(score) * 100)}%." if score is not None else " Оценка позже."
            )
            await call.message.answer(
                f"✅ <b>{_e(detail['title'])}</b>: ответ принят.{tail}", parse_mode="HTML"
            )
            return
        prev = (await state.get_data()).get("t") or {}
        await begin(
            call.message,
            state,
            src="task",
            id=task_id,
            rid=None,
            head=f"📋 <b>{_e(detail['title'])}</b>",
            item=detail["item"],
            n=prev.get("n", 0),
        )

    return router
