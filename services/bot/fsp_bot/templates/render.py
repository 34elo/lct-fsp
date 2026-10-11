from __future__ import annotations

from collections.abc import Callable
from html import escape
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from fsp_contracts.notify import TgButton, TgTemplate

DOTS = "●●●●"


def _e(value: Any) -> str:
    return escape(str(value), quote=False)


def _money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def _dots(level: int) -> str:
    level = max(0, min(4, int(level)))
    return "●" * level + "○" * (4 - level)


_FORMATS = {"remote": "удалёнка", "office": "офис", "hybrid": "гибрид"}
_EMPLOYMENT = {
    "full": "полная занятость",
    "part": "частичная занятость",
    "internship": "стажировка",
    "project": "проект",
}
_MONTHS = (
    "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split()
)
_STATUS_TEXT = {
    "sent": "отправлен",
    "viewed": "просмотрен",
    "accepted": "принят",
    "declined": "отклонён",
    "expired": "срок истёк",
    "withdrawn": "отозван работодателем",
    "interview": "приглашение на интервью",
    "hired": "вас взяли на работу",
    "not_hired": "работодатель принял решение: без найма",
    "interest": "компания интересуется вами, ответ — на сайте",
    "interest_opened": "кандидат открыл интерес, можно отправить приглашение",
}
_MARK = {"plus": "✓", "minus": "⚠", "warn": "⚠"}


def _date_ru(iso: str) -> str:
    """`2026-10-12T09:00:00+00:00` → `12 октября`; не разобрали — как есть."""
    try:
        day, month = int(iso[8:10]), int(iso[5:7])
        return f"{day} {_MONTHS[month - 1]}"
    except (ValueError, IndexError):
        return iso


def offer_new(d: dict) -> str:
    """Поля — как в `notifications.offer_card_data` (core): company_name, vacancy_title, formats…"""
    mark = " ✔︎" if d.get("verified", True) else ""
    rating = (
        f" (ответственность {_e(d['company_responsibility'])}/5)"
        if d.get("company_responsibility") is not None
        else ""
    )
    lines = [
        f"💼 <b>Новый оффер</b> · Компания «{_e(d.get('company_name') or 'без названия')}»"
        f"{mark}{rating}",
        f"<b>{_e(d.get('vacancy_title') or '')}</b>",
    ]
    basis = "на руки" if d.get("salary_basis") == "net" else "до НДФЛ"
    money = f"💰 <b>{_money(d['salary_from'])} – {_money(d['salary_to'])} ₽</b> {basis}"
    extra = [_FORMATS.get(f, f) for f in d.get("formats") or []]
    if d.get("employment_type"):
        extra.append(_EMPLOYMENT.get(d["employment_type"], d["employment_type"]))
    lines.append(" · ".join([money, *map(_e, extra)]))
    if d.get("below_candidate_min"):
        lines.append("⚠ Ниже ваших ожиданий")
    if d.get("match_score") is not None:
        score = float(d["match_score"])
        pct = round(score * 100) if score <= 1 else round(score)
        lines += ["", f"Совпадение <b>{pct}%</b>"]
    for r in d.get("explanation") or []:
        lines.append(f"{_MARK.get(r.get('kind'), '✓')} {_e(r.get('text', ''))}")
    if d.get("message"):
        lines += ["", f"«{_e(d['message'])}»"]
    if d.get("expires_at"):
        lines.append(f"⏳ Ответить до {_e(_date_ru(d['expires_at']))}")
    return "\n".join(lines)


def offer_accepted(d: dict) -> str:
    text = "✅ Вы приняли оффер. Компания получила ваши контакты."
    if d.get("recruiter"):
        text += f" Рекрутер: {_e(d['recruiter'])}"
        if d.get("recruiter_contact"):
            text += f", {_e(d['recruiter_contact'])}"
        text += "."
    return text


def offer_updated(d: dict) -> str:
    """У кандидата данные — `{offer_id, status}`; у участника компании ещё `vacancy_title`."""
    status = _STATUS_TEXT.get(str(d.get("status")), d.get("status_text") or "статус изменился")
    title = d.get("vacancy_title") or d.get("title")
    head = f"💼 Оффер «{_e(title)}»" if title else "💼 Оффер"
    return f"{head}: {_e(status)}"


def offer_message(d: dict) -> str:
    """Текста сообщения в уведомлении нет (может быть ПДн): только факт и куда идти."""
    title = d.get("vacancy_title") or d.get("title")
    where = f" по офферу «{_e(title)}»" if title else " по офферу"
    return f"✉️ Новое сообщение{where}. Ответ — на сайте или в разделе «💼 Офферы»."


def profile_updated(d: dict) -> str:
    lines = []
    if d.get("fsp_result"):
        lines.append(f"🏆 Новый результат ФСП: {_e(d['fsp_result'])}")
    skills = d.get("skills", [])
    if skills:
        lines.append("Навыки обновлены:")
        for s in skills:
            lines.append(f"• {_e(s['name'])} {_dots(s['from'])} → {_dots(s['to'])}")
    if d.get("grade_from") or d.get("grade_to"):
        tail = " (предварительно)" if d.get("grade_preliminary", True) else ""
        lines.append(f"Грейд: {_e(d.get('grade_from', '—'))} → {_e(d.get('grade_to', '—'))}{tail}")
    return "\n".join(lines) or "👤 Профиль обновился"


def resume_progress(d: dict) -> str:
    steps = d.get("steps", [])
    lines = [f"{'✓' if s.get('done') else '◌'} {_e(s.get('text', ''))}" for s in steps]
    return "\n".join(["⏳ Разбираю резюме…", *lines])


