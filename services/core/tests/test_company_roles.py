"""Роли компании (E39-24): владелец и HR, приглашение по ссылке, личный профиль, аватар."""

import sqlite3
import uuid

import fakeredis
import pytest
from app.config import Settings
from app.main import build_app
from core_helpers import upgrade_head
from fastapi.testclient import TestClient
from fsp_platform.ratelimit import RateLimiter

PWD = "correct-horse-battery"
INN = "7707083893"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class FakeStorage:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    async def ensure_bucket(self):
        return None

    async def put(self, key, data, content_type="application/octet-stream"):
        self.files[key] = data

    async def get(self, key):
        return self.files[key]

    async def delete(self, key):
        self.files.pop(key, None)


class FakeMailer:
    def __init__(self):
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to, subject, body):
        self.sent.append((to, subject, body))


@pytest.fixture(scope="module")
def template_db(tmp_path_factory):
    db = tmp_path_factory.mktemp("roles") / "r.db"
    upgrade_head(f"sqlite+aiosqlite:///{db}")
    with sqlite3.connect(db) as con:
        con.execute(
            "insert into skills (id, slug, name, kind, status, source, support_candidates,"
            " support_vacancies, testable) values (?,?,?,?,?,?,0,0,0)",
            (uuid.uuid4().hex, "python", "python", "tech", "active", "seed"),
        )
    return db


@pytest.fixture
def c(tmp_path, template_db):
    import shutil

    db = tmp_path / "r.db"
    shutil.copy(template_db, db)
    app = build_app(Settings(database_url=f"sqlite+aiosqlite:///{db}", ui_bus_enabled=False))
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        app.state.storage = FakeStorage()
        app.state.mailer = FakeMailer()
        client.db = db
        client.storage = app.state.storage
        client.mailer = app.state.mailer
        yield client


def _db(c, sql, *args):
    with sqlite3.connect(c.db) as con:
        return con.execute(sql, args).fetchall()


def _user(c, email, role="employer"):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": role})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _owner(c, email="owner@x.io", name="Acme Labs", verified=False):
    h = _user(c, email)
    co = c.post("/companies", json={"name": name, "inn": INN}, headers=h)
    assert co.status_code == 201, co.text
    if verified:
        company_id = co.json()["id"].replace("-", "")
        _db(c, "update companies set status='verified' where id=?", company_id)
    return h


def _invite(c, owner, email):
    r = c.post("/companies/me/invites", json={"email": email}, headers=owner)
    assert r.status_code == 201, r.text
    return r.json()["url"].rsplit("/", 1)[-1]


def _hr(c, owner, email="hr@x.io"):
    token = _invite(c, owner, email)
    h = _user(c, email)
    r = c.post(f"/company-invites/{token}/accept", headers=h)
    assert r.status_code == 200, r.text
    return h


def test_invite_flow_hr_sees_but_cannot_edit(c):
    owner = _owner(c)
    r = c.post("/companies/me/invites", json={"email": "HR@x.io"}, headers=owner)
    assert r.status_code == 201
    inv = r.json()
    assert inv["email"] == "hr@x.io" and "/invite/company/" in inv["url"]
    to, subject, body = c.mailer.sent[-1]
    assert to == "hr@x.io" and "Acme Labs" in subject and inv["url"] in body
    token = inv["url"].rsplit("/", 1)[-1]

    preview = c.get(f"/company-invites/{token}")  # без авторизации
    assert preview.status_code == 200
    assert preview.json()["company_name"] == "Acme Labs"
    assert preview.json()["email_masked"] == "h***@x.io"

    hr = _user(c, "hr@x.io")
    acc = c.post(f"/company-invites/{token}/accept", headers=hr)
    assert acc.status_code == 200 and acc.json()["my_role"] == "member"
    assert c.get("/me", headers=hr).json()["company"]["role"] == "member"
    # ссылка одноразовая
    assert c.get(f"/company-invites/{token}").status_code == 404
    assert c.post(f"/company-invites/{token}/accept", headers=hr).status_code == 404

    # HR видит компанию и команду, но не правит и не управляет командой
    assert c.get("/companies/me", headers=hr).status_code == 200
    assert c.patch("/companies/me", json={"name": "Hacked"}, headers=hr).status_code == 403
    assert c.post("/companies/me/invites", json={"email": "z@x.io"}, headers=hr).status_code == 403
    team = c.get("/companies/me/members", headers=hr).json()
    assert team["can_manage"] is False and team["invites"] == []
    assert [m["role"] for m in team["members"]] == ["admin", "member"]
    assert [m["is_me"] for m in team["members"]] == [False, True]
    owner_id = team["members"][0]["user_id"]
    assert c.delete(f"/companies/me/members/{owner_id}", headers=hr).status_code == 403

    # владелец правит, описание в Markdown хранится как есть
    md = "## О нас\n\n- **Python**\n- | a | b |"
    r = c.patch("/companies/me", json={"description": md}, headers=owner)
    assert r.status_code == 200 and r.json()["description"] == md
    owner_team = c.get("/companies/me/members", headers=owner).json()
    assert owner_team["can_manage"] is True


