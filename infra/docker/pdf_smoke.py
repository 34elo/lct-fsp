"""Смоук генерации PDF-профиля внутри образа core (WeasyPrint + системные библиотеки).

Запуск: см. job pdf-smoke в .github/workflows/ci.yml.
Падает, если нет libpango/libgobject или шрифтов, либо PDF пустой.
"""

from datetime import UTC, datetime
from types import SimpleNamespace as N

from app.candidates import pdf

skill = N(skill=N(name="Пайтон"), level=2, sources=["test"], claimed_only=False)
profile = N(
    pseudonym="Смоук", profile_version=1, category=None,
    grade=N(grade=None, preliminary=False, breakdown=[]),
    contacts=N(email="smoke@example.com", phone=None, telegram=None),
    experience_months=30, preferences=N(city="Москва", salary_min=None),
    skills=[skill], fsp=None, experience=[], claimed_soft=[], visibility=N(companies=False),
)  # fmt: skip

data = pdf.render_pdf(pdf.build_html(profile, [], now=datetime(2026, 1, 1, tzinfo=UTC)))
assert data.startswith(b"%PDF-"), "нет заголовка PDF"
assert len(data) > 1000, f"PDF подозрительно мал: {len(data)} байт"
print(f"PDF OK: {len(data)} байт")
