"""Офферы: создание, вилка, лимиты, идемпотентность, автомат статусов, права (E8-1)."""

import asyncio
import itertools
import json
import shutil
import sqlite3
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import fakeredis
import pytest
from app.config import Settings
from app.main import build_app
from app.offers import router as offers_router
from app.offers import service
from fastapi.testclient import TestClient
from fsp_contracts.enums import OfferStatus
from fsp_platform.db import make_engine, make_session_factory
from fsp_platform.ratelimit import RateLimiter

CORE = Path(__file__).resolve().parents[1]
PWD = "correct-horse-battery"
INN = "7707083893"
S = OfferStatus


@pytest.fixture(scope="module")
def template_db(tmp_path_factory):
    """Миграции гоняем один раз на модуль, дальше копируем файл."""
    db = tmp_path_factory.mktemp("tpl") / "o.db"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url=sqlite+aiosqlite:///{db}", "upgrade", "head"],
        cwd=CORE, check=True, capture_output=True,
    )  # fmt: skip
    with sqlite3.connect(db) as con:
        for slug in ("python", "fastapi"):
            con.execute(
                "insert into skills (id, slug, name, kind, status, source, support_candidates,"
                " support_vacancies, testable) values (?,?,?,?,?,?,0,0,0)",
                (uuid.uuid4().hex, slug, slug, "tech", "active", "seed"),
            )
    return db


@pytest.fixture
def c(tmp_path, template_db):
    db = tmp_path / "o.db"
    shutil.copy(template_db, db)
    app = build_app(Settings(database_url=f"sqlite+aiosqlite:///{db}", ui_bus_enabled=False))
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        client.db = db
        yield client


def _past(**kw):
    """Момент в прошлом в формате, в котором SQLAlchemy хранит datetime в SQLite."""
    return (datetime.now(UTC) - timedelta(**kw)).strftime("%Y-%m-%d %H:%M:%S.%f")


def _db(c, sql, *args):
    with sqlite3.connect(c.db) as con:
        return con.execute(sql, args).fetchall()


def _employer(c, email, *, verified=True, name="Acme Labs", inn=INN):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": "employer"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    co = c.post("/companies", json={"name": name, "inn": inn}, headers=h).json()
    if verified:
        _db(c, "update companies set status='verified' where id=?", co["id"].replace("-", ""))
    return h


def _vacancy(c, h, *, publish=True):
    body = {
        "title": "Backend", "role": "backend", "grade_min": "middle", "grade_max": "senior",
        "formats": ["remote"], "employment_type": "full", "salary_from": 200000,
        "salary_to": 300000, "skills": [{"slug": "python"}],
    }  # fmt: skip
    vid = c.post("/vacancies", json=body, headers=h).json()["id"]
    if publish:
        assert c.post(f"/vacancies/{vid}/publish", headers=h).status_code == 200
    return vid


def _candidate(c, email, n, **kw):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": "candidate"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    body = {"consents": [{"type": "pd_processing", "granted": True}]}
    assert c.put("/me/consents", json=body, headers=h).status_code == 200
    assert c.get("/candidates/me/profile", headers=h).status_code == 200
    (uid,) = _db(c, "select user_id from candidates order by rowid desc limit 1")[0]
    cols = {"primary_role": "backend", "grade": "middle", "pseudo_id": f"pid{n:04d}"} | kw
    sets = ", ".join(f"{k}=?" for k in cols)
    _db(c, f"update candidates set {sets} where user_id=?", *cols.values(), uid)
    return h, f"pid{n:04d}", uid


def _offer(c, h, vid, pid, key=None, **over):
    body = {"vacancy_id": vid, "candidate_pseudo_id": pid, "salary_from": 250000,
            "salary_to": 320000, "message": "Привет!"} | over  # fmt: skip
    body = {k: v for k, v in body.items() if v is not None}
    return c.post("/offers", json=body, headers={**h, "Idempotency-Key": key or uuid.uuid4().hex})


@pytest.fixture
def world(c):
    e = _employer(c, "e@x.ru")
    vid = _vacancy(c, e)
    ch, pid, uid = _candidate(c, "c@x.ru", 1, salary_min=350000)
    return c, e, vid, ch, pid, uid


def _events(c, like="offer.%"):
    return [r[0] for r in _db(c, "select type from outbox where type like ? order by id", like)]


