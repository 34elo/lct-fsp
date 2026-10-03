import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import fakeredis
import pytest
from app.config import Settings
from app.identity.models import User
from app.main import build_app
from app.telegram.models import TelegramAccount
from app.telegram.service import sign_widget
from fastapi.testclient import TestClient
from fsp_platform.ratelimit import RateLimiter
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

CORE = Path(__file__).resolve().parents[1]
BOT_TOKEN = "123456:TEST-TOKEN-not-real"
SVC = {"Authorization": "Service test-bot-token"}
PWD = "correct-horse-battery"


@pytest.fixture
def ctx(tmp_path):
    db = tmp_path / "t.db"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url=sqlite+aiosqlite:///{db}", "upgrade", "head"],
        cwd=CORE,
        check=True,
        capture_output=True,
    )
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{db}",
        ui_bus_enabled=False,
        auth_cookie_path="/",
        service_token_bot="test-bot-token",
        tg_bot_token=BOT_TOKEN,
        tg_bot_username="fsp_test_bot",
        web_base_url="https://web.test",
    )
    app = build_app(settings)
    with TestClient(app) as c:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        yield c, create_engine(f"sqlite:///{db}")


def widget(tg_id=777, **over):
    data = {"id": tg_id, "first_name": "Ann", "username": "ann", "auth_date": int(time.time())}
    data.update(over)
    data["hash"] = sign_widget(data, BOT_TOKEN)
    return data


def start(c, tg=777, chat=777, **kw):
    return c.post(
        "/internal/tg/start",
        json={"tg_user_id": tg, "chat_id": chat, "username": "ann", **kw},
        headers=SVC,
    )


def reg(c, email="a@x.io"):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": "candidate"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]["id"]


def magic_token(url):
    return parse_qs(urlparse(url).query)["token"][0]


def test_widget_login_registers_and_logs_in(ctx):
    c, engine = ctx
    r = c.post("/auth/telegram", json=widget())
    assert r.status_code == 200 and r.json()["user"]["role"] == "candidate"
    assert r.json()["user"]["email"] is None and "rt=" in r.headers["set-cookie"]
    first = r.json()["user"]["id"]
    again = c.post("/auth/telegram", json=widget())
    assert again.json()["user"]["id"] == first
    h = {"Authorization": f"Bearer {again.json()['access_token']}"}
    assert c.get("/me", headers=h).json()["telegram_linked"] is True
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(TelegramAccount)) == 1


def test_widget_rejects_bad_signature_and_stale(ctx):
    c, _ = ctx
    bad = widget()
    bad["first_name"] = "Mallory"  # изменили поле после подписи
    assert c.post("/auth/telegram", json=bad).json()["code"] == "invalid_telegram_auth"
    no_hash = widget()
    del no_hash["hash"]
    assert c.post("/auth/telegram", json=no_hash).status_code == 401
    old = widget(auth_date=int(time.time()) - 25 * 3600)
    r = c.post("/auth/telegram", json=old)
    assert r.status_code == 401 and r.json()["code"] == "telegram_auth_expired"
    ok = widget(auth_date=int(time.time()) - 23 * 3600)
    assert c.post("/auth/telegram", json=ok).status_code == 200


def test_widget_disabled_without_token(ctx):
    c, _ = ctx
    c.app.state.settings.tg_bot_token = ""
    assert c.post("/auth/telegram", json=widget()).json()["code"] == "telegram_login_disabled"


def test_internal_requires_service_token(ctx):
    c, _ = ctx
    body = {"tg_user_id": 1, "chat_id": 1}
    assert c.post("/internal/tg/start", json=body).status_code == 401
    r = c.post("/internal/tg/start", json=body, headers={"Authorization": "Service nope"})
    assert r.status_code == 401
    c.app.state.settings.service_token_bot = ""  # пустой токен = закрыто
    assert (
        c.post("/internal/tg/start", json=body, headers={"Authorization": "Service "}).status_code
        == 401
    )


def test_start_creates_user_idempotently_and_consents(ctx):
    c, engine = ctx
    r = start(c)
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "candidate" and body["linked"] is False
    assert body["missing_consents"] == ["pd_processing", "telegram_notifications"]
    again = start(c, chat=778).json()
    assert again["user_id"] == body["user_id"]
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(User)) == 1
        assert s.scalar(select(TelegramAccount.chat_id)) == 778
    ok = c.post(
        "/internal/tg/consents",
        json={"tg_user_id": 777, "types": ["pd_processing", "telegram_notifications"]},
        headers=SVC,
    )
    assert ok.status_code == 204
    assert start(c).json()["missing_consents"] == []
    bad = c.post("/internal/tg/consents", json={"tg_user_id": 777, "types": ["nope"]}, headers=SVC)
    assert bad.status_code == 422
    unknown = c.post(
        "/internal/tg/consents", json={"tg_user_id": 1, "types": ["pd_processing"]}, headers=SVC
    )
    assert unknown.status_code == 404


def test_magic_link_one_time_login(ctx):
    c, _ = ctx
    user_id = start(c).json()["user_id"]
    r = c.post(
        "/internal/auth/magic-link",
        json={"tg_user_id": 777, "redirect": "/candidate/profile"},
        headers=SVC,
    )
    url = r.json()["url"]
    assert url.startswith("https://web.test/auth/magic?")
    assert parse_qs(urlparse(url).query)["redirect"] == ["/candidate/profile"]
    token = magic_token(url)
    login = c.post("/auth/magic", json={"token": token})
    assert login.status_code == 200 and login.json()["user"]["id"] == user_id
    reuse = c.post("/auth/magic", json={"token": token})
    assert reuse.status_code == 401 and reuse.json()["code"] == "invalid_magic_token"
    assert c.post("/auth/magic", json={"token": "garbage"}).status_code == 401


