"""Доступ HR без почты (E41-16): временный пароль, смена при первом входе, сброс, отзыв, журнал."""

import sqlite3
import uuid
from datetime import UTC, datetime, timedelta

import fakeredis
import pytest
from app.config import Settings
from app.main import build_app
from core_helpers import upgrade_head
from fastapi.testclient import TestClient
from fsp_platform.ratelimit import RateLimiter

PWD = "correct-horse-battery"
INN = "7707083893"
WEB = "https://career.example.ru"


@pytest.fixture(scope="module")
def template_db(tmp_path_factory):
    db = tmp_path_factory.mktemp("hr") / "h.db"
    upgrade_head(f"sqlite+aiosqlite:///{db}")
    return db


@pytest.fixture
def c(tmp_path, template_db):
    import shutil

    db = tmp_path / "h.db"
    shutil.copy(template_db, db)
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{db}", ui_bus_enabled=False, web_base_url=WEB + "/"
    )
    app = build_app(settings)
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        client.db = db
        yield client


def _db(c, sql, *args):
    with sqlite3.connect(c.db) as con:
        return con.execute(sql, args).fetchall()


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _user(c, email, role="employer"):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": role})
    assert r.status_code == 201, r.text
    return _h(r.json()["access_token"])


def _owner(c, email="owner@x.io", name="Acme Labs"):
    h = _user(c, email)
    assert c.post("/companies", json={"name": name, "inn": INN}, headers=h).status_code == 201
    return h


def _create_hr(c, owner, email="hr@x.io", name="Анна Смирнова"):
    r = c.post("/companies/me/hr", json={"email": email, "full_name": name}, headers=owner)
    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == "no-store"
    return r.json()


def _login(c, email, password):
    return c.post("/auth/login", json={"email": email, "password": password})


def test_temp_password_works_and_requires_change_first(c):
    owner = _owner(c)
    card = _create_hr(c, owner, "HR@x.io")
    assert card["email"] == "hr@x.io" and card["full_name"] == "Анна Смирнова"
    assert card["login_url"] == f"{WEB}/login"  # адрес из WEB_BASE_URL, не localhost
    temp = card["temp_password"]
    assert len(temp) == 14 and temp.count("-") == 2

    # в БД только argon2-хеш, пароль в открытом виде не хранится
    stored = _db(c, "select password_hash, must_change_password from users where email='hr@x.io'")
    assert stored[0][0].startswith("$argon2") and temp not in stored[0][0] and stored[0][1] == 1
    assert not any(temp in str(row) for row in _db(c, "select * from company_access_log"))

    r = _login(c, "hr@x.io", temp)
    assert r.status_code == 200 and r.json()["user"]["must_change_password"] is True
    hr = _h(r.json()["access_token"])
    me = c.get("/me", headers=hr).json()
    assert me["must_change_password"] is True and me["company"]["role"] == "member"
    # до смены — никаких других действий
    r = c.get("/companies/me", headers=hr)
    assert r.status_code == 403 and r.json()["code"] == "password_change_required"
    assert c.get("/companies/me/members", headers=hr).status_code == 403
    assert c.patch("/me/profile", json={"position": "HR"}, headers=hr).status_code == 403
    # новый не может совпадать с временным
    r = c.post("/auth/password/initial", json={"new_password": temp}, headers=hr)
    assert r.status_code == 422 and r.json()["code"] == "same_password"
    r = c.post("/auth/password/initial", json={"new_password": "my-own-secret"}, headers=hr)
    assert r.status_code == 204
    assert c.get("/me", headers=hr).json()["must_change_password"] is False
    assert c.get("/companies/me", headers=hr).status_code == 200
    # повтор не нужен; временный больше не работает, свой — работает
    r = c.post("/auth/password/initial", json={"new_password": "another-secret"}, headers=hr)
    assert r.status_code == 409
    assert _login(c, "hr@x.io", temp).status_code == 401
    assert _login(c, "hr@x.io", "my-own-secret").status_code == 200


def test_temp_password_expires_after_72h(c):
    owner = _owner(c)
    card = _create_hr(c, owner)
    left = datetime.fromisoformat(card["expires_at"]) - datetime.now(UTC)
    assert timedelta(hours=71, minutes=59) < left <= timedelta(hours=72)
    _db(c, "update users set temp_password_expires_at='2020-01-01 00:00:00' where email='hr@x.io'")
    r = _login(c, "hr@x.io", card["temp_password"])
    assert r.status_code == 401 and r.json()["code"] == "temp_password_expired"


