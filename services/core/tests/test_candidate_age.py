"""Кандидаты 15–17 лет: возрастная группа и согласие родителя."""

import uuid

from app.candidates import service as cands
from app.candidates.models import Candidate
from sqlalchemy import select
from test_candidate_profile_form import _patch, _q, _user, c  # noqa: F401


def _row(c):  # noqa: F811
    async def go(s):
        return (await s.scalars(select(Candidate))).one()

    return _q(c, go)


def test_default_is_publishable(c):  # noqa: F811
    h = _user(c, "a@x.io")
    p = c.get("/candidates/me/profile", headers=h).json()
    assert p["age_group"] is None and p["parent_consent"] is False and p["publishable"] is True


def test_minor_needs_parent_consent(c):  # noqa: F811
    h = _user(c, "m@x.io")
    p = _patch(c, h, {"age_group": "minor"}).json()
    assert p["age_group"] == "minor" and p["publishable"] is False
    p = _patch(c, h, {"parent_consent": True}).json()
    assert p["parent_consent"] is True and p["publishable"] is True
    assert _row(c).parent_consent_at is not None
    p = _patch(c, h, {"parent_consent": False}).json()  # отзыв
    assert p["publishable"] is False and _row(c).parent_consent_at is None


def test_switch_to_adult_clears_consent(c):  # noqa: F811
    h = _user(c, "s@x.io")
    _patch(c, h, {"age_group": "minor", "parent_consent": True})
    p = _patch(c, h, {"age_group": "adult"}).json()
    assert p["parent_consent"] is False and p["publishable"] is True


def test_consent_requires_minor(c):  # noqa: F811
    h = _user(c, "r@x.io")
    assert _patch(c, h, {"parent_consent": True}).status_code == 422
    assert _patch(c, h, {"age_group": "adult", "parent_consent": True}).status_code == 422
    assert _patch(c, h, {"age_group": "teen"}).status_code == 422


def test_search_pool_hides_minor_without_consent(c):  # noqa: F811
    h = _user(c, "p@x.io")
    _patch(c, h, {"age_group": "minor"})

    async def prep(s):
        row = (await s.scalars(select(Candidate))).one()
        row.primary_role = "backend"
        return row.user_id

    uid = _q(c, prep)

    async def pool(s):
        return await cands.search_pool(s, company_id=uuid.uuid4())

    async def elig(s):
        return await cands.eligible(s, [uid], salary_cap=10**9, formats=[], company_id=uuid.uuid4())

    assert _q(c, pool) == [] and _q(c, elig) == []
    _patch(c, h, {"parent_consent": True})
    assert len(_q(c, pool)) == 1 and len(_q(c, elig)) == 1
