import sqlite3
import subprocess
import sys
from pathlib import Path

import fakeredis
import pytest
from app.config import Settings
from app.main import build_app
from fastapi.testclient import TestClient
from fsp_platform.ratelimit import RateLimiter

CORE = Path(__file__).resolve().parents[1]
PWD = "correct-horse-battery"
INN = "7707083893"


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
        client.db = db
        yield client


def _user(c, email, role="employer"):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": role})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _admin(c):
    h = _user(c, "root@x.io")
    with sqlite3.connect(c.db) as con:
        con.execute("update users set role='fsp_admin' where email='root@x.io'")
    return h


def _company(c, h, name="Acme Labs"):
    r = c.post("/companies", json={"name": name, "inn": INN}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_register_company_pending_and_me(c):
    h = _user(c, "e@x.io")
    assert c.get("/companies/me", headers=h).status_code == 404
    co = _company(c, h)
    assert co["status"] == "pending" and co["my_role"] == "admin"
    assert c.get("/companies/me", headers=h).json()["id"] == co["id"]
    me = c.get("/me", headers=h).json()
    assert me["company"] == {
        "id": co["id"],
        "name": "Acme Labs",
        "status": "pending",
        "role": "admin",
    }
    assert c.post("/companies", json={"name": "Other"}, headers=h).status_code == 409


def test_roles_and_validation(c):
    cand = _user(c, "k@x.io", role="candidate")
    assert c.post("/companies", json={"name": "Acme"}, headers=cand).status_code == 403
    assert c.post("/companies", json={"name": "Acme"}).status_code == 401
    h = _user(c, "e@x.io")
    assert c.post("/companies", json={"name": "A"}, headers=h).status_code == 422
    assert c.post("/companies", json={"name": "Acme", "inn": "12"}, headers=h).status_code == 422
    assert (
        c.post("/companies", json={"name": "Acme", "status": "verified"}, headers=h).status_code
        == 422
    )
    assert c.get("/me", headers=cand).json()["company"] is None


def test_patch_admin_only_and_status_untouchable(c):
    adm = _user(c, "a@x.io")
    _company(c, adm)
    r = c.patch(
        "/companies/me", json={"site": "https://acme.test", "description": "d"}, headers=adm
    )
    assert r.status_code == 200 and r.json()["site"] == "https://acme.test"
    assert c.patch("/companies/me", json={"status": "verified"}, headers=adm).status_code == 422
    assert (
        c.patch("/companies/me", json={"responsibility_score": 5}, headers=adm).status_code == 422
    )
    mem = _user(c, "m@x.io")
    assert c.post("/companies/me/members", json={"email": "M@x.io"}, headers=adm).status_code == 201
    assert c.get("/companies/me", headers=mem).json()["my_role"] == "member"
    assert c.patch("/companies/me", json={"site": "x"}, headers=mem).status_code == 403
    assert c.post("/companies/me/members", json={"email": "a@x.io"}, headers=mem).status_code == 403


def test_members_invite_rules(c):
    adm = _user(c, "a@x.io")
    _company(c, adm)
    body = {"email": "m@x.io"}
    assert c.post("/companies/me/members", json=body, headers=adm).status_code == 404  # нет юзера
    _user(c, "m@x.io")
    assert c.post("/companies/me/members", json=body, headers=adm).status_code == 201
    assert (
        c.post("/companies/me/members", json=body, headers=adm).status_code == 201
    )  # идемпотентно
    _user(c, "k@x.io", role="candidate")
    assert c.post("/companies/me/members", json={"email": "k@x.io"}, headers=adm).status_code == 404
    other = _user(c, "o@x.io")
    _company(c, other, "Other Co")
    assert c.post("/companies/me/members", json={"email": "o@x.io"}, headers=adm).status_code == 409
    # чужая компания не видна: у приглашённого своя, у постороннего без компании — 404
    stranger = _user(c, "s@x.io")
    assert c.get("/companies/me", headers=stranger).status_code == 404
    assert c.post("/companies/me/members", json=body, headers=stranger).status_code == 404


def test_moderation_flow(c):
    h = _user(c, "e@x.io")
    co = _company(c, h)
    adm = _admin(c)
    assert c.get("/admin/companies", headers=h).status_code == 403
    assert c.post(f"/admin/companies/{co['id']}/verify", headers=h).status_code == 403
    assert [x["id"] for x in c.get("/admin/companies?status=pending", headers=adm).json()] == [
        co["id"]
    ]
    assert c.get("/admin/companies?status=bogus", headers=adm).status_code == 422
    v = c.post(f"/admin/companies/{co['id']}/verify", headers=adm)
    assert v.status_code == 200 and v.json()["status"] == "verified"
    assert c.post(f"/admin/companies/{co['id']}/verify", headers=adm).json()["status"] == "verified"
    assert c.get("/admin/companies?status=pending", headers=adm).json() == []
    assert c.get("/companies/me", headers=h).json()["status"] == "verified"
    r = c.post(f"/admin/companies/{co['id']}/reject", headers=adm)
    assert r.json()["status"] == "rejected"
    assert c.post(f"/admin/companies/{co['id']}/verify", headers=adm).json()["status"] == "verified"
    missing = "00000000-0000-0000-0000-000000000000"
    assert c.post(f"/admin/companies/{missing}/verify", headers=adm).status_code == 404


def test_blocked_cannot_be_moderated(c):
    h = _user(c, "e@x.io")
    co = _company(c, h)
    adm = _admin(c)
    with sqlite3.connect(c.db) as con:
        con.execute("update companies set status='blocked'")
    for act in ("verify", "reject"):
        r = c.post(f"/admin/companies/{co['id']}/{act}", headers=adm)
        assert r.status_code == 409 and r.json()["code"] == "invalid_status"
