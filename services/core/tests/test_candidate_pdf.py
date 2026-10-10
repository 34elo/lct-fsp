"""E20-6: PDF-профиль `GET /candidates/me/profile.pdf`."""

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
    for needle in ("Навыки и доверие", "me@x.ru", "Стаж"):
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
    assert "Пайтон" in html and "●●○○" in html and "тест" in html
    assert pdf.dots(3) == "●●●○" and pdf.dots(9) == "●●●●"
    with_photo = pdf.build_html(p, [], photo=(b"\x89PNG\r\n\x1a\n", "candidate-avatars/u/a.png"))
    assert 'class="photo"' in with_photo and "data:image/png;base64," in with_photo
    assert 'class="photo"' not in html  # без аватара блока нет
