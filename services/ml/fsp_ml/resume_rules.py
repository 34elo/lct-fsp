"""Правила без LLM (шаги 2 и 6): контакты, ссылки, периоды работы, стаж."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from fsp_contracts.ml import ResumeExperience

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-zA-Zа-яА-Я]{2,}")
_PHONE = re.compile(r"(?<![\w+])(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)")
_TG_LINK = re.compile(r"(?:https?://)?t\.me/([A-Za-z0-9_]{5,32})", re.I)
_TG_HANDLE = re.compile(r"(?i)(?:telegram|телеграм|tg)\s*[:\-]?\s*@?([A-Za-z0-9_]{5,32})\b")
_LINK = re.compile(
    r"(?:https?://)?(?:www\.)?(?:github\.com|gitlab\.com|linkedin\.com/in|habr\.com/(?:ru/)?users"
    r"|career\.habr\.com)/[A-Za-z0-9_.\-]+",
    re.I,
)


@dataclass
class Contacts:
    email: str | None = None
    phone: str | None = None
    telegram: str | None = None
    links: list[str] = field(default_factory=list)


def _phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    return "+7" + digits[1:]


def contacts(text: str) -> Contacts:
    out = Contacts()
    if m := _EMAIL.search(text):
        out.email = m.group(0)
    if m := _PHONE.search(text):
        out.phone = _phone(m.group(0))
    if m := _TG_LINK.search(text) or _TG_HANDLE.search(text):
        out.telegram = "@" + m.group(1)
    seen: dict[str, str] = {}
    for m in _LINK.finditer(text):
        url = m.group(0).rstrip(".")
        url = re.sub(r"^(?:https?://)?(?:www\.)?", "https://", url, flags=re.I)
        seen.setdefault(url.lower(), url)
    out.links = list(seen.values())
    return out


# --- периоды: «янв 2021 – н.в.», «2019–2022», «03.2020 — 05.2023», «2022-03» ---

_MONTHS = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6, "июл": 7, "авг": 8,
    "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_NOW = re.compile(r"^(?:н\.?\s*в\.?|наст|по\s+наст|сейчас|текущ|present|now|current|today)", re.I)
_ISO = re.compile(r"^(\d{4})[-./](\d{1,2})$")
_MY = re.compile(r"^(\d{1,2})[-./](\d{4})$")
_WORD = re.compile(r"^([a-zа-яё]{3,})\.?\s*(\d{4})$", re.I)
_YEAR = re.compile(r"^(\d{4})$")


def parse_month(raw: str | None) -> str | None:
    """Одна дата → `YYYY-MM`; «н.в.», пусто или нераспознанное → None."""
    if not raw:
        return None
    s = raw.strip().lower().replace("ё", "е")
    y = mo = None
    if m := _ISO.match(s):
        y, mo = int(m.group(1)), int(m.group(2))
    elif m := _MY.match(s):
        mo, y = int(m.group(1)), int(m.group(2))
    elif m := _WORD.match(s):
        mo, y = _MONTHS.get(m.group(1)[:3]), int(m.group(2))
    elif m := _YEAR.match(s):
        y, mo = int(m.group(1)), 1
    if y is None or mo is None or not 1 <= mo <= 12 or not 1970 <= y <= 2100:
        return None
    return f"{y:04d}-{mo:02d}"


def is_present(raw: str | None) -> bool:
    return bool(raw) and bool(_NOW.match(raw.strip()))


def parse_end(raw: str | None) -> str | None:
    """Конец периода: только год → декабрь (если год прошёл, это полный год)."""
    if not raw or is_present(raw):
        return None
    value = parse_month(raw)
    if value and _YEAR.match(raw.strip()):
        value = value[:5] + "12"
    return value


# --- стаж ---


def _ym(value: str) -> int:
    return int(value[:4]) * 12 + int(value[5:7]) - 1


def _is_internship(e: ResumeExperience) -> bool:
    title = (e.title or "").lower()
    return any(w in title for w in ("стажер", "стажёр", "intern", "практикант", "trainee"))


def total_experience_months(experience: list[ResumeExperience], today: date) -> int:
    """Сумма непересекающихся интервалов коммерческого опыта, стажировки × 0.5.

    Считаем как core (`resumes.service.experience_months`): конец не включается,
    «2022-03 … 2022-05» = 2 мес. Пересечение со стажировкой засчитывается один раз
    по полной ставке.
    """
    now = today.year * 12 + today.month - 1
    weight: dict[int, float] = {}
    for e in experience:
        if not e.is_commercial or not e.start:
            continue
        start = _ym(e.start)
        end = min(_ym(e.end), now) if e.end else now
        w = 0.5 if _is_internship(e) else 1.0
        for m in range(start, end):
            weight[m] = max(weight.get(m, 0.0), w)
    return int(sum(weight.values()))
