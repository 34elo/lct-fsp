import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import fakeredis
import pytest
from app.candidates import service
from app.candidates.models import Candidate
from app.config import Settings
from app.identity.models import utcnow
from app.main import build_app
from fastapi.testclient import TestClient
from fsp_platform.ratelimit import RateLimiter

CORE = Path(__file__).resolve().parents[1]
PWD = "correct-horse-battery"


@pytest.fixture
def c(tmp_path):
    db = tmp_path / "c.db"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url=sqlite+aiosqlite:///{db}", "upgrade", "head"],
        cwd=CORE,
        check=True,
        capture_output=True,
    )
    app = build_app(Settings(database_url=f"sqlite+aiosqlite:///{db}", ui_bus_enabled=False))
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        client.app_ = app
        yield client


def _user(c, email, role="candidate", consent=True):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": role})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if consent:
        body = {"consents": [{"type": "pd_processing", "granted": True}]}
        assert c.put("/me/consents", json=body, headers=h).status_code == 200
    return h


def test_pseudo_id_hmac():
    uid = uuid.uuid4()
    a = service.make_pseudo_id("s1", uid)
    assert len(a) == 12 and a != uid.hex[:12]
    assert a == service.make_pseudo_id("s1", uid)
    assert a != service.make_pseudo_id("s2", uid)
    assert a != service.make_pseudo_id("s1", uuid.uuid4())


def test_profile_lazy_create_stable(c):
    h = _user(c, "a@x.io")
    p1 = c.get("/candidates/me/profile", headers=h).json()
    p2 = c.get("/candidates/me/profile", headers=h).json()
    assert p1["pseudonym"] == p2["pseudonym"] and p1["pseudonym"].startswith("Candidate #")
    assert p1["search_status"] == "open" and p1["preferences"]["formats"] == []
    assert p1["visibility"] == {
        "companies": False,
        "education": False,
        "repos": False,
        "public_profile": False,
        "teams": True,
    }
    assert "pseudo_id" not in p1 and "user_id" not in p1


def test_roles_and_auth(c):
    assert c.get("/candidates/me/profile").status_code == 401
    e = _user(c, "e@x.io", role="employer")
    assert c.get("/candidates/me/profile", headers=e).status_code == 403


def test_preferences_patch_and_active_window(c):
    h = _user(c, "a@x.io")
    r = c.patch(
        "/candidates/me/preferences",
        json={
            "salary_min": 200000,
            "formats": ["remote", "hybrid", "remote"],
            "employment_types": ["full"],
            "city": "Казань",
            "relocation": True,
            "search_status": "active",
        },
        headers=h,
    )
    assert r.status_code == 200
    j = r.json()
    assert j["search_status"] == "active" and j["active_until"]
    assert j["preferences"] == {
        "salary_min": 200000,
        "formats": ["hybrid", "remote"],
        "employment_types": ["full"],
        "city": "Казань",
        "relocation": True,
    }
    # частичное обновление не трогает остальное; null очищает
    j = c.patch("/candidates/me/preferences", json={"salary_min": None}, headers=h).json()
    assert j["preferences"]["salary_min"] is None and j["preferences"]["city"] == "Казань"
    assert j["search_status"] == "active"
    j = c.patch("/candidates/me/preferences", json={"search_status": "dnd"}, headers=h).json()
    assert j["search_status"] == "dnd" and j["active_until"] is None
    bad = c.patch("/candidates/me/preferences", json={"formats": ["moon"]}, headers=h)
    assert bad.status_code == 422
    assert (
        c.patch("/candidates/me/preferences", json={"salary_min": -1}, headers=h).status_code == 422
    )


def test_active_expires_to_open():
    cand = Candidate(search_status="active", active_until=utcnow() - timedelta(seconds=1))
    assert service.effective_status(cand) == "open"
    cand.active_until = utcnow() + timedelta(days=1)
    assert service.effective_status(cand) == "active"


def test_visibility_and_public_consent(c):
    h = _user(c, "a@x.io")
    j = c.patch("/candidates/me/visibility", json={"companies": True}, headers=h).json()
    assert j["visibility"]["companies"] is True and j["visibility"]["teams"] is True
    r = c.patch("/candidates/me/visibility", json={"public_profile": True}, headers=h)
    assert r.status_code == 403 and r.json()["code"] == "consent_required"
    c.put(
        "/me/consents",
        json={"consents": [{"type": "public_profile", "granted": True}]},
        headers=h,
    )
    j = c.patch("/candidates/me/visibility", json={"public_profile": True}, headers=h).json()
    assert j["visibility"]["public_profile"] is True and j["visibility"]["companies"] is True


def test_stoplist_idempotent_and_isolated(c):
    h1, h2 = _user(c, "a@x.io"), _user(c, "b@x.io")
    ids = [str(uuid.uuid4()) for _ in range(2)]
    for _ in range(2):
        r = c.put("/candidates/me/stoplist", json={"company_ids": ids + ids[:1]}, headers=h1)
        assert r.status_code == 200 and sorted(r.json()["company_ids"]) == sorted(ids)
    assert (
        c.put("/candidates/me/stoplist", json={"company_ids": ["x"]}, headers=h1).status_code == 422
    )
    c.get("/candidates/me/profile", headers=h2)
    # чужой стоп-лист не виден и не меняется
    assert c.put("/candidates/me/stoplist", json={"company_ids": []}, headers=h2).json() == {
        "company_ids": []
    }
    assert sorted(
        c.put("/candidates/me/stoplist", json={"company_ids": ids}, headers=h1).json()[
            "company_ids"
        ]
    ) == sorted(ids)


def test_writes_need_pd_consent(c):
    h = _user(c, "a@x.io", consent=False)
    assert c.get("/candidates/me/profile", headers=h).status_code == 200
    r = c.patch("/candidates/me/preferences", json={"city": "X"}, headers=h)
    assert r.status_code == 403 and r.json()["code"] == "consent_required"


def test_distinct_pseudonyms_and_pseudo_ids(c):
    hs = [_user(c, f"u{i}@x.io") for i in range(5)]
    names = {c.get("/candidates/me/profile", headers=h).json()["pseudonym"] for h in hs}
    assert len(names) == 5
