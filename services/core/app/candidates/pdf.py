"""E20-6: PDF-профиль кандидата (HTML → WeasyPrint). Только владелец, контакты — свои.

Строится из уже собранных данных (`CandidateProfile` + грейды теста); ПДн в логи не пишем.
"""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from typing import Any

from fsp_contracts.assessment import CandidateGrade

DOTS_MAX = 4
GRADE_TITLES = {
    "intern": "Intern", "junior": "Junior", "junior_plus": "Junior+", "middle": "Middle",
    "middle_plus": "Middle+", "senior": "Senior", "lead": "Lead",
}  # fmt: skip
SOURCE_TITLES = {
    "self": "заявлено", "resume": "резюме", "github": "код", "test": "тест",
    "ai_interview": "интервью", "fsp": "ФСП", "codeforces": "Codeforces",
}  # fmt: skip

# ruff: noqa: E501
CSS = """
@page { size: A4; margin: 16mm 14mm; @bottom-right { content: counter(page) " / " counter(pages);
  font-size: 8pt; color: #6b6b7b; } }
body { font-family: "DejaVu Sans", "Liberation Sans", sans-serif; font-size: 9.5pt; color: #1b1b25; }
h1 { font-size: 20pt; margin: 0; color: #201880; }
h2 { font-size: 12pt; color: #402FFF; border-bottom: 1.5pt solid #A9A1FF; padding-bottom: 2pt;
  margin: 16pt 0 6pt; }
.head { border-left: 5pt solid #402FFF; padding-left: 10pt; margin-bottom: 8pt; }
.muted { color: #6b6b7b; font-size: 8.5pt; }
table { width: 100%; border-collapse: collapse; }
td, th { text-align: left; padding: 3pt 4pt; border-bottom: .5pt solid #e1e0f0; vertical-align: top; }
th { font-size: 8pt; color: #6b6b7b; font-weight: normal; }
.dots { color: #402FFF; letter-spacing: 1pt; white-space: nowrap; }
.tag { background: #eeecff; color: #201880; padding: 1pt 5pt; border-radius: 6pt; font-size: 8.5pt; }
"""


def dots(level: int) -> str:
    n = max(0, min(DOTS_MAX, int(level)))
    return "●" * n + "○" * (DOTS_MAX - n)


def _e(v: Any) -> str:
    return escape("" if v is None else str(v))


def _date(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%d.%m.%Y")


def _table(head: list[str], rows: list[list[str]]) -> str:
    th = "".join(f"<th>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{th}</tr>{body}</table>"


def build_html(profile: Any, grades: list[CandidateGrade], now: datetime | None = None) -> str:
    """`profile` — `CandidateProfile` из router; все значения экранируются."""
    now = now or datetime.now(UTC)
    p = profile
    out: list[str] = []
    cat = p.category
    role = _e(cat.primary_role) if cat and cat.primary_role else "категория не определена"
    g = p.grade
    grade_txt = GRADE_TITLES.get(g.grade or "", g.grade or "—")
    if g.grade and g.preliminary:
        grade_txt += " (предварительно)"
    out.append(
        f'<div class="head"><h1>{_e(p.pseudonym)}</h1>'
        f"<div>{role} · грейд {_e(grade_txt)}</div>"
        f'<div class="muted">ФСП Карьера · профиль v{p.profile_version} · {_date(now)}</div></div>'
    )
    if p.contacts and any([p.contacts.email, p.contacts.phone, p.contacts.telegram]):
        parts = [p.contacts.email, p.contacts.phone, p.contacts.telegram]
        out.append(f'<div class="muted">Контакты: {_e(" · ".join(x for x in parts if x))}</div>')
    facts = []
    if p.experience_months is not None:
        facts.append(f"Стаж: {p.experience_months // 12} г. {p.experience_months % 12} мес.")
    if p.preferences.city:
        facts.append(f"Город: {_e(p.preferences.city)}")
    if p.preferences.salary_min:
        facts.append(f"От {p.preferences.salary_min:,} ₽/мес".replace(",", " "))
    if facts:
        out.append(f"<p>{' · '.join(facts)}</p>")

    if g.grade and g.breakdown:
        out.append("<h2>Грейд: из чего сложился</h2>")
        out.append(
            _table(["Сигнал", "Баллы"], [[_e(b.label), f"{b.points:+.1f}"] for b in g.breakdown])
        )

    if grades:
        out.append("<h2>Результаты теста</h2>")
        rows = [
            [_e(x.profession), _e(GRADE_TITLES.get(x.grade, x.grade)),
             "требует подтверждения" if x.needs_confirmation else "подтверждён",
             _date(x.confirmed_at), _date(x.valid_until)]
            for x in sorted(grades, key=lambda x: x.profession)
        ]  # fmt: skip
        out.append(_table(["Профессия", "Грейд", "Статус", "Пройден", "Действует до"], rows))

    out.append("<h2>Навыки и доверие</h2>")
    if p.skills:
        rows = []
        for s in p.skills:
            src = ", ".join(SOURCE_TITLES.get(x, x) for x in s.sources) or "—"
            if s.claimed_only:
                src = "только заявлено"
            rows.append([_e(s.skill.name), f'<span class="dots">{dots(s.level)}</span>', _e(src)])
        out.append(_table(["Навык", "Доверие", "Источники"], rows))
    else:
        out.append('<p class="muted">Навыки пока не подтверждены.</p>')

    if p.fsp:
        out.append("<h2>ФСП</h2>")
        rows = [
            [_e(a.title), _e(a.level), f"{a.place} из {a.of}" if a.place and a.of else _e(a.place or "—"),
             str(a.year)]
            for a in p.fsp.achievements
        ]  # fmt: skip
        if rows:
            out.append(_table(["Событие", "Уровень", "Место", "Год"], rows))
        if p.fsp.ranks:
            ranks = " ".join(
                f'<span class="tag">{_e(r.discipline)}: {_e(r.rank)}</span>' for r in p.fsp.ranks
            )
            out.append(f"<p>Разряды: {ranks}</p>")
        out.append(
            f'<p class="muted">{"Данные подтверждены ФСП" if p.fsp.verified else "Не подтверждено ФСП"}</p>'
        )

    if p.experience:
        out.append("<h2>Опыт</h2>")
        rows = [
            [_e(x.title or "—"), _e(x.company or "—") if p.visibility.companies else "—",
             f"{_e(x.start or '')} — {_e(x.end or 'н. в.')}", _e(", ".join(x.skills))]
            for x in p.experience
        ]  # fmt: skip
        out.append(_table(["Роль", "Компания", "Период", "Навыки"], rows))

    if p.claimed_soft:
        tags = " ".join(f'<span class="tag">{_e(x)}</span>' for x in p.claimed_soft)
        out.append(f"<h2>Мягкие навыки (заявлено)</h2><p>{tags}</p>")

    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        f"<title>Профиль {_e(p.pseudonym)}</title><style>{CSS}</style></head>"
        f"<body>{''.join(out)}</body></html>"
    )


def render_pdf(html: str) -> bytes:
    """Синхронный рендер; из async-кода вызывать через `asyncio.to_thread`."""
    from weasyprint import HTML  # тяжёлый импорт — лениво

    return HTML(string=html).write_pdf()
