from uuid import uuid4

import fakeredis
import pytest
from fastapi.testclient import TestClient
from fsp_connector.api import router
from fsp_connector.config import Settings
from fsp_connector.errors import FspError
from fsp_connector.linking import LinkService
from fsp_connector.main import STATUS
from fsp_connector.models import FspLink, FspLinkConflict, metadata
from fsp_contracts import Envelope
from fsp_platform.app import create_app, problem_response
from fsp_platform.db import make_engine, make_session_factory
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import func, select

TOKEN = "t"
H = {"Authorization": f"Service {TOKEN}"}


@pytest.fixture
async def env(tmp_path, adapter, mock_store):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    factory = make_session_factory(engine)
    redis = fakeredis.FakeAsyncRedis()
    svc = LinkService(adapter, factory, redis, code_ttl=600, max_attempts=5)
    yield svc, factory, redis, mock_store
    await engine.dispose()


def _code(store, pid):
    return [c for c in store.codes if c["participant_id"] == pid][-1]["code"]


async def _events(factory):
    async with factory() as s:
        return (await s.execute(select(OutboxRecord).order_by(OutboxRecord.id))).scalars().all()


async def test_code_flow_links_verified_and_publishes_once(env):
    svc, factory, redis, store = env
    cid = uuid4()
    method, masked = await svc.start(cid, "p-anya", None)
    assert method == "code" and "*" in masked.masked
    assert await redis.ttl(f"s:fspcode:{cid}") > 0
    wrong = "000000" if _code(store, "p-anya") != "000000" else "111111"
    assert await svc.verify(cid, wrong) is False  # неверный код не привязывает
    async with factory() as s:
        assert await s.get(FspLink, cid) is None
    assert await svc.verify(cid, _code(store, "p-anya")) is True
    async with factory() as s:
        link = await s.get(FspLink, cid)
    assert (link.participant_id, link.verified, link.method) == ("p-anya", True, "code")
    evs = await _events(factory)
    assert [e.type for e in evs] == ["fsp.linked"]
    assert Envelope.model_validate(evs[0].payload).payload["verified"] is True
    # повторная привязка того же — событие не дублируется
    await svc._bind(cid, "p-anya", "code", True)
    assert len(await _events(factory)) == 1


async def test_wrong_codes_limited_to_five_attempts(env):
    svc, _, _, store = env
    cid = uuid4()
    await svc.start(cid, "p-anya", None)
    good = _code(store, "p-anya")
    bad = "000000" if good != "000000" else "111111"
    for _ in range(5):
        assert await svc.verify(cid, bad) is False
    from fsp_platform.app import ProblemError

    with pytest.raises(ProblemError) as e:
        await svc.verify(cid, good)
    assert e.value.status == 429 and e.value.code == "too_many_attempts"


async def test_verify_without_pending_is_expired(env):
    svc, *_ = env
    from fsp_platform.app import ProblemError

    with pytest.raises(ProblemError) as e:
        await svc.verify(uuid4(), "123456")
    assert e.value.code == "code_expired"


async def test_manual_link_unverified(env):
    svc, factory, *_ = env
    cid = uuid4()
    await svc.link_manual(cid, "p-anya")
    async with factory() as s:
        link = await s.get(FspLink, cid)
    assert (link.verified, link.method) == (False, "manual")
    evs = await _events(factory)
    assert Envelope.model_validate(evs[0].payload).payload["method"] == "manual"


async def test_manual_then_code_upgrades(env):
    svc, factory, _, store = env
    cid = uuid4()
    await svc.link_manual(cid, "p-anya")
    await svc.start(cid, "p-anya", None)
    assert await svc.verify(cid, _code(store, "p-anya")) is True
    async with factory() as s:
        link = await s.get(FspLink, cid)
    assert (link.verified, link.method) == (True, "code")
    assert len(await _events(factory)) == 2


async def test_participant_cannot_be_linked_twice_and_conflict_recorded(env):
    from fsp_platform.app import ProblemError

    svc, factory, *_ = env
    a, b = uuid4(), uuid4()
    await svc.link_manual(a, "p-anya")
    with pytest.raises(ProblemError) as e:
        await svc.link_manual(b, "p-anya")
    assert e.value.status == 409 and e.value.code == "fsp_already_linked"
    with pytest.raises(ProblemError):
        await svc.start(b, "p-anya", None)
    async with factory() as s:
        n = (await s.execute(select(func.count()).select_from(FspLinkConflict))).scalar_one()
        c = (await s.execute(select(FspLinkConflict).limit(1))).scalar_one()
        assert await s.get(FspLink, b) is None
    assert n == 2 and c.candidate_id == b and c.participant_id == "p-anya"
    assert len(await _events(factory)) == 1


