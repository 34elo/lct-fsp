"""Публичные эндпоинты: бейдж SVG, публичный профиль, OG-превью (E15-1)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.consents.models import Consent
from factories.base import make_candidate, make_grade
from fsp_contracts.assessment import TestGrade
from fsp_contracts.enums import ConsentType
from fsp_platform.db import session_scope

TG_UA = "TelegramBot (like TwitterBot)"
TW_UA = "Mozilla/5.0 (compatible; Twitterbot/1.0)"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36"


async def _cand(factory, *, public=True, consent=True, grade=TestGrade.middle, **kw):
    """Кандидат с заданными условиями публикации. Возвращает `(pseudo_id, user_id)`."""
    async with session_scope(factory) as s:
        cand = await make_candidate(s, **kw)
        cand.visibility = {**cand.visibility, "public_profile": public}
        if consent:
            s.add(
                Consent(
                    user_id=cand.user_id,
                    type=ConsentType.profile_publication,
                    version="2025-09-01",
                    granted_at=datetime.now(UTC),
                )
            )
        if grade:
            await make_grade(s, cand.user_id, "backend", grade)
        await s.flush()
        return cand.pseudo_id, cand.user_id


async def test_badge_ok(api, factory):
    slug, _ = await _cand(factory)
    r = api.get(f"/public/badge/{slug}.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in r.text
    assert "Backend" in r.text and "Middle" in r.text


async def test_badge_hidden_cases_404(api, factory):
    cases = [
        await _cand(factory, public=False),
        await _cand(factory, consent=False),
        await _cand(factory, grade=None),
    ]
    for slug, _ in cases:
        assert api.get(f"/public/badge/{slug}.svg").status_code == 404
    assert api.get("/public/badge/nonexistent00.svg").status_code == 404


async def test_badge_escapes_text():
    from app.views.service import generate_badge_svg

    svg = generate_badge_svg('<script>alert(1)</script>"', "<b>senior</b>")
    assert "<script>" not in svg and "<b>" not in svg
    assert "&lt;" in svg and "&gt;" in svg


async def test_profile_ok_without_pii(api, factory):
    slug, user_id = await _cand(factory, city="Казань")
    r = api.get(f"/public/profiles/{slug}")
    assert r.status_code == 200
    body = r.json()
    assert body["pseudo_id"] == slug
    assert body["grades"][0]["profession"] == "backend"
    assert body["grades"][0]["grade"] == "middle"
    forbidden = {"user_id", "email", "full_name", "name", "phone", "telegram", "contacts"}
    assert not forbidden & set(body)
    assert str(user_id) not in r.text and user_id.hex not in r.text.replace(slug, "")
    assert "@" not in r.text


async def test_profile_hidden_cases_404(api, factory):
    for kw in ({"public": False}, {"consent": False}, {"grade": None}):
        slug, _ = await _cand(factory, **kw)
        assert api.get(f"/public/profiles/{slug}").status_code == 404
    assert api.get("/public/profiles/nonexistent00").status_code == 404


async def test_athlete_og_for_crawlers(api, factory):
    slug, _ = await _cand(factory)
    for ua in (TG_UA, TW_UA):
        r = api.get(f"/athlete/{slug}", headers={"user-agent": ua}, follow_redirects=False)
        assert r.status_code == 200
        assert 'property="og:title"' in r.text
        assert f"/public/badge/{slug}.svg" in r.text
        assert 'property="og:image"' in r.text


async def test_athlete_redirects_browser(api, factory):
    slug, _ = await _cand(factory)
    r = api.get(f"/athlete/{slug}", headers={"user-agent": BROWSER_UA}, follow_redirects=False)
    assert r.status_code in (302, 307)
    loc = r.headers["location"]
    assert loc.endswith(f"/athlete/{slug}")
    assert "/public/" not in loc and loc != f"/athlete/{slug}"  # не зацикливается на себя


async def test_athlete_hidden_not_leaked_to_crawler(api, factory):
    slug, _ = await _cand(factory, public=False)
    r = api.get(f"/athlete/{slug}", headers={"user-agent": TG_UA}, follow_redirects=False)
    assert r.status_code == 404
    assert "og:title" not in r.text


async def test_athlete_og_escapes_pseudonym(api, factory):
    slug, _ = await _cand(factory, pseudonym='"><script>x</script>')
    r = api.get(f"/athlete/{slug}", headers={"user-agent": TG_UA}, follow_redirects=False)
    assert r.status_code == 200
    assert "<script>x</script>" not in r.text
