from pathlib import Path

import fakeredis
import pytest
from app.config import Settings
from app.consents.deps import require_consent
from app.main import build_app
from core_helpers import upgrade_head
from fastapi import Depends
from fastapi.testclient import TestClient
from fsp_contracts.enums import ConsentType
from fsp_platform.ratelimit import RateLimiter

CORE = Path(__file__).resolve().parents[1]
PWD = "correct-horse-battery"


@pytest.fixture
def c(tmp_path):
    db = tmp_path / "c.db"
    upgrade_head(f"sqlite+aiosqlite:///{db}")
    app = build_app(Settings(database_url=f"sqlite+aiosqlite:///{db}", ui_bus_enabled=False))

    gate = Depends(require_consent(ConsentType.pd_processing))

    @app.post("/_probe/resume")
    async def probe(user=gate):
        return {"ok": True}

    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        yield client


def _user(c, email):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": "candidate"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_list_and_gate(c):
    h = _user(c, "a@x.io")
    lst = c.get("/me/consents", headers=h).json()
    assert len(lst) == len(ConsentType) and not any(i["granted"] for i in lst)
    assert [i["required"] for i in lst if i["type"] == "pd_processing"] == [True]
    r = c.post("/_probe/resume", headers=h)
    assert r.status_code == 403 and r.json()["code"] == "consent_required"
    assert c.post("/_probe/resume").status_code == 401


def test_grant_revoke_idempotent(c):
    h = _user(c, "a@x.io")
    body = {"consents": [{"type": "pd_processing", "granted": True, "version": "2025-09-01"}]}
    for _ in range(2):  # повтор не меняет результат
        assert c.put("/me/consents", json=body, headers=h).status_code == 200
    assert c.post("/_probe/resume", headers=h).status_code == 200
    assert c.get("/me", headers=h).json()["consents"] == ["pd_processing"]
    off = {"consents": [{"type": "pd_processing", "granted": False}]}
    out = c.put("/me/consents", json=off, headers=h).json()
    assert not [i for i in out if i["type"] == "pd_processing"][0]["granted"]
    assert c.post("/_probe/resume", headers=h).status_code == 403
    c.put("/me/consents", json=body, headers=h)  # повторная выдача после отзыва
    assert c.post("/_probe/resume", headers=h).status_code == 200


def test_version_mismatch_and_isolation(c):
    h1, h2 = _user(c, "a@x.io"), _user(c, "b@x.io")
    bad = {"consents": [{"type": "fsp_data", "granted": True, "version": "old"}]}
    r = c.put("/me/consents", json=bad, headers=h1)
    assert r.status_code == 409 and r.json()["code"] == "consent_version_mismatch"
    c.put(
        "/me/consents", json={"consents": [{"type": "pd_processing", "granted": True}]}, headers=h1
    )
    assert c.post("/_probe/resume", headers=h2).status_code == 403  # чужое согласие не считается
    assert c.put("/me/consents", json={"consents": []}, headers=h1).status_code == 422