def test_invite_errors(c):
    owner = _owner(c)
    assert c.post("/company-invites/nope/accept", headers=_user(c, "a@x.io")).status_code == 404
    assert c.get("/company-invites/nope").status_code == 404
    token = _invite(c, owner, "hr@x.io")
    assert c.post(f"/company-invites/{token}/accept").status_code == 401
    cand = _user(c, "hr2@x.io", role="candidate")
    assert c.post(f"/company-invites/{token}/accept", headers=cand).status_code == 403
    other = _user(c, "other@x.io")
    r = c.post(f"/company-invites/{token}/accept", headers=other)
    assert r.status_code == 403 and r.json()["code"] == "invite_email_mismatch"
    # повтор приглашения на тот же email отзывает старую ссылку
    token2 = _invite(c, owner, "hr@x.io")
    assert c.get(f"/company-invites/{token}").status_code == 404
    assert c.get(f"/company-invites/{token2}").status_code == 200
    assert len(c.get("/companies/me/members", headers=owner).json()["invites"]) == 1
    # уже в другой компании
    hr = _owner(c, "hr@x.io", name="Other Co")
    r = c.post(f"/company-invites/{token2}/accept", headers=hr)
    assert r.status_code == 409 and r.json()["code"] == "already_member"
    # участника приглашать нельзя; невалидный email — 422
    r = c.post("/companies/me/invites", json={"email": "owner@x.io"}, headers=owner)
    assert r.status_code == 409
    assert c.post("/companies/me/invites", json={"email": "bad"}, headers=owner).status_code == 422


def test_foreign_invites_and_members_404(c):
    a = _owner(c, "a@x.io", name="Alpha")
    b = _owner(c, "b@x.io", name="Beta")
    _hr(c, a, "hr@x.io")
    _invite(c, a, "next@x.io")
    team_a = c.get("/companies/me/members", headers=a).json()
    invite_id = team_a["invites"][0]["id"]
    hr_id = team_a["members"][1]["user_id"]
    me_id = team_a["members"][0]["user_id"]
    assert c.delete(f"/companies/me/invites/{invite_id}", headers=b).status_code == 404
    assert c.delete(f"/companies/me/members/{hr_id}", headers=b).status_code == 404
    assert c.delete(f"/companies/me/invites/{uuid.uuid4()}", headers=a).status_code == 404
    # владельца убрать нельзя
    r = c.delete(f"/companies/me/members/{me_id}", headers=a)
    assert r.status_code == 409 and r.json()["code"] == "owner_cannot_be_removed"
    # свои: отзыв (повтор — no-op) и удаление HR
    assert c.delete(f"/companies/me/invites/{invite_id}", headers=a).status_code == 204
    assert c.delete(f"/companies/me/invites/{invite_id}", headers=a).status_code == 204
    assert c.get("/companies/me/members", headers=a).json()["invites"] == []
    assert c.delete(f"/companies/me/members/{hr_id}", headers=a).status_code == 204
    assert len(c.get("/companies/me/members", headers=a).json()["members"]) == 1
    # без компании — 404
    assert c.get("/companies/me/members", headers=_user(c, "x@x.io")).status_code == 404


def test_personal_profile(c):
    h = _owner(c)
    assert c.get("/me/profile", headers=h).json() == {
        "full_name": None, "position": None, "about": None, "avatar_url": None,
    }  # fmt: skip
    body = {"full_name": " Анна Смирнова ", "position": "HR-партнёр", "about": "**Найм** в ИТ"}
    r = c.patch("/me/profile", json=body, headers=h)
    assert r.status_code == 200
    assert r.json()["full_name"] == "Анна Смирнова" and r.json()["position"] == "HR-партнёр"
    r = c.patch("/me/profile", json={"position": ""}, headers=h)
    assert r.json()["position"] is None and r.json()["full_name"] == "Анна Смирнова"
    assert c.patch("/me/profile", json={"full_name": "x" * 121}, headers=h).status_code == 422
    assert c.patch("/me/profile", json={"email": "a@b.c"}, headers=h).status_code == 422
    cand = _user(c, "k@x.io", role="candidate")
    assert c.get("/me/profile", headers=cand).status_code == 403
    assert c.patch("/me/profile", json={}, headers=cand).status_code == 403
    assert c.get("/me/profile").status_code == 401