def test_create_offer(world):
    c, e, vid, ch, pid, uid = world
    r = _offer(c, e, vid, pid)
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["status"] == "sent" and o["awaiting_reply_from"] == "candidate"
    assert (o["salary_from"], o["salary_to"], o["message"]) == (250000, 320000, "Привет!")
    assert o["below_candidate_min"] is True  # потолок вилки ниже желаемого минимума
    assert o["vacancy"]["id"] == vid and o["candidate"]["pseudo_id"] == pid
    created = datetime.fromisoformat(o["created_at"])
    expires = datetime.fromisoformat(o["expires_at"])
    assert timedelta(days=6, hours=23) < expires - created <= timedelta(days=7)
    text = json.dumps(o)
    assert "user_id" not in text and "@" not in text  # до принятия — только анонимная карточка
    assert _db(c, "select from_status, to_status, actor from offer_events") == [
        (None, "sent", "company")
    ]
    assert _events(c) == ["offer.sent"]
    payload = json.loads(_db(c, "select payload from outbox where type='offer.sent'")[0][0])
    assert payload["payload"]["offer_id"] == o["id"] and payload["payload"]["status"] == "sent"


def test_match_snapshot_is_copied(world):
    c, e, vid, ch, pid, uid = world
    expl = [{"kind": "plus", "code": "skill_confirmed", "text": "Python", "skill": "python",
             "evidence_ids": [], "weight": 0.5}]  # fmt: skip
    _db(
        c,
        "insert into matches (vacancy_id, candidate_id, score, breakdown, explanation,"
        " candidate_version, vacancy_version, computed_at) values (?,?,?,?,?,1,1,?)",
        vid.replace("-", ""), uid, 0.81, "{}", json.dumps(expl), datetime.now(UTC).isoformat(),
    )  # fmt: skip
    o = _offer(c, e, vid, pid).json()
    assert o["match_snapshot"]["score"] == 0.81
    assert o["match_snapshot"]["explanation"][0]["code"] == "skill_confirmed"


def test_salary_range_is_mandatory(world):
    c, e, vid, ch, pid, uid = world
    for over in ({"salary_from": None}, {"salary_to": None}, {"salary_from": 0}):
        r = _offer(c, e, vid, pid, **over)
        assert (r.status_code, r.json()["code"]) == (422, "salary_range_required"), over
    r = _offer(c, e, vid, pid, salary_from=300000, salary_to=200000)
    assert (r.status_code, r.json()["code"]) == (422, "invalid_salary_range")
    r = _offer(c, e, vid, pid, salary_from=100000, salary_to=300000)  # слишком широкая — не запрет
    assert r.status_code == 201
    assert _db(c, "select count(*) from offers") == [(1,)]


def test_create_preconditions(c):
    e = _employer(c, "e@x.ru")
    unverified = _employer(c, "u@x.ru", verified=False, name="Pending")
    vid, draft = _vacancy(c, e), _vacancy(c, e, publish=False)
    other_vid = _vacancy(c, _employer(c, "o@x.ru", name="Other"))
    ch, pid, _ = _candidate(c, "c1@x.ru", 1)
    _, dnd, _ = _candidate(c, "c2@x.ru", 2, search_status="dnd")
    _, stop, _ = _candidate(c, "c3@x.ru", 3)

    def code(r):
        return r.status_code, r.json().get("code")

    assert code(_offer(c, unverified, _vacancy(c, unverified, publish=False), pid)) == (
        403, "company_not_verified")  # fmt: skip
    assert code(_offer(c, e, draft, pid)) == (409, "vacancy_not_published")
    assert code(_offer(c, e, other_vid, pid)) == (404, "vacancy_not_found")
    assert code(_offer(c, e, str(uuid.uuid4()), pid)) == (404, "vacancy_not_found")
    assert code(_offer(c, e, vid, "nope")) == (404, "candidate_not_found")
    assert code(_offer(c, e, vid, dnd)) == (404, "candidate_not_found")
    co_id = _db(c, "select id from companies where name='Acme Labs'")[0][0]
    _db(c, "update candidates set stoplist_company_ids=? where pseudo_id=?", json.dumps([
        f"{uuid.UUID(co_id)}"]), stop)  # fmt: skip
    assert code(_offer(c, e, vid, stop)) == (404, "candidate_not_found")
    assert code(_offer(c, ch, vid, pid)) == (403, "forbidden")  # кандидат не создаёт офферы
    assert _db(c, "select count(*) from offers") == [(0,)]
    assert _events(c) == []


def test_duplicate_offer_for_vacancy_is_rejected(world):
    c, e, vid, ch, pid, uid = world
    assert _offer(c, e, vid, pid).status_code == 201
    r = _offer(c, e, vid, pid)  # другой ключ — это новый запрос
    assert (r.status_code, r.json()["code"]) == (409, "offer_exists")
    assert _db(c, "select count(*) from offers") == [(1,)]