def test_reset_password_invalidates_old_and_sessions(c):
    owner = _owner(c)
    card = _create_hr(c, owner)
    first = _login(c, "hr@x.io", card["temp_password"])
    assert first.status_code == 200
    hr = _h(first.json()["access_token"])
    assert (
        c.post(
            "/auth/password/initial", json={"new_password": "hr-secret-1"}, headers=hr
        ).status_code
        == 204
    )
    refresh_cookie = first.cookies.get("rt")
    assert refresh_cookie

    r = c.post(f"/companies/me/members/{card['user_id']}/password", headers=owner)
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["temp_password"] != card["temp_password"] and new["login_url"] == f"{WEB}/login"
    # старый временный и свой пароль больше не работают, сессии закрыты
    assert _login(c, "hr@x.io", card["temp_password"]).status_code == 401
    assert _login(c, "hr@x.io", "hr-secret-1").status_code == 401
    c.cookies.clear()
    c.cookies.set("rt", refresh_cookie)
    assert c.post("/auth/refresh").status_code == 401
    c.cookies.clear()
    r = _login(c, "hr@x.io", new["temp_password"])
    assert r.status_code == 200 and r.json()["user"]["must_change_password"] is True


def test_revoke_blocks_login_and_kills_sessions(c):
    owner = _owner(c)
    card = _create_hr(c, owner)
    r = _login(c, "hr@x.io", card["temp_password"])
    hr = _h(r.json()["access_token"])
    rt = r.cookies.get("rt")
    assert (
        c.post(
            "/auth/password/initial", json={"new_password": "hr-secret-1"}, headers=hr
        ).status_code
        == 204
    )

    assert c.delete(f"/companies/me/members/{card['user_id']}", headers=owner).status_code == 204
    assert _login(c, "hr@x.io", "hr-secret-1").status_code == 401
    assert c.get("/me", headers=hr).status_code == 401  # access-токен гаснет сразу
    c.cookies.clear()
    c.cookies.set("rt", rt)
    assert c.post("/auth/refresh").status_code == 401
    c.cookies.clear()
    team = c.get("/companies/me/members", headers=owner).json()
    assert [m["role"] for m in team["members"]] == ["admin"]

    # та же компания может вернуть доступ: новый временный пароль
    again = _create_hr(c, owner)
    assert again["user_id"] == card["user_id"]
    assert _login(c, "hr@x.io", again["temp_password"]).status_code == 200

    log = c.get("/companies/me/access-log", headers=owner).json()
    assert [e["action"] for e in log] == ["created", "revoked", "created"]
    assert log[0]["target_email"] == "hr@x.io" and log[0]["target_name"] == "Анна Смирнова"
    assert log[0]["actor_name"] == "owner@x.io"


