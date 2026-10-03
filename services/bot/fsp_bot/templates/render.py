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


def offer_new(d: dict) -> str:
    company = _e(d.get("company", "Компания"))
    mark = " ✔︎" if d.get("verified") else ""
    rating = f" (ответственность {d['rating']}/5)" if d.get("rating") is not None else ""
    lines = [
        f"💼 <b>Новый оффер</b> · Компания «{company}»{mark}{rating}",
        f"<b>{_e(d.get('title', ''))}</b>",
    ]
    money = f"💰 <b>{_money(d['salary_from'])} – {_money(d['salary_to'])} ₽</b> на руки"
    extra = [x for x in (d.get("format"), d.get("employment")) if x]
    lines.append(" · ".join([money, *map(_e, extra)]))
    if d.get("below_min") is not None:
        lines.append(f"⚠ Ниже ваших ожиданий (от {_money(d['below_min'])} ₽)")
    if d.get("match") is not None:
        lines += ["", f"Совпадение <b>{_e(d['match'])}%</b>"]
    for r in d.get("reasons", []):
        lines.append(f"{'✓' if r.get('ok', True) else '⚠'} {_e(r.get('text', ''))}")
    if d.get("message"):
        lines += ["", f"«{_e(d['message'])}»"]
    if d.get("deadline"):
        lines.append(f"⏳ Ответить до {_e(d['deadline'])}")
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
    return f"💼 Оффер «{_e(d.get('title', ''))}»: {_e(d.get('status_text', 'статус изменился'))}"


def offer_message(d: dict) -> str:
    who = _e(d.get("from", "Собеседник"))
    return f"✉️ <b>{who}</b> по офферу «{_e(d.get('title', ''))}»:\n{_e(d.get('text', ''))}"


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
    TgTemplate.test_result: test_result,
    TgTemplate.uplift: uplift,
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
    """Краткий профиль (telegram.md §2): категория, грейд, топ-6 навыков, ФСП."""
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