def test_idempotency_key(world):
    c, e, vid, ch, pid, uid = world
    first = _offer(c, e, vid, pid, key="k-1")
    again = _offer(c, e, vid, pid, key="k-1")
    assert (first.status_code, again.status_code) == (201, 201)
    assert first.json()["id"] == again.json()["id"]
    assert (
        again.headers.get("Idempotent-Replay") == "true"
        and "Idempotent-Replay" not in first.headers
    )
    assert _db(c, "select count(*) from offers") == [(1,)]
    assert _events(c) == ["offer.sent"]  # повтор не дублирует событие
    assert _db(c, "select count(*) from offer_events") == [(1,)]
    _, pid2, _ = _candidate(c, "c2@x.ru", 2)
    r = _offer(c, e, vid, pid2, key="k-1")  # тот же ключ, другой запрос
    assert (r.status_code, r.json()["code"]) == (409, "idempotency_key_reused")
    no_key = c.post("/offers", headers=e, json={"vacancy_id": vid, "candidate_pseudo_id": pid})
    assert (no_key.status_code, no_key.json()["code"]) == (422, "idempotency_key_required")
    other = _employer(c, "o@x.ru", name="Other")  # ключи компаний не пересекаются
    assert _offer(c, other, _vacancy(c, other), pid, key="k-1").status_code == 201


def test_company_daily_limit(world, monkeypatch):
    c, e, vid, ch, pid, uid = world
    monkeypatch.setattr(offers_router, "_LIMITS", service.OfferLimits(company_per_day=2))
    pids = [_candidate(c, f"x{i}@x.ru", 10 + i)[1] for i in range(3)]
    assert _offer(c, e, vid, pids[0], key="k0").status_code == 201
    assert _offer(c, e, vid, pids[1]).status_code == 201
    r = _offer(c, e, vid, pids[2])
    assert (r.status_code, r.json()["code"]) == (429, "offer_limit_exceeded")
    assert int(r.headers["Retry-After"]) > 0
    # повтор уже принятого запроса лимитом не блокируется
    assert _offer(c, e, vid, pids[0], key="k0").status_code == 201
    _db(c, "update offers set created_at=?", _past(hours=25))
    assert _offer(c, e, vid, pids[2]).status_code == 201  # окно скользит


def test_candidate_incoming_limit(c, monkeypatch):
    monkeypatch.setattr(offers_router, "_LIMITS", service.OfferLimits(candidate_per_day=1))
    ch, pid, _ = _candidate(c, "c@x.ru", 1)
    e1 = _employer(c, "e1@x.ru", name="Alpha")
    e2 = _employer(c, "e2@x.ru", name="Beta")
    assert _offer(c, e1, _vacancy(c, e1), pid).status_code == 201
    r = _offer(c, e2, _vacancy(c, e2), pid)
    assert (r.status_code, r.json()["code"]) == (429, "candidate_offer_limit_exceeded")


def test_limits_loaded_from_scoring_yaml():
    lim = service.OfferLimits.load()
    assert (lim.company_per_day, lim.candidate_per_day, lim.validity_days) == (20, 10, 7)


def test_transition_table_is_exhaustive():
    """Разрешены ровно переходы из flows.md F8; всё остальное запрещено."""
    expected = {
        ("sent", "viewed"), ("sent", "accepted"), ("viewed", "accepted"), ("sent", "declined"),
        ("viewed", "declined"), ("sent", "expired"), ("viewed", "expired"), ("sent", "withdrawn"),
        ("viewed", "withdrawn"), ("accepted", "interview"), ("interview", "hired"),
        ("interview", "not_hired"), ("accepted", "not_hired"),
    }  # fmt: skip
    assert {(a.value, b.value) for a, b in service.TRANSITIONS} == expected
    terminal = {S.hired, S.not_hired, S.declined, S.expired, S.withdrawn}
    assert not [p for p in service.TRANSITIONS if p[0] in terminal]
    assert set(itertools.product(S, S)) - set(
        service.TRANSITIONS
    )  # запретов больше, чем разрешений


def _status(c, h, oid):
    return c.get(f"/offers/{oid}", headers=h).json()["status"]


