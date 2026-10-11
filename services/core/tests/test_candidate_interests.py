# ruff: noqa: F811
"""Встречный сигнал: кандидат показал интерес к компании."""

import uuid

import pytest
from test_offers import (  # noqa: F401  (фикстуры и помощники)
    PWD,
    _candidate,
    _db,
    c,
    template_db,
)

INN = "500100732259"


def _employer(c, email, name="Test Company"):
    """Создать работодателя и вернуть заголовки авторизации."""
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": "employer"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    co = c.post("/companies", json={"name": name, "inn": INN}, headers=h).json()
    _db(c, "update companies set status='verified' where id=?", co["id"].replace("-", ""))
    return h, co["id"]


def _mark_interest(c, ch, company_id):
    """POST /companies/{company_id}/interest"""
    return c.post(f"/companies/{company_id}/interest", headers=ch)


def _remove_interest(c, ch, company_id):
    """DELETE /companies/{company_id}/interest"""
    return c.delete(f"/companies/{company_id}/interest", headers=ch)


@pytest.fixture
def world(c):
    ch, _, uid = _candidate(c, "c@x.ru", 1)
    _, company_id = _employer(c, "e@x.ru", "Acme Labs")
    return c, ch, uid, company_id


def test_mark_candidate_interest(world):
    """Кандидат показывает интерес к компании."""
    c, ch, uid, company_id = world
    r = _mark_interest(c, ch, company_id)
    assert r.status_code == 200, r.text
    o = r.json()
    assert "created_at" in o
    # Повтор — идемпотентен
    r2 = _mark_interest(c, ch, company_id)
    assert r2.status_code == 200
    assert r2.json()["created_at"] == o["created_at"]


def test_remove_candidate_interest(world):
    """Кандидат снимает интерес к компании."""
    c, ch, uid, company_id = world
    _mark_interest(c, ch, company_id)
    r = _remove_interest(c, ch, company_id)
    assert r.status_code == 200
    assert r.json()["removed"] is True
    # Повтор — ничего не меняет
    r2 = _remove_interest(c, ch, company_id)
    assert r2.status_code == 200
    assert r2.json()["removed"] is False


def test_interest_404_on_unknown_company(world):
    """Несуществующая компания -> 404."""
    c, ch, uid, _ = world
    ghost = str(uuid.uuid4())
    r = _mark_interest(c, ch, ghost)
    assert (r.status_code, r.json()["code"]) == (404, "company_not_found")


def test_candidate_only_can_mark_interest(world):
    """Только кандидат может отмечать интерес."""
    c, ch, uid, company_id = world
    assert c.post(f"/companies/{company_id}/interest").status_code == 401
    eh, _ = _employer(c, "e2@x.ru", "Beta")
    assert c.post(f"/companies/{company_id}/interest", headers=eh).status_code == 403
    assert c.delete(f"/companies/{company_id}/interest", headers=eh).status_code == 403


def test_interest_unverified_company_404(world):
    """Неподтверждённая компания для кандидата не существует."""
    c, ch, uid, company_id = world
    _db(c, "update companies set status='pending' where id=?", company_id.replace("-", ""))
    r = _mark_interest(c, ch, company_id)
    assert (r.status_code, r.json()["code"]) == (404, "company_not_found")


def test_multiple_interests(world):
    """Кандидат может показать интерес к разным компаниям."""
    c, ch, uid, company_id = world
    _, company_id2 = _employer(c, "e2@x.ru", "Beta")
    r1 = _mark_interest(c, ch, company_id)
    r2 = _mark_interest(c, ch, company_id2)
    assert r1.status_code == 200 and r2.status_code == 200
    # Разные компании -> разные интересы
    assert r1.json()["created_at"] and r2.json()["created_at"]
