"""PDF-профиль `GET /candidates/me/profile.pdf`."""
# ruff: noqa: E501

from test_candidate_profile_form import PWD, _patch, _user, c  # noqa: F401


def test_pdf_requires_auth_and_candidate(c):  # noqa: F811
    assert c.get("/candidates/me/profile.pdf").status_code == 401
    r = c.post("/auth/register", json={"email": "hr@x.ru", "password": PWD, "role": "employer"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert c.get("/candidates/me/profile.pdf", headers=h).status_code == 403


def test_pdf_contains_cyrillic_and_profile(c):  # noqa: F811
    import fitz

    h = _user(c, "pdf@x.ru")
    _patch(c, h, {"stack": [{"slug": "python", "years": 3}], "contacts": {"email": "me@x.ru"},
                  "experience_months": 30})  # fmt: skip
    r = c.get("/candidates/me/profile.pdf", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")
    text = "".join(pg.get_text() for pg in fitz.open(stream=r.content, filetype="pdf"))
    for needle in ("Навыки", "me@x.ru", "Стаж"):
        assert needle in text
    assert "из чего сложился" not in text
    for needle in ():
        assert needle in text


def test_html_escapes_user_text():
    from types import SimpleNamespace as N

    from app.candidates import pdf

    skill = N(skill=N(name="Пайтон"), level=2, sources=["test"], claimed_only=False)
    p = N(
        pseudonym="<b>x</b>", profile_version=1, category=None,
        grade=N(grade=None, preliminary=False, breakdown=[]),
        contacts=None, experience_months=None, preferences=N(city="<i>", salary_min=None),
        skills=[skill], fsp=None, experience=[], claimed_soft=[], visibility=N(companies=False),
    )  # fmt: skip
    html = pdf.build_html(p, [])
    assert "<b>x</b>" not in html and "&lt;b&gt;" in html and "&lt;i&gt;" in html
    assert "Пайтон" in html
    with_photo = pdf.build_html(p, [], photo=(b"\x89PNG\r\n\x1a\n", "candidate-avatars/u/a.png"))
    assert 'class="photo"' in with_photo and "data:image/png;base64," in with_photo
    assert 'class="photo"' not in html  # без аватара блока нет


def test_resume_html_sections_cyrillic_no_breakdown():
    from datetime import UTC, datetime
    from types import SimpleNamespace as N

    from app.candidates import pdf

    sk = lambda n, t: N(skill=N(name=n, type=t), level=2, sources=["test"], claimed_only=False)  # noqa: E731
    p = N(
        pseudonym="Лис-42", full_name="Иванова Мария", profile_version=3,
        category=N(primary_role="Backend-разработчик"),
        grade=N(grade="middle", preliminary=False, breakdown=[N(label="СЕКРЕТНЫЙ-СИГНАЛ", points=1.0)]),
        contacts=N(email="m@x.ru", phone="+7 900 000-00-00", telegram="@masha_dev"),
        desired_roles=["Тимлид"], experience_months=40,
        preferences=N(city="Казань", salary_min=200000, formats=["remote"], relocation=True),
        skills=[sk("Пайтон", "hard"), sk("Алгоритмы", "fundamental")], claimed_soft=["Коммуникация"],
        fsp=N(verified=True, achievements=[N(title="Чемпионат", level="Всероссийский", place=2, of=40, year=2025)],
              ranks=[N(discipline="Алгоритмы", rank="КМС")]),
        experience=[N(title="Разработчик", company="Вымышленная Компания", start="2022", end=None, skills=["Пайтон"])],
        education=[N(institution="КФУ", degree="Бакалавр", field="Информатика", year_end=2022)],
        links=["https://example.com/maria"], visibility=N(companies=False),
    )  # fmt: skip
    html = pdf.build_html(p, [], now=datetime(2026, 1, 1, tzinfo=UTC))
    for needle in (
        "Иванова Мария",
        "Backend-разработчик · Middle",
        "m@x.ru",
        "Тимлид",
        "Казань",
        "удалённо",
        "Хард-скиллы",
        "Фундамент",
        "Софт-скиллы",
        "Коммуникация",
        "Опыт",
        "Вымышленная Компания",
        "Образование",
        "КФУ",
        "Достижения ФСП",
        "2 место из 40",
        "КМС",
        "Ссылки",
        "example.com/maria",
    ):
        assert needle in html, needle
    assert "СЕКРЕТНЫЙ-СИГНАЛ" not in html and "из чего сложился" not in html