def test_errors_and_foreign_company_404(c):
    a = _owner(c, "a@x.io", "Alpha")
    b = _owner(c, "b@x.io", "Beta")
    _user(c, "cand@x.io", role="candidate")
    r = c.post("/companies/me/hr", json={"email": "cand@x.io", "full_name": "Иван"}, headers=a)
    assert r.status_code == 409 and r.json()["code"] == "email_is_candidate"
    r = c.post("/companies/me/hr", json={"email": "b@x.io", "full_name": "Иван"}, headers=a)
    assert r.status_code == 409 and r.json()["code"] == "email_taken"
    card = _create_hr(c, a)
    r = c.post("/companies/me/hr", json={"email": "hr@x.io", "full_name": "Иван"}, headers=a)
    assert r.status_code == 409 and r.json()["code"] == "already_member"
    # отозванный аккаунт другой компании Beta не забирает
    assert c.delete(f"/companies/me/members/{card['user_id']}", headers=a).status_code == 204
    r = c.post("/companies/me/hr", json={"email": "hr@x.io", "full_name": "Иван"}, headers=b)
    assert r.status_code == 409 and r.json()["code"] == "email_taken"
    bad = c.post("/companies/me/hr", json={"email": "bad", "full_name": "Иван"}, headers=a)
    assert bad.status_code == 422

    card = _create_hr(c, a, "hr2@x.io")
    uid = card["user_id"]
    # чужая компания — 404
    assert c.post(f"/companies/me/members/{uid}/password", headers=b).status_code == 404
    assert c.delete(f"/companies/me/members/{uid}", headers=b).status_code == 404
    assert c.post(f"/companies/me/members/{uuid.uuid4()}/password", headers=a).status_code == 404
    assert c.get("/companies/me/access-log", headers=b).json() == []
    # владельцу и самостоятельно зарегистрированному HR пароль не сбрасывают
    owner_id = c.get("/me", headers=a).json()["id"]
    r = c.post(f"/companies/me/members/{owner_id}/password", headers=a)
    assert r.status_code == 409 and r.json()["code"] == "not_managed"
    # HR не управляет доступом
    hr = _h(_login(c, "hr2@x.io", card["temp_password"]).json()["access_token"])
    assert (
        c.post(
            "/auth/password/initial", json={"new_password": "hr-secret-2"}, headers=hr
        ).status_code
        == 204
    )
    r = c.post("/companies/me/hr", json={"email": "z@x.io", "full_name": "Зоя"}, headers=hr)
    assert r.status_code == 403
    assert c.get("/companies/me/access-log", headers=hr).status_code == 403
    team = c.get("/companies/me/members", headers=hr).json()
    assert all(m["managed"] is False for m in team["members"])
    owner_team = c.get("/companies/me/members", headers=a).json()
    assert [m["managed"] for m in owner_team["members"]] == [False, True]


def test_rate_limit(c):
    owner = _owner(c)
    for i in range(20):
        _create_hr(c, owner, f"hr{i}@x.io")
    r = c.post("/companies/me/hr", json={"email": "z@x.io", "full_name": "Зоя"}, headers=owner)
    assert r.status_code == 429


def test_e43_3_full_flow_temp_change_login_refresh(c):
    """E43-3: временный пароль → смена → вход новым 200, старым 401; refresh работает."""
    owner = _owner(c)
    temp = _create_hr(c, owner, "hr3@x.io")["temp_password"]
    r = _login(c, "hr3@x.io", temp)
    assert r.status_code == 200
    hr = _h(r.json()["access_token"])
    rt = r.cookies.get("rt")
    assert (
        c.post(
            "/auth/password/initial", json={"new_password": "brand-new-pass"}, headers=hr
        ).status_code
        == 204
    )
    # та же сессия: флаг снят, refresh отдаёт пользователя без must_change_password
    assert c.get("/me", headers=hr).json()["must_change_password"] is False
    c.cookies.clear()
    c.cookies.set("rt", rt)
    r = c.post("/auth/refresh")
    assert r.status_code == 200 and r.json()["user"]["must_change_password"] is False
    # вход новым паролем (в любом регистре email) — 200 и сразу без флага; временным — 401
    r = _login(c, "HR3@x.io", "brand-new-pass")
    assert r.status_code == 200 and r.json()["user"]["must_change_password"] is False
    assert c.get("/companies/me", headers=_h(r.json()["access_token"])).status_code == 200
    r = _login(c, "hr3@x.io", temp)
    assert r.status_code == 401 and r.json()["code"] == "invalid_credentials"


def test_e43_3_initial_password_committed_before_response(c):
    """Смена пароля попадает в БД до отправки 204: клиент сразу читает /me и входит новым."""
    owner = _owner(c)
    temp = _create_hr(c, owner, "hr4@x.io")["temp_password"]
    hr = _h(_login(c, "hr4@x.io", temp).json()["access_token"])
    seen: list[int] = []

    async def drive():
        body = b'{"new_password": "brand-new-pass"}'
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"authorization", hr["Authorization"].encode()),
            (b"host", b"testserver"),
        ]
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/auth/password/initial",
            "raw_path": b"/auth/password/initial",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 1),
            "server": ("testserver", 80),
            "root_path": "",
        }
        sent = False

        async def receive():
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(msg):
            if msg["type"] == "http.response.start":
                # в этот момент клиент уже мог бы получить ответ: смотрим состояние БД
                seen.append(
                    _db(c, "select must_change_password from users where email='hr4@x.io'")[0][0]
                )
                seen.append(msg["status"])

        await c.app(scope, receive, send)

    c.portal.call(drive)
    assert seen == [0, 204]