def test_magic_and_link_tokens_have_ttl_and_are_hashed():
    import asyncio
    import uuid

    from app.telegram import service

    async def run():
        redis = fakeredis.FakeAsyncRedis()
        uid = uuid.uuid4()
        token = await service._issue(redis, "magic", uid, service.MAGIC_TTL)
        keys = [k.decode() async for k in redis.scan_iter("magic:*")]
        assert keys and token not in keys[0]  # в Redis только хеш
        assert 0 < await redis.ttl(keys[0]) <= 300
        assert await service._consume(redis, "magic", token) == uid
        assert await service._consume(redis, "magic", token) is None

    asyncio.run(run())


@pytest.mark.parametrize("redirect", ["https://evil.test/", "//evil.test", "evil", "/a\\b", "/x\n"])
def test_magic_link_rejects_open_redirect(ctx, redirect):
    c, _ = ctx
    start(c)
    r = c.post(
        "/internal/auth/magic-link", json={"tg_user_id": 777, "redirect": redirect}, headers=SVC
    )
    assert r.status_code == 422 and r.json()["code"] == "invalid_redirect"


def test_magic_link_unknown_tg_is_404(ctx):
    c, _ = ctx
    r = c.post("/internal/auth/magic-link", json={"tg_user_id": 5, "redirect": "/"}, headers=SVC)
    assert r.status_code == 404


def test_deep_link_binding_merges_bot_stub(ctx):
    c, engine = ctx
    h, site_id = reg(c)
    assert c.get("/me", headers=h).json()["telegram_linked"] is False
    link = c.post("/me/telegram/link", headers=h).json()["deep_link"]
    assert link.startswith("https://t.me/fsp_test_bot?start=link_")
    token = link.split("start=link_")[1]
    stub = start(c).json()  # бот создал заготовку
    c.post(
        "/internal/tg/consents",
        json={"tg_user_id": 777, "types": ["pd_processing"]},
        headers=SVC,
    )
    r = c.post("/internal/tg/link", json={"tg_user_id": 777, "token": token}, headers=SVC)
    assert r.status_code == 200 and r.json()["user_id"] == site_id != stub["user_id"]
    me = c.get("/me", headers=h).json()
    assert me["telegram_linked"] is True and "pd_processing" in me["consents"]
    after = start(c).json()
    assert after["user_id"] == site_id and after["linked"] is True
    with Session(engine) as s:
        old = s.get(User, __import__("uuid").UUID(stub["user_id"]))
        assert old.is_active is False and old.deleted_at is not None
        assert s.scalar(select(func.count()).select_from(TelegramAccount)) == 1
    # токен одноразовый
    again = c.post("/internal/tg/link", json={"tg_user_id": 777, "token": token}, headers=SVC)
    assert again.status_code == 410 and again.json()["code"] == "link_token_invalid"


def test_link_conflicts(ctx):
    c, _ = ctx
    h1, _ = reg(c, "a@x.io")
    h2, _ = reg(c, "b@x.io")
    t1 = c.post("/me/telegram/link", headers=h1).json()["deep_link"].split("start=link_")[1]
    t2 = c.post("/me/telegram/link", headers=h2).json()["deep_link"].split("start=link_")[1]
    start(c)
    assert (
        c.post("/internal/tg/link", json={"tg_user_id": 777, "token": t1}, headers=SVC).status_code
        == 200
    )
    # тот же tg к другому аккаунту сайта: привязан к аккаунту с email
    r = c.post("/internal/tg/link", json={"tg_user_id": 777, "token": t2}, headers=SVC)
    assert r.status_code == 409 and r.json()["code"] == "telegram_already_linked"
    # другой Telegram к аккаунту, у которого Telegram уже есть
    t3 = c.post("/me/telegram/link", headers=h1).json()["deep_link"].split("start=link_")[1]
    start(c, tg=888, chat=888)
    r = c.post("/internal/tg/link", json={"tg_user_id": 888, "token": t3}, headers=SVC)
    assert r.status_code == 409
    # повтор того же токена для уже привязанного — токен сожжён, не меняет состояние
    assert (
        c.post("/internal/tg/link", json={"tg_user_id": 999, "token": "x"}, headers=SVC).status_code
        == 410
    )


def test_link_idempotent_for_same_account(ctx):
    c, _ = ctx
    h, site_id = reg(c)
    t = c.post("/me/telegram/link", headers=h).json()["deep_link"].split("start=link_")[1]
    start(c)
    assert (
        c.post("/internal/tg/link", json={"tg_user_id": 777, "token": t}, headers=SVC).status_code
        == 200
    )
    t2 = c.post("/me/telegram/link", headers=h).json()["deep_link"].split("start=link_")[1]
    r = c.post("/internal/tg/link", json={"tg_user_id": 777, "token": t2}, headers=SVC)
    assert r.status_code == 200 and r.json()["user_id"] == site_id


def test_me_telegram_link_requires_auth_and_bot_name(ctx):
    c, _ = ctx
    assert c.post("/me/telegram/link").status_code == 401
    h, _ = reg(c)
    c.app.state.settings.tg_bot_username = ""
    assert c.post("/me/telegram/link", headers=h).status_code == 503
