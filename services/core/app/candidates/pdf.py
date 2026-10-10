"""E20-6, E41-13: PDF-резюме кандидата (HTML → WeasyPrint). Только владелец, контакты — свои.

Строится из уже собранных данных (`CandidateProfile` + грейды теста); ПДн в логи не пишем.
Объяснения «из чего сложился грейд» в резюме нет.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from html import escape
from typing import Any

from fsp_contracts.assessment import CandidateGrade

GRADE_TITLES = {
    "intern": "Intern", "junior": "Junior", "junior_plus": "Junior+", "middle": "Middle",
    "middle_plus": "Middle+", "senior": "Senior", "lead": "Lead",
}  # fmt: skip
FORMAT_TITLES = {"office": "офис", "hybrid": "гибрид", "remote": "удалённо"}
TYPE_TITLES = {
    "hard": "Хард-скиллы", "fundamental": "Фундамент", "thinking": "Инженерное мышление",
    "business": "Бизнес и домен", "soft": "Софт-скиллы", "experience": "Опыт и инструменты",
}  # fmt: skip
TYPE_ORDER = list(TYPE_TITLES)

# ruff: noqa: E501
# Две краски: графит и один тёплый акцент (хвойный зелёный), без синего.
CSS = """
@page { size: A4; margin: 15mm 16mm; @bottom-right { content: counter(page) " / " counter(pages);
  font-size: 8pt; color: #7a7a72; } }
body { font-family: "DejaVu Sans", "Liberation Sans", sans-serif; font-size: 9.5pt; color: #222; line-height: 1.35; }
h1 { font-size: 21pt; margin: 0 0 2pt; color: #222; font-weight: bold; }
h2 { font-size: 10.5pt; color: #2f5d50; text-transform: uppercase; letter-spacing: .6pt;
  border-bottom: 1pt solid #2f5d50; padding-bottom: 2pt; margin: 13pt 0 6pt; }
.role { font-size: 12pt; color: #2f5d50; margin-bottom: 4pt; }
img.photo { float: right; width: 28mm; height: 28mm; object-fit: cover; margin-left: 8mm; }
.muted { color: #6b6b64; font-size: 8.5pt; }
.line { margin: 1pt 0; }
.item { margin: 0 0 6pt; page-break-inside: avoid; }
.item .t { font-weight: bold; }
.item .when { float: right; color: #6b6b64; font-size: 8.5pt; }
.grp { margin: 0 0 3pt; }
"""


def _e(v: Any) -> str:
    return escape("" if v is None else str(v))


def _date(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%d.%m.%Y")


def _section(title: str, body: str) -> str:
    return f"<h2>{title}</h2>{body}"


def build_html(
    profile: Any,
    grades: list[CandidateGrade],
    now: datetime | None = None,
    photo: tuple[bytes, str] | None = None,
) -> str:
    """Резюме владельца (E41-13): шапка, контакты, навыки по типам, опыт, образование, ФСП, ссылки.

    `profile` — `CandidateProfile`; все значения экранируются. `photo` — (байты, ключ файла)
    аватара (E41-12), вшивается как data-URI. `grades` — подтверждённые грейды теста."""
    now = now or datetime.now(UTC)
    p = profile
    out: list[str] = []
    if photo:
        mime = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}.get(
            photo[1].rsplit(".", 1)[-1], "image/png"
        )
        b64 = base64.b64encode(photo[0]).decode()
        out.append(f'<img class="photo" alt="" src="data:{mime};base64,{b64}">')

    name = getattr(p, "full_name", None) or p.pseudonym
    out.append(f"<h1>{_e(name)}</h1>")
    cat = p.category
    g = p.grade
    role = _e(cat.primary_role) if cat and cat.primary_role else ""
    if g.grade:
        grade_txt = GRADE_TITLES.get(g.grade, g.grade) + (
            " (предварительно)" if g.preliminary else ""
        )
        role = f"{role} · {_e(grade_txt)}" if role else _e(grade_txt)
    if role:
        out.append(f'<div class="role">{role}</div>')

    if p.contacts:
        parts = [p.contacts.email, p.contacts.phone, p.contacts.telegram]
        if any(parts):
            out.append(f'<div class="line">{_e(" · ".join(x for x in parts if x))}</div>')
    desired = getattr(p, "desired_roles", None) or []
    if desired:
        out.append(f'<div class="line">Желаемая роль: {_e(", ".join(desired))}</div>')
    where = []
    if p.preferences.city:
        where.append(_e(p.preferences.city))
    fmts = [
        FORMAT_TITLES.get(str(getattr(f, "value", f)), str(f))
        for f in getattr(p.preferences, "formats", None) or []
    ]
    if fmts:
        where.append("формат: " + _e(", ".join(fmts)))
    if getattr(p.preferences, "relocation", False):
        where.append("готов к переезду")
    if p.preferences.salary_min:
        where.append(f"от {p.preferences.salary_min:,} ₽/мес".replace(",", " "))
    if where:
        out.append(f'<div class="line">{" · ".join(where)}</div>')
    if p.experience_months is not None:
        out.append(
            f'<div class="line muted">Стаж: {p.experience_months // 12} г. {p.experience_months % 12} мес.</div>'
        )

    # Навыки списком, группы по типу
    by_type: dict[str, list[str]] = {}
    for s in p.skills:
        by_type.setdefault(getattr(s.skill, "type", None) or "hard", []).append(_e(s.skill.name))
    soft = by_type.setdefault("soft", [])
    soft += [x for x in (_e(v) for v in (p.claimed_soft or [])) if x not in soft]
    if any(by_type.values()):
        order = TYPE_ORDER + [t for t in by_type if t not in TYPE_ORDER]
        rows = [
            f'<div class="grp"><b>{_e(TYPE_TITLES.get(t, t))}:</b> {", ".join(by_type[t])}</div>'
            for t in order
            if by_type.get(t)
        ]
        out.append(_section("Навыки", "".join(rows)))

    if p.experience:
        items = []
        for x in p.experience:
            title = _e(x.title or "—") + (f", {_e(x.company)}" if x.company else "")
            when = f"{_e(x.start or '')} — {_e(x.end or 'н. в.')}"
            sk = f'<div class="muted">{_e(", ".join(x.skills))}</div>' if x.skills else ""
            items.append(
                f'<div class="item"><span class="when">{when}</span><span class="t">{title}</span>{sk}</div>'
            )
        out.append(_section("Опыт", "".join(items)))

    education = getattr(p, "education", None) or []
    if education:
        items = []
        for ed in education:
            spec = ", ".join(x for x in (ed.degree, ed.field) if x)
            year = f'<span class="when">{ed.year_end}</span>' if ed.year_end else ""
            sub = f'<div class="muted">{_e(spec)}</div>' if spec else ""
            items.append(
                f'<div class="item">{year}<span class="t">{_e(ed.institution or "—")}</span>{sub}</div>'
            )
        out.append(_section("Образование", "".join(items)))

    if p.fsp:
        items = []
        for a in p.fsp.achievements:
            place = (
                f"{a.place} место из {a.of}"
                if a.place and a.of
                else (f"{a.place} место" if a.place else "")
            )
            sub = " · ".join(x for x in (_e(a.level), place) if x)
            items.append(
                f'<div class="item"><span class="when">{a.year}</span><span class="t">{_e(a.title)}</span>'
                f'<div class="muted">{sub}</div></div>'
            )
        if p.fsp.ranks:
            ranks = "; ".join(f"{_e(r.discipline)}: {_e(r.rank)}" for r in p.fsp.ranks)
            items.append(f'<div class="line">Разряды: {ranks}</div>')
        if items:
            note = (
                '<div class="muted">Подтверждено Федерацией спортивного программирования</div>'
                if p.fsp.verified
                else ""
            )
            out.append(_section("Достижения ФСП", "".join(items) + note))

    if grades:
        rows = [
            f'<div class="line">{_e(x.profession)} — {_e(GRADE_TITLES.get(x.grade, x.grade))}'
            f' <span class="muted">(тест от {_date(x.confirmed_at)})</span></div>'
            for x in sorted(grades, key=lambda x: x.profession)
        ]
        out.append(_section("Оценка на платформе", "".join(rows)))

    links = getattr(p, "links", None) or []
    if links:
        out.append(_section("Ссылки", "".join(f'<div class="line">{_e(u)}</div>' for u in links)))

    out.append(f'<p class="muted" style="margin-top:14pt">ФСП Карьера · {_date(now)}</p>')
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        f"<title>Резюме {_e(name)}</title><style>{CSS}</style></head>"
        f"<body>{''.join(out)}</body></html>"
    )


def render_pdf(html: str) -> bytes:
    """Синхронный рендер; из async-кода вызывать через `asyncio.to_thread`."""
    from weasyprint import HTML  # тяжёлый импорт — лениво

    return HTML(string=html).write_pdf()