def test_candidate_view_accept_flow(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    assert (
        c.get(f"/offers/{oid}", headers=e).json()["status"] == "sent"
    )  # работодатель не «просмотр»
    r = c.get(f"/offers/{oid}", headers=ch)
    assert r.status_code == 200 and r.json()["status"] == "viewed"
    assert r.json()["company"]["name"] == "Acme Labs" and r.json()["company"]["verified"] is True
    assert c.get(f"/offers/{oid}", headers=ch).json()["status"] == "viewed"  # повтор — без события
    assert _events(c) == ["offer.sent", "offer.viewed"]
    r = c.post(f"/offers/{oid}/accept", headers=ch)
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    assert r.json()["awaiting_reply_from"] is None
    assert _events(c)[-1] == "offer.accepted"
    again = c.post(f"/offers/{oid}/accept", headers=ch)  # повторный запрос не меняет результат
    assert (again.status_code, again.json()["code"]) == (409, "invalid_transition")
    assert _events(c) == ["offer.sent", "offer.viewed", "offer.accepted"]
    assert _db(c, "select from_status, to_status, actor from offer_events order by id") == [
        (None, "sent", "company"), ("sent", "viewed", "candidate"),
        ("viewed", "accepted", "candidate"),
    ]  # fmt: skip
    assert _db(c, "select responded_at is not null, viewed_at is not null from offers") == [(1, 1)]


def test_accept_straight_from_sent(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    assert c.post(f"/offers/{oid}/accept", headers=ch).json()["status"] == "accepted"
    assert _events(c) == ["offer.sent", "offer.accepted"]


def test_decline(c):
    e = _employer(c, "e@x.ru")
    vid = _vacancy(c, e)
    ch, pid, _ = _candidate(c, "c@x.ru", 1)
    oid = _offer(c, e, vid, pid).json()["id"]
    bad = c.post(f"/offers/{oid}/decline", json={"reason": "bad"}, headers=ch)
    assert bad.status_code == 422
    r = c.post(
        f"/offers/{oid}/decline", json={"reason": "low_salary", "comment": "мало"}, headers=ch
    )
    assert r.status_code == 200 and r.json()["status"] == "declined"
    assert r.json()["decline"] == {"reason": "low_salary", "comment": "мало"}
    assert _events(c)[-1] == "offer.declined"
    payload = json.loads(_db(c, "select payload from outbox where type='offer.declined'")[0][0])
    assert payload["payload"]["decline_reason"] == "low_salary"
    assert c.post(f"/offers/{oid}/accept", headers=ch).json()["code"] == "invalid_transition"
    again = c.post(f"/offers/{oid}/decline", json={"reason": "other"}, headers=ch)
    assert again.status_code == 409
    assert _db(c, "select decline_reason from offers") == [("low_salary",)]  # не перезаписан
    assert c.post(f"/offers/{oid}/withdraw", headers=e).status_code == 409
    ofr = c.get("/offers?status=declined", headers=e).json()
    assert [o["id"] for o in ofr] == [oid] and ofr[0]["decline"]["reason"] == "low_salary"


def test_withdraw(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    c.get(f"/offers/{oid}", headers=ch)  # viewed
    r = c.post(f"/offers/{oid}/withdraw", headers=e)
    assert r.status_code == 200 and r.json()["status"] == "withdrawn"
    assert _events(c)[-1] == "offer.withdrawn"
    assert c.post(f"/offers/{oid}/withdraw", headers=e).status_code == 409
    assert c.post(f"/offers/{oid}/accept", headers=ch).json()["code"] == "invalid_transition"
    # отозванный оффер кандидат больше не может «открыть» в другой статус
    assert _status(c, ch, oid) == "withdrawn"


def test_withdraw_forbidden_after_accept(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    c.post(f"/offers/{oid}/accept", headers=ch)
    r = c.post(f"/offers/{oid}/withdraw", headers=e)
    assert (r.status_code, r.json()["code"]) == (409, "invalid_transition")


def test_company_status_chain(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]

    def st(s, h=e):
        return c.post(f"/offers/{oid}/status", json={"status": s}, headers=h)

    for s in ("interview", "hired", "not_hired"):  # из sent нельзя
        assert st(s).status_code == 409
    for s in ("accepted", "declined", "viewed", "withdrawn", "expired", "sent"):
        assert st(s).status_code == 422  # такие статусы вручную не ставятся
    c.post(f"/offers/{oid}/accept", headers=ch)
    assert st("hired").status_code == 409  # минуя interview нельзя
    assert st("interview").json()["status"] == "interview"
    assert st("interview").status_code == 409
    assert st("hired").json()["status"] == "hired"
    assert st("not_hired").status_code == 409  # hired — конечный
    assert _events(c)[-3:] == ["offer.accepted"] + ["offer.status_changed"] * 2
    assert st("interview", ch).status_code == 403  # кандидат не двигает воронку


def test_accepted_may_become_not_hired(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    c.post(f"/offers/{oid}/accept", headers=ch)
    r = c.post(f"/offers/{oid}/status", json={"status": "not_hired"}, headers=e)
    assert r.json()["status"] == "not_hired"


def test_expired_offer_cannot_be_answered(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    _db(c, "update offers set expires_at=?", _past(minutes=1))
    for call in (
        lambda: c.post(f"/offers/{oid}/accept", headers=ch),
        lambda: c.post(f"/offers/{oid}/decline", json={"reason": "other"}, headers=ch),
        lambda: c.post(f"/offers/{oid}/withdraw", headers=e),
    ):
        r = call()
        assert (r.status_code, r.json()["code"]) == (409, "offer_expired")
    assert _status(c, e, oid) == "sent"


def test_expire_due_marks_expired_idempotently(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    _db(c, "update offers set expires_at=?", _past(minutes=1))
    url = f"sqlite+aiosqlite:///{c.db}"

    async def run() -> int:
        engine = make_engine(url)
        try:
            async with make_session_factory(engine)() as s:
                n = await service.expire_due(s)
                await s.commit()
            async with make_session_factory(engine)() as s:
                again = await service.expire_due(s)
                await s.commit()
            return n * 10 + again
        finally:
            await engine.dispose()

    assert asyncio.run(run()) == 10
    assert _status(c, e, oid) == "expired"
    assert _events(c) == ["offer.sent", "offer.expired"]
    assert c.post(f"/offers/{oid}/accept", headers=ch).json()["code"] == "invalid_transition"


def test_foreign_offer_is_404(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    e2 = _employer(c, "e2@x.ru", name="Other")
    ch2, _, _ = _candidate(c, "c2@x.ru", 2)
    ghost = str(uuid.uuid4())
    for h, oid_ in ((e2, oid), (ch2, oid), (e, ghost), (ch, ghost)):
        assert c.get(f"/offers/{oid_}", headers=h).status_code == 404
    assert c.post(f"/offers/{oid}/withdraw", headers=e2).status_code == 404
    assert (
        c.post(f"/offers/{oid}/status", json={"status": "interview"}, headers=e2).status_code == 404
    )
    assert c.post(f"/offers/{oid}/accept", headers=ch2).status_code == 404
    d = c.post(f"/offers/{oid}/decline", json={"reason": "other"}, headers=ch2)
    assert d.status_code == 404 and d.json()["code"] == "offer_not_found"
    assert c.get("/offers", headers=e2).json() == []
    assert c.get("/candidates/me/offers", headers=ch2).json() == []
    assert _status(c, e, oid) == "sent"  # чужие попытки ничего не изменили
    assert c.get("/offers").status_code == 401


def test_role_checks(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    assert c.get("/offers", headers=ch).status_code == 403
    assert c.get("/candidates/me/offers", headers=e).status_code == 403
    assert c.post(f"/offers/{oid}/accept", headers=e).status_code == 403
    assert c.post(f"/offers/{oid}/withdraw", headers=ch).status_code == 403


def test_lists_and_card_offers_from_you(world):
    c, e, vid, ch, pid, uid = world
    vid2 = _vacancy(c, e)
    o1 = _offer(c, e, vid, pid).json()["id"]
    o2 = _offer(c, e, vid2, pid).json()["id"]
    c.post(f"/offers/{o1}/accept", headers=ch)
    assert {o["id"] for o in c.get("/offers", headers=e).json()} == {o1, o2}
    assert [o["id"] for o in c.get(f"/offers?vacancy_id={vid2}", headers=e).json()] == [o2]
    assert [o["id"] for o in c.get("/offers?status=accepted", headers=e).json()] == [o1]
    mine = c.get("/candidates/me/offers", headers=ch).json()
    assert {o["id"] for o in mine} == {o1, o2} and "candidate" not in mine[0]
    assert c.get("/candidates/me/offers", headers=ch).json()[0]["status"] in {"sent", "accepted"}
    card = c.get(f"/candidates/{pid}/card", headers=e).json()
    assert {(o["id"], o["status"]) for o in card["offers_from_you"]} == {
        (o1, "accepted"), (o2, "sent")}  # fmt: skip
    other = _employer(c, "o@x.ru", name="Other")
    assert c.get(f"/candidates/{pid}/card", headers=other).json()["offers_from_you"] == []