def resume_parsed(d: dict) -> str:
    lines = ["📄 <b>Вот что я понял</b>"]
    if d.get("experience"):
        lines.append(f"Опыт: {_e(d['experience'])}")
    if d.get("skills"):
        lines.append("Навыки: " + ", ".join(_e(s) for s in d["skills"]))
    return "\n".join(lines)


def code_progress(d: dict) -> str:
    done, total = d.get("done", 0), d.get("total", 0)
    return f"🧬 Анализирую код: {_e(done)} из {_e(total)} репозиториев"


def fsp_imported(d: dict) -> str:
    return f"🏆 Привязка ФСП выполнена. Импортировано достижений: {_e(d.get('count', 0))}"


def regular_task_published(d: dict) -> str:
    name = d.get("profession_title") or d.get("profession", "")
    return f"📋 Новое задание по профессии {_e(name)}"


def category_subscription(d: dict) -> str:
    n = int(d.get("count", 0) or 0)
    return f"🔔 По подписке «{_e(d.get('title', ''))}»: новых кандидатов — {n}"


def test_result(d: dict) -> str:
    return (
        f"✅ Тест по навыку «{_e(d.get('skill', ''))}» пройден: "
        f"{_e(d.get('score', 0))}%. Навык: {_dots(d.get('level', 0))}"
    )


def uplift(d: dict) -> str:
    lines = [
        "🚀 <b>Быстрый рост</b>",
        f"Подтверди {_e(d.get('skill', ''))} — подойдёшь под {_e(d.get('gain_pct', 0))}% больше "
        f"вакансий ({_e(d.get('from', 0))} → {_e(d.get('to', 0))})"
        + (f", медиана вилок +{_money(d['salary_delta'])} ₽." if d.get("salary_delta") else "."),
    ]
    if d.get("ways"):
        lines.append("Как подтвердить:")
        lines += [f"• {_e(w)}" for w in d["ways"]]
    return "\n".join(lines)


RENDERERS: dict[TgTemplate, Callable[[dict], str]] = {
    TgTemplate.offer_new: offer_new,
    TgTemplate.offer_accepted: offer_accepted,
    TgTemplate.offer_updated: offer_updated,
    TgTemplate.offer_message: offer_message,
    TgTemplate.profile_updated: profile_updated,
    TgTemplate.resume_progress: resume_progress,
    TgTemplate.resume_parsed: resume_parsed,
    TgTemplate.code_progress: code_progress,
    TgTemplate.fsp_imported: fsp_imported,
    TgTemplate.regular_task_published: regular_task_published,
    TgTemplate.test_result: test_result,
    TgTemplate.uplift: uplift,
    TgTemplate.category_subscription: category_subscription,
}


def render(template: TgTemplate, data: dict) -> str:
    return RENDERERS[template](data)


def render_keyboard(buttons: list[list[TgButton]]) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    rows = [
        [InlineKeyboardButton(text=b.text, callback_data=b.callback_data, url=b.url) for b in row]
        for row in buttons
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


_GRADES = {
    "intern": "Intern",
    "junior": "Junior",
    "middle": "Middle",
    "senior": "Senior",
    "lead": "Lead",
}


def profile_summary(d: dict) -> str:
    """Краткий профиль: категория, грейд, топ-6 навыков, ФСП."""
    lines = ["👤 <b>Твой профиль</b>"]
    if d.get("primary_role"):
        lines.append(f"Категория: {_e(d['primary_role'])}")
    if d.get("grade"):
        tail = " (предварительно)" if d.get("grade_preliminary", True) else ""
        lines.append(f"Грейд: {_e(_GRADES.get(d['grade'], d['grade']))}{tail}")
    skills = d.get("skills") or []
    if skills:
        lines.append("")
        for s in skills:
            mark = " <i>(заявлено)</i>" if s.get("claimed_only") else ""
            lines.append(f"• {_e(s['name'])} {_dots(s.get('level', 0))}{mark}")
    for label in d.get("fsp") or []:
        lines.append(f"🏆 {_e(label)}")
    if not (skills or d.get("grade")):
        lines.append("Пока пусто. Пришли резюме: 📄 Резюме.")
    return "\n".join(lines)


# callback_data причин отказа → DeclineReason core
DECLINE_CODES = {
    "ls": "low_salary",
    "ws": "wrong_stack",
    "wf": "wrong_format",
    "wg": "wrong_grade",
    "nl": "not_looking",
    "ot": "other",
}
_DECLINE_LABELS = (
    ("ls", "💸 Мало денег"),
    ("ws", "🧱 Не тот стек"),
    ("wf", "🏠 Не подходит формат"),
    ("wg", "📊 Не тот уровень"),
    ("nl", "😴 Не ищу сейчас"),
    ("ot", "✍️ Другое"),
)


def offer_keyboard(offer_id: str, status: str) -> InlineKeyboardMarkup | None:
    """Ответить можно, пока оффер `sent|viewed`; после принятия кнопок нет (чата нет)."""
    if status in ("sent", "viewed"):
        rows = [
            [
                InlineKeyboardButton(text="✅ Принять", callback_data=f"o:a:{offer_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"o:d:{offer_id}"),
            ],
            [InlineKeyboardButton(text="📄 Подробнее", callback_data=f"o:v:{offer_id}")],
        ]
    else:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


def decline_keyboard(offer_id: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"o:r:{offer_id}:{code}")
        for code, label in _DECLINE_LABELS
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data=f"o:b:{offer_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
