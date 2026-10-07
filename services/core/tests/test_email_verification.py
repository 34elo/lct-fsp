"""E20-1: поток кода подтверждения email."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from app.identity.models import EmailVerification
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

PWD = "correct-horse-battery"


class FakeMailer:
    def __init__(self):
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to, subject, body):
        self.sent.append((to, subject, body))

    def code(self) -> str:
        return re.search(r"\d{6}", self.sent[-1][2]).group()


@pytest.fixture
def mail(api):
    api.app.state.mailer = FakeMailer()
    return api.app.state.mailer


def _reg(api, email="ann@example.com", role="candidate"):
    r = api.post("/auth/register", json={"email": email, "password": PWD, "role": role})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]["id"]


def _db(api, fn):
    eng = create_engine(f"sqlite:///{api.db_path}")
    with Session(eng) as s:
        fn(s)
        s.commit()


def test_register_sends_code_and_verify(api, mail):
    h, _ = _reg(api)
    assert len(mail.sent) == 1 and mail.sent[0][0] == "ann@example.com"
    assert api.get("/me", headers=h).json()["email_verified"] is False
    assert api.post("/auth/email/verify", json={"code": mail.code()}, headers=h).status_code == 204
    assert api.get("/me", headers=h).json()["email_verified"] is True
    # повтор после успеха идемпотентен
    assert api.post("/auth/email/verify", json={"code": "000000"}, headers=h).status_code == 204


def test_wrong_code_400_and_attempts_limit(api, mail):
    h, _ = _reg(api)
    for _i in range(5):
        r = api.post("/auth/email/verify", json={"code": "abcdef"}, headers=h)
        assert r.status_code == 400 and r.json()["code"] == "invalid_code"
    r = api.post("/auth/email/verify", json={"code": mail.code()}, headers=h)
    assert r.status_code == 429 and r.json()["code"] == "too_many_attempts"


def test_verify_locks_code_row(api, mail, monkeypatch):
    """Счётчик попыток читается FOR UPDATE: параллельные угадывания не теряют инкремент."""
    from sqlalchemy.ext.asyncio import AsyncSession

    h, _ = _reg(api)
    locks: list[bool] = []
    orig = AsyncSession.get

    async def spy(self, entity, ident, **kw):
        if entity is EmailVerification:
            locks.append(bool(kw.get("with_for_update")))
        return await orig(self, entity, ident, **kw)

    monkeypatch.setattr(AsyncSession, "get", spy)
    api.post("/auth/email/verify", json={"code": "abcdef"}, headers=h)
    assert locks == [True]


def test_expired_code(api, mail):
    h, uid = _reg(api)
    past = datetime.now(UTC) - timedelta(minutes=1)
    _db(api, lambda s: s.execute(update(EmailVerification).values(expires_at=past)))
    r = api.post("/auth/email/verify", json={"code": mail.code()}, headers=h)
    assert r.status_code == 400 and r.json()["code"] == "code_expired"


def test_resend_cooldown_then_new_code_invalidates_old(api, mail):
    h, _ = _reg(api)
    r = api.post("/auth/email/send", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "cooldown"
    old = mail.code()
    sent = datetime.now(UTC) - timedelta(minutes=5)
    _db(api, lambda s: s.execute(update(EmailVerification).values(sent_at=sent)))
    assert api.post("/auth/email/send", headers=h).status_code == 204
    assert len(mail.sent) == 2
    if mail.code() != old:
        r = api.post("/auth/email/verify", json={"code": old}, headers=h)
        assert r.status_code == 400
    assert api.post("/auth/email/verify", json={"code": mail.code()}, headers=h).status_code == 204


def test_endpoints_require_auth(api, mail):
    assert api.post("/auth/email/send").status_code == 401
    assert api.post("/auth/email/verify", json={"code": "123456"}).status_code == 401


def test_gate_by_require_verified_email(api, mail):
    from app.identity import service
    from app.identity.models import User
    from fsp_platform.app import ProblemError

    h, _ = _reg(api)
    user = User(email="x@example.com", role="candidate")
    with pytest.raises(ProblemError) as e:
        service.require_verified_email(user, required=True)
    assert e.value.code == "email_not_verified"
    api.post("/auth/email/verify", json={"code": mail.code()}, headers=h)