async def test_candidate_cannot_switch_participant(env):
    from fsp_platform.app import ProblemError

    svc, *_ = env
    cid = uuid4()
    await svc.link_manual(cid, "p-anya")
    with pytest.raises(ProblemError) as e:
        await svc._bind(cid, "p-other", "manual", False)
    assert e.value.code == "candidate_already_linked"


async def test_unknown_participant_is_not_found(env):
    from fsp_connector.errors import FspNotFound

    svc, *_ = env
    with pytest.raises(FspNotFound):
        await svc.start(uuid4(), "p-nope", None)


# --- HTTP-слой -----------------------------------------------------------------


@pytest.fixture
def client(env):
    svc, *_ = env
    app = create_app("t")
    app.include_router(router)
    app.state.settings = Settings(service_token_core=TOKEN)
    app.state.links = svc

    @app.exception_handler(FspError)
    async def _h(_, exc):
        st, title = STATUS.get(exc.code, STATUS["fsp_error"])
        return problem_response(st, exc.code, title)

    return TestClient(app)


def test_internal_requires_service_token(client):
    url = "/internal/oauth/authorize-url?state=s&code_challenge=c"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Service no"}).status_code == 401
    r = client.get(url, headers=H)
    assert r.status_code == 200 and "code_challenge=c" in r.json()["url"]


def test_empty_token_closes_internal(client):
    client.app.state.settings = Settings(service_token_core="")
    r = client.get("/internal/oauth/authorize-url?state=s&code_challenge=c", headers=H)
    assert r.status_code == 401


def test_http_link_unknown_participant_404_and_conflict_409(client):
    r = client.post(
        "/internal/links", headers=H, json={"candidate_id": str(uuid4()), "participant_id": "zz"}
    )
    assert r.status_code == 404 and r.json()["code"] == "fsp_not_found"
    a, b = str(uuid4()), str(uuid4())
    body = {"participant_id": "p-anya", "manual": True}
    assert client.post("/internal/links", headers=H, json={"candidate_id": a, **body}).json() == {
        "method": "manual",
        "masked_contact": None,
    }
    r = client.post("/internal/links", headers=H, json={"candidate_id": b, **body})
    assert r.status_code == 409 and r.json()["code"] == "fsp_already_linked"


def test_http_code_flow_and_oauth(client, env):
    _, _, _, store = env
    cid = str(uuid4())
    r = client.post(
        "/internal/links", headers=H, json={"candidate_id": cid, "participant_id": "p-anya"}
    )
    assert r.json()["method"] == "code" and r.json()["masked_contact"]
    bad = client.post("/internal/links/verify", headers=H, json={"candidate_id": cid, "code": "x"})
    assert bad.json() == {"verified": False}
    ok = client.post(
        "/internal/links/verify",
        headers=H,
        json={"candidate_id": cid, "code": _code(store, "p-anya")},
    )
    assert ok.json() == {"verified": True}


async def test_oauth_exchange_links_verified(env, mock_app):
    import base64
    import hashlib
    from urllib.parse import parse_qs, urlparse

    import httpx
    from fsp_connector.errors import FspAuthError

    svc, factory, *_ = env
    verifier = "v" * 50
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    q = parse_qs(urlparse(svc.authorize_url("st", challenge)).query)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mock_app), base_url="http://mock"
    ) as browser:
        r = await browser.post(
            "/oauth/authorize",
            data={
                "participant_id": "p-anya",
                "redirect_uri": q["redirect_uri"][0],
                "code_challenge": challenge,
                "state": "st",
            },
        )
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    cid = uuid4()
    assert await svc.exchange(cid, code, verifier) == ("p-anya", True)
    async with factory() as s:
        link = await s.get(FspLink, cid)
    assert (link.verified, link.method) == (True, "oauth")
    assert [e.type for e in await _events(factory)] == ["fsp.linked"]
    with pytest.raises(FspAuthError):  # код одноразовый
        await svc.exchange(cid, code, verifier)
    assert len(await _events(factory)) == 1
