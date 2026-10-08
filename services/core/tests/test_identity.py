from datetime import UTC, datetime, timedelta
from pathlib import Path

import fakeredis
import pytest
from app.config import Settings
from app.identity.models import RefreshToken
from app.main import build_app
from core_helpers import upgrade_head
from fastapi.testclient import TestClient
from fsp_platform.jwt import decode_token
from fsp_platform.ratelimit import RateLimiter
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

CORE = Path(__file__).resolve().parents[1]
PWD = "correct-horse-battery"


@pytest.fixture
def ctx(tmp_path):
    db = tmp_path / "i.db"
    upgrade_head(f"sqlite+aiosqlite:///{db}")
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{db}",
        ui_bus_enabled=False,
        auth_cookie_path="/",
        allowed_origins=["https://dashboard.test"],
    )
    app = build_app(settings)
    with TestClient(app) as c:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        yield c, create_engine(f"sqlite:///{db}"), settings


def _reg(c, email="Ann@Example.com", role="candidate"):
    return c.post("/auth/register", json={"email": email, "password": PWD, "role": role})


def _auth(r):
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_register_login_me(ctx):
    c, engine, settings = ctx
    r = _reg(c)
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["email"] == "ann@example.com" and body["user"]["role"] == "candidate"
    claims = decode_token(settings.jwt_secret, body["access_token"])
    assert claims["role"] == "candidate" and claims["jti"] and claims["sub"] == body["user"]["id"]
    assert "httponly" in r.headers["set-cookie"].lower() and "rt=" in r.headers["set-cookie"]
    with Session(engine) as s:  # пароль хранится как argon2id, токен — как sha256
        from app.identity.models import User

        u = s.scalar(select(User))
        assert u.password_hash.startswith("$argon2id$")
        assert s.scalar(select(RefreshToken)).token_hash != c.cookies.get("rt")
    c.cookies.clear()
    r = c.post("/auth/login", json={"email": "ANN@example.com", "password": PWD})
    assert r.status_code == 200
    assert c.get("/me", headers=_auth(r)).json()["email"] == "ann@example.com"


def test_register_validation_and_duplicate(ctx):
    c, *_ = ctx
    assert _reg(c).status_code == 201
    r = _reg(c, "ann@example.com")
    assert r.status_code == 409 and r.json()["code"] == "email_taken"
    short = c.post(
        "/auth/register", json={"email": "b@x.io", "password": "short", "role": "candidate"}
    )
    assert short.status_code == 422
    for role in ("fsp_admin", "admin"):
        r = c.post("/auth/register", json={"email": "z@x.io", "password": PWD, "role": role})
        assert r.status_code == 422


def test_login_wrong_credentials_same_error(ctx):
    c, *_ = ctx
    _reg(c)
    a = c.post("/auth/login", json={"email": "ann@example.com", "password": "wrong-password"})
    b = c.post("/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"})
    assert a.status_code == b.status_code == 401
    assert a.json()["code"] == b.json()["code"] == "invalid_credentials"


def test_login_rate_limit_per_email(ctx):
    c, *_ = ctx
    _reg(c)
    for _ in range(5):
        assert (
            c.post(
                "/auth/login", json={"email": "ann@example.com", "password": "bad-pass-1"}
            ).status_code
            == 401
        )
    r = c.post("/auth/login", json={"email": "ann@example.com", "password": PWD})
    assert r.status_code == 429 and "retry-after" in r.headers


def test_me_requires_valid_token(ctx):
    c, *_ = ctx
    assert c.get("/me").status_code == 401
    assert c.get("/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_refresh_rotates(ctx):
    c, *_ = ctx
    _reg(c)
    old = c.cookies.get("rt")
    r = c.post("/auth/refresh")
    assert r.status_code == 200 and r.json()["access_token"]
    new = c.cookies.get("rt")
    assert new and new != old
    assert c.get("/me", headers=_auth(r)).status_code == 200


def test_refresh_reuse_revokes_family(ctx):
    c, engine, _ = ctx
    _reg(c)
    old = c.cookies.get("rt")
    assert c.post("/auth/refresh").status_code == 200
    newest = c.cookies.get("rt")
    # злоумышленник предъявляет уже использованный токен
    c.cookies.clear()
    c.cookies.set("rt", old)
    r = c.post("/auth/refresh")
    assert r.status_code == 401 and r.json()["code"] == "refresh_reused"
    # отзыв закоммичен: легитимный (новейший) токен тоже мёртв
    with Session(engine) as s:
        assert all(t.revoked_at is not None for t in s.scalars(select(RefreshToken)))
    c.cookies.clear()
    c.cookies.set("rt", newest)
    assert c.post("/auth/refresh").status_code == 401


def test_refresh_without_cookie_and_expired(ctx):
    c, engine, _ = ctx
    assert c.post("/auth/refresh").status_code == 401
    _reg(c)
    with Session(engine) as s, s.begin():
        s.execute(update(RefreshToken).values(expires_at=datetime.now(UTC) - timedelta(days=1)))
    r = c.post("/auth/refresh")
    assert r.status_code == 401 and r.json()["code"] == "unauthorized"


def test_logout_revokes_family(ctx):
    c, *_ = ctx
    _reg(c)
    token = c.cookies.get("rt")
    assert c.post("/auth/logout").status_code == 204
    c.cookies.set("rt", token)
    assert c.post("/auth/refresh").status_code == 401
    assert c.post("/auth/logout").status_code == 204  # идемпотентно, без cookie


def test_refresh_foreign_origin_rejected(ctx):
    c, *_ = ctx
    _reg(c)
    r = c.post("/auth/refresh", headers={"Origin": "https://evil.test"})
    assert r.status_code == 403
    assert c.post("/auth/refresh", headers={"Origin": "https://dashboard.test"}).status_code == 200


def test_inactive_user_cannot_use_tokens(ctx):
    from app.identity.models import User

    c, engine, _ = ctx
    r = _reg(c)
    with Session(engine) as s, s.begin():
        s.execute(update(User).values(is_active=False))
    assert c.get("/me", headers=_auth(r)).status_code == 401
    assert c.post("/auth/refresh").status_code == 401
    assert (
        c.post("/auth/login", json={"email": "ann@example.com", "password": PWD}).status_code == 401
    )


def test_require_roles(ctx):
    from app.identity.deps import require_roles
    from fastapi import Depends

    c, *_ = ctx
    app = c.app

    employer_only = Depends(require_roles("employer"))

    @app.get("/_only_employer")
    async def only(user=employer_only):
        return {"ok": True}

    cand = _reg(c)
    assert c.get("/_only_employer", headers=_auth(cand)).status_code == 403
    emp = _reg(c, "boss@example.com", "employer")
    assert c.get("/_only_employer", headers=_auth(emp)).status_code == 200