def test_avatar_signature_and_public_read(c):
    h = _owner(c)
    files = {"file": ("a.png", PNG, "image/png")}
    r = c.put("/me/avatar", files=files, headers=h)
    assert r.status_code == 200, r.text
    url = r.json()["avatar_url"]
    assert url.startswith("/users/") and "?v=" in url
    img = c.get(url)  # без авторизации: <img> не несёт токен
    assert img.status_code == 200 and img.content == PNG
    assert img.headers["content-type"] == "image/png"
    # подпись проверяется по содержимому, а не по имени файла
    fake = {"file": ("a.png", b"<svg onload=alert(1)>", "image/png")}
    r = c.put("/me/avatar", files=fake, headers=h)
    assert r.status_code == 415 and r.json()["code"] == "unsupported_file_type"
    big = {"file": ("b.png", PNG + b"\x00" * (2 * 1024 * 1024), "image/png")}
    assert c.put("/me/avatar", files=big, headers=h).status_code == 413
    # замена удаляет старый файл
    jpg = b"\xff\xd8\xff\xe0" + b"\x01" * 32
    r = c.put("/me/avatar", files={"file": ("p.jpg", jpg, "image/jpeg")}, headers=h)
    assert r.json()["avatar_url"] != url and len(c.storage.files) == 1
    assert c.get(r.json()["avatar_url"]).headers["content-type"] == "image/jpeg"
    # удаление
    assert c.delete("/me/avatar", headers=h).json()["avatar_url"] is None
    assert c.storage.files == {}
    assert c.get(url.split("?")[0]).status_code == 404
    assert c.get(f"/users/{uuid.uuid4()}/avatar").status_code == 404
    cand = _user(c, "k@x.io", role="candidate")
    assert c.put("/me/avatar", files=files, headers=cand).status_code == 403


def _candidate(c):
    h = _user(c, "cand@x.io", role="candidate")
    body = {"consents": [{"type": "pd_processing", "granted": True},
                         {"type": "profile_publication", "granted": True}]}  # fmt: skip
    assert c.put("/me/consents", json=body, headers=h).status_code == 200
    assert c.get("/candidates/me/profile", headers=h).status_code == 200
    (uid,) = _db(c, "select user_id from candidates order by rowid desc limit 1")[0]
    _db(
        c,
        "update candidates set primary_role='backend', grade='middle', pseudo_id='pid0001'"
        " where user_id=?",
        uid,
    )
    _db(
        c,
        "insert into grades (candidate_id, profession, grade, theta, band_position,"
        " theta_by_type, integrity, needs_confirmation, low_confidence, source, confirmed_at,"
        " valid_until, next_change_at) values (?,?,?,0.5,0.5,'{}',1.0,0,0,'seed',"
        "'2026-01-01 00:00:00','2999-01-01 00:00:00','2026-01-01 00:00:00')",
        uid,
        "backend",
        "middle",
    )
    return h


def test_offer_signed_by_hr(c):
    owner = _owner(c, verified=True)
    c.patch("/companies/me", json={"description": "Мы **делаем** продукт"}, headers=owner)
    hr = _hr(c, owner)
    c.patch("/me/profile", json={"full_name": "Анна Смирнова", "position": "HR"}, headers=hr)
    c.put("/me/avatar", files={"file": ("a.png", PNG, "image/png")}, headers=hr)
    cand = _candidate(c)
    body = {
        "title": "Backend", "role": "backend", "grade_min": "middle", "grade_max": "senior",
        "formats": ["remote"], "employment_type": "full", "salary_from": 200000,
        "salary_to": 300000, "skills": [{"slug": "python"}],
    }  # fmt: skip
    vid = c.post("/vacancies", json=body, headers=hr).json()["id"]
    assert c.post(f"/vacancies/{vid}/publish", headers=hr).status_code == 200
    offer = {"vacancy_id": vid, "candidate_pseudo_id": "pid0001", "salary_from": 250000,
             "salary_to": 320000, "message": "Привет!"}  # fmt: skip
    r = c.post("/offers", json=offer, headers={**hr, "Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 201, r.text
    items = c.get("/candidates/me/offers", headers=cand).json()
    sender = items[0]["sender"]
    assert sender["full_name"] == "Анна Смирнова" and sender["position"] == "HR"
    assert sender["avatar_url"].startswith("/users/")
    assert "email" not in sender
    assert items[0]["company"]["description"] == "Мы **делаем** продукт"
    assert c.get(sender["avatar_url"]).status_code == 200
