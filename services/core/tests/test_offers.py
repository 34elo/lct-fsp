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
    body = {"consents": [{"type": "pd_processing", "granted": True},
                         {"type": "profile_publication", "granted": True}]}  # fmt: skip
    assert c.put("/me/consents", json=body, headers=h).status_code == 200
    assert c.get("/candidates/me/profile", headers=h).status_code == 200
    (uid,) = _db(c, "select user_id from candidates order by rowid desc limit 1")[0]
    cols = {"primary_role": "backend", "grade": "middle", "pseudo_id": f"pid{n:04d}"} | kw
    sets = ", ".join(f"{k}=?" for k in cols)
    _db(c, f"update candidates set {sets} where user_id=?", *cols.values(), uid)
    _db(
        c,
        "insert into grades (candidate_id, profession, grade, theta, band_position,"
        " theta_by_type, integrity, needs_confirmation, low_confidence, source, confirmed_at,"
        " valid_until, next_change_at) values (?,?,?,0.5,0.5,'{}',1.0,0,0,'seed',"
        "'2026-01-01 00:00:00','2999-01-01 00:00:00','2026-01-01 00:00:00')",
        uid,
        "backend",
        "middle",
    )  # грейд из теста: без него карточки нет (E23-1)
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


# --- E8-2: контакты, переписка, жалобы -------------------------------------------------


def test_contacts_revealed_only_after_accept(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    r = c.get(f"/offers/{oid}/contacts", headers=e)
    assert r.status_code == 409 and r.json()["code"] == "contacts_not_revealed"
    assert _db(c, "select count(*) from contact_reveals") == [(0,)]
    assert "contacts" not in json.dumps(c.get(f"/offers/{oid}", headers=e).json()) or (
        c.get(f"/offers/{oid}", headers=e).json()["contacts"] is None
    )
    c.post(f"/offers/{oid}/decline", json={"reason": "other"}, headers=ch)
    assert c.get(f"/offers/{oid}/contacts", headers=e).status_code == 409
    assert _db(c, "select count(*) from contact_reveals") == [(0,)]


def test_accept_creates_reveal_and_contacts(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    assert c.post(f"/offers/{oid}/accept", headers=ch).status_code == 200
    c.post(f"/offers/{oid}/accept", headers=ch)  # повтор: строка одна
    assert _db(c, "select count(*) from contact_reveals") == [(1,)]
    r = c.get(f"/offers/{oid}/contacts", headers=e)
    assert r.status_code == 200 and r.json()["email"] == "c@x.ru" and r.json()["name"]
    full = c.get(f"/offers/{oid}", headers=e).json()
    assert full["contacts"]["email"] == "c@x.ru"
    assert c.get("/offers", headers=e).json()[0]["contacts"] is None  # в списке контактов нет
    c.post(f"/offers/{oid}/status", json={"status": "interview"}, headers=e)
    assert c.get(f"/offers/{oid}/contacts", headers=e).status_code == 200


def test_contacts_permissions(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    c.post(f"/offers/{oid}/accept", headers=ch)
    other = _employer(c, "o@x.ru", name="Other", inn="7736050003")
    assert c.get(f"/offers/{oid}/contacts", headers=other).status_code == 404
    assert c.get(f"/offers/{oid}/contacts", headers=ch).status_code == 403
    ghost = str(uuid.uuid4())
    assert c.get(f"/offers/{ghost}/contacts", headers=e).status_code == 404


def test_messages_flow_and_privacy(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    r = c.post(f"/offers/{oid}/messages", json={"text": "  Вопрос по стеку  "}, headers=ch)
    assert r.status_code == 201 and r.json()["author_side"] == "candidate"
    assert r.json()["text"] == "Вопрос по стеку"
    assert c.post(f"/offers/{oid}/messages", json={"text": "Ответ"}, headers=e).status_code == 201
    for h in (e, ch):
        msgs = c.get(f"/offers/{oid}/messages", headers=h).json()
        assert [m["author_side"] for m in msgs] == ["candidate", "company"]
        assert "author_user_id" not in msgs[0]
    ev = _db(c, "select payload from outbox where type='offer.message'")
    assert len(ev) == 2
    assert c.post(f"/offers/{oid}/messages", json={"text": "  "}, headers=e).status_code == 422
    other = _employer(c, "o@x.ru", name="Other", inn="7736050003")
    assert c.get(f"/offers/{oid}/messages", headers=other).status_code == 404
    assert c.post(f"/offers/{oid}/messages", json={"text": "x"}, headers=other).status_code == 404
    ch2, *_ = _candidate(c, "c2@x.ru", 2)
    assert c.get(f"/offers/{oid}/messages", headers=ch2).status_code == 404
    assert c.post(f"/offers/{oid}/messages", json={"text": "x"}, headers=ch2).status_code == 404


def test_messages_awaiting_and_closed(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    c.post(f"/offers/{oid}/accept", headers=ch)
    c.post(f"/offers/{oid}/messages", json={"text": "Привет"}, headers=ch)
    assert c.get(f"/offers/{oid}", headers=e).json()["awaiting_reply_from"] == "company"
    c.post(f"/offers/{oid}/messages", json={"text": "Здравствуйте"}, headers=e)
    assert c.get(f"/offers/{oid}", headers=e).json()["awaiting_reply_from"] == "candidate"
    c.post(f"/offers/{oid}/status", json={"status": "not_hired"}, headers=e)
    r = c.post(f"/offers/{oid}/messages", json={"text": "Ещё"}, headers=ch)
    assert r.status_code == 409 and r.json()["code"] == "offer_closed"
    assert len(c.get(f"/offers/{oid}/messages", headers=ch).json()) == 2  # история читается


def test_messages_closed_for_declined_and_expired(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    _db(c, "update offers set expires_at=? where id=?", _past(hours=1), oid.replace("-", ""))
    r = c.post(f"/offers/{oid}/messages", json={"text": "Поздно"}, headers=e)
    assert r.status_code == 409 and r.json()["code"] == "offer_expired"
    c2 = _offer(c, e, _vacancy(c, e), pid).json()["id"]
    c.post(f"/offers/{c2}/decline", json={"reason": "other"}, headers=ch)
    r = c.post(f"/offers/{c2}/messages", json={"text": "?"}, headers=e)
    assert r.status_code == 409 and r.json()["code"] == "offer_closed"


def test_messages_rate_limit(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    for _ in range(service.MESSAGES_PER_HOUR):
        assert c.post(f"/offers/{oid}/messages", json={"text": "a"}, headers=ch).status_code == 201
    r = c.post(f"/offers/{oid}/messages", json={"text": "a"}, headers=ch)
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_complaint(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    body = {"reason": "spam", "comment": "Рассылка"}
    r = c.post(f"/offers/{oid}/complaint", json=body, headers=ch)
    assert r.status_code == 201 and r.json()["status"] == "open"
    again = c.post(f"/offers/{oid}/complaint", json=body, headers=ch)
    assert again.status_code == 409 and again.json()["code"] == "complaint_exists"
    assert c.post(f"/offers/{oid}/complaint", json={"reason": "zzz"}, headers=ch).status_code == 422
    assert c.post(f"/offers/{oid}/complaint", json=body, headers=e).status_code == 403
    ch2, *_ = _candidate(c, "c2@x.ru", 2)
    assert c.post(f"/offers/{oid}/complaint", json=body, headers=ch2).status_code == 404
    assert _db(c, "select reason, status from complaints") == [("spam", "open")]


def test_admin_complaints(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    c.post(f"/offers/{oid}/complaint", json={"reason": "spam", "comment": "Рассылка"}, headers=ch)
    c.post("/auth/register", json={"email": "root@x.io", "password": PWD, "role": "candidate"})
    _db(c, "update users set role='fsp_admin' where email='root@x.io'")
    tok = c.post("/auth/login", json={"email": "root@x.io", "password": PWD}).json()
    adm = {"Authorization": f"Bearer {tok['access_token']}"}
    assert c.get("/admin/complaints", headers=ch).status_code == 403
    assert c.get("/admin/complaints", headers=e).status_code == 403
    assert c.get("/admin/complaints", headers={}).status_code == 401
    assert c.get("/admin/complaints?status=zzz", headers=adm).status_code == 422
    rows = c.get("/admin/complaints?status=open", headers=adm).json()
    assert len(rows) == 1 and rows[0]["reason"] == "spam" and rows[0]["offer_id"] == oid
    assert "reporter" not in json.dumps(rows) and "user_id" not in json.dumps(rows)
    cid = rows[0]["id"]
    url = f"/admin/complaints/{cid}/resolve"
    assert c.post(url, headers=ch).status_code == 403
    assert c.post(f"/admin/complaints/{uuid.uuid4()}/resolve", headers=adm).status_code == 404
    assert c.post(url, json={"decision": "x"}, headers=adm).status_code == 422
    r = c.post(url, headers=adm)
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    assert c.post(url, json={"decision": "resolved"}, headers=adm).json()["status"] == "resolved"
    r = c.post(url, json={"decision": "dismissed"}, headers=adm)
    assert r.status_code == 409 and r.json()["code"] == "invalid_status"
    assert c.get("/admin/complaints?status=open", headers=adm).json() == []
    assert len(c.get("/admin/complaints", headers=adm).json()) == 1


def test_salary_hint(world):
    c, e, vid, ch, pid, uid = world
    body = {
        "vacancy_id": vid,
        "candidate_pseudo_id": pid,
        "salary_from": 200000,
        "salary_to": 340000,
    }
    r = c.post("/offers/salary-hint", json=body, headers=e)
    assert r.status_code == 200, r.text
    h = r.json()
    assert h["candidate_min"] == 350000 and h["below_candidate_min"] is True
    assert h["range_too_wide"] is True and 0 < h["p_accept"] < 1
    assert h["acceptance_hint"] in ("low", "medium", "high") and h["message"]
    better = c.post("/offers/salary-hint", json=body | {"salary_to": 450000}, headers=e).json()
    assert better["p_accept"] > h["p_accept"] and better["below_candidate_min"] is False
    bad = c.post("/offers/salary-hint", json=body | {"salary_from": None}, headers=e)
    assert bad.status_code == 422 and bad.json()["code"] == "salary_range_required"
    assert c.post("/offers/salary-hint", json=body, headers=ch).status_code == 403
    miss = c.post("/offers/salary-hint", json=body | {"candidate_pseudo_id": "nope"}, headers=e)
    assert miss.status_code == 404
    other = _employer(c, "o2@x.ru", name="Other", inn="7736050003")
    assert c.post("/offers/salary-hint", json=body, headers=other).status_code == 404


def test_salary_hint_range_too_wide_threshold(world):
    """range_too_wide в salary-hint respects threshold: salary_to / salary_from > 1.6."""
    c, e, vid, ch, pid, uid = world
    base = {
        "vacancy_id": vid,
        "candidate_pseudo_id": pid,
        "salary_from": 200000,
    }
    # 320k / 200k = 1.6, not > 1.6, so warning should be False
    h1 = c.post("/offers/salary-hint", json=base | {"salary_to": 320000}, headers=e).json()
    assert h1["range_too_wide"] is False
    # 321k / 200k ≈ 1.605 > 1.6, so warning should be True
    h2 = c.post("/offers/salary-hint", json=base | {"salary_to": 321000}, headers=e).json()
    assert h2["range_too_wide"] is True


def test_offer_events_timeline(world):
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    c.post(f"/offers/{oid}/accept", headers=ch)
    for who in (e, ch):
        ev = c.get(f"/offers/{oid}/events", headers=who).json()
        assert [x["to_status"] for x in ev] == ["sent", "accepted"]
        assert [x["actor"] for x in ev] == ["company", "candidate"]
        assert "payload" not in ev[0]
    other = _employer(c, "o3@x.ru", name="Other", inn="7736050003")
    assert c.get(f"/offers/{oid}/events", headers=other).status_code == 404


# --- E20-2: приглашение без вакансии (ADR-022) ---------------------------------------------


def _invite(c, h, pid, key=None, **over):
    body = {"candidate_pseudo_id": pid, "salary_from": 250000, "salary_to": 320000,
            "title": "Python-разработчик в R&D", "description": "Пилотный проект",
            "contact_method": "telegram"} | over  # fmt: skip
    body = {k: v for k, v in body.items() if v is not None}
    return c.post("/offers", json=body, headers={**h, "Idempotency-Key": key or uuid.uuid4().hex})


def test_invite_without_vacancy_created_and_accepted(world):
    c, e, vid, ch, pid, uid = world
    r = _invite(c, e, pid)
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["vacancy"] is None and o["initiator"] == "employer"
    assert (o["title"], o["description"], o["contact_method"]) == (
        "Python-разработчик в R&D", "Пилотный проект", "telegram",
    )  # fmt: skip
    assert o["match_snapshot"] is None and o["candidate"]["pseudo_id"] == pid
    mine = c.get("/candidates/me/offers", headers=ch).json()
    assert [x["id"] for x in mine] == [o["id"]] and mine[0]["vacancy"] is None
    assert mine[0]["company"]["name"] == "Acme Labs"
    assert c.post(f"/offers/{o['id']}/accept", headers=ch).status_code == 200
    assert _status(c, e, o["id"]) == "accepted"
    assert c.get(f"/offers/{o['id']}/contacts", headers=e).status_code == 200
    assert _events(c) == ["offer.sent", "offer.accepted"]
    rows = _db(c, "select payload from outbox where type like 'offer.%'")
    envs = [json.loads(p) for (p,) in rows]
    assert {env["schema_version"] for env in envs} == {2}
    assert all(env["payload"]["vacancy_id"] is None for env in envs)
    assert all(env["payload"]["initiator"] == "employer" for env in envs)


def test_invite_with_vacancy_keeps_vacancy_and_v2_event(world):
    c, e, vid, ch, pid, uid = world
    o = _offer(c, e, vid, pid).json()
    assert o["vacancy"]["id"] == vid and o["title"] == "Backend" and o["initiator"] == "employer"
    (raw,) = _db(c, "select payload from outbox where type='offer.sent'")[0]
    env = json.loads(raw)
    assert env["schema_version"] == 2 and env["payload"]["vacancy_id"] == vid


def test_invite_requires_salary_and_title(world):
    c, e, vid, ch, pid, uid = world
    for over in ({"salary_from": None}, {"salary_to": None}):
        r = _invite(c, e, pid, **over)
        assert (r.status_code, r.json()["code"]) == (422, "salary_range_required"), over
    r = _invite(c, e, pid, title=None)
    assert (r.status_code, r.json()["code"]) == (422, "title_required")
    r = _invite(c, e, pid, title="   ")
    assert (r.status_code, r.json()["code"]) == (422, "title_required")
    r = _invite(c, e, pid, contact_method="pigeon")
    assert r.status_code == 422
    assert _db(c, "select count(*) from offers") == [(0,)]
    assert _events(c) == []


def test_invite_idempotent_and_no_duplicates(world):
    c, e, vid, ch, pid, uid = world
    r1 = _invite(c, e, pid, key="inv-1")
    r2 = _invite(c, e, pid, key="inv-1")  # повтор того же запроса
    assert r2.status_code == 201 and r2.headers.get("Idempotent-Replay") == "true"
    assert r1.json()["id"] == r2.json()["id"]
    # тот же ключ, но с вакансией — другой запрос
    r = _offer(c, e, vid, pid, key="inv-1")
    assert (r.status_code, r.json()["code"]) == (409, "idempotency_key_reused")
    # второе открытое приглашение без вакансии тому же кандидату — 409
    r = _invite(c, e, pid, title="Другое")
    assert (r.status_code, r.json()["code"]) == (409, "offer_exists")
    assert _db(c, "select count(*) from offers") == [(1,)]
    assert _events(c) == ["offer.sent"]
    # после отказа можно пригласить снова; оффер по вакансии не мешает
    c.post(f"/offers/{r1.json()['id']}/decline", json={"reason": "other"}, headers=ch)
    assert _invite(c, e, pid).status_code == 201
    assert _offer(c, e, vid, pid).status_code == 201


def test_invite_foreign_is_404(world):
    c, e, vid, ch, pid, uid = world
    oid = _invite(c, e, pid).json()["id"]
    e2 = _employer(c, "e2@x.ru", name="Other", inn="7736050003")
    ch2, _, _ = _candidate(c, "c2@x.ru", 2)
    assert c.get(f"/offers/{oid}", headers=e2).status_code == 404
    assert c.get(f"/offers/{oid}", headers=ch2).status_code == 404
    assert c.post(f"/offers/{oid}/accept", headers=ch2).status_code == 404
    assert c.post(f"/offers/{oid}/withdraw", headers=e2).status_code == 404
    # чужая вакансия в приглашении — 404
    r = _offer(c, e2, vid, pid)
    assert r.status_code == 404
    assert _invite(c, ch, pid).status_code == 403  # кандидат не приглашает
    assert _status(c, e, oid) == "sent"


def test_invite_requires_verified_email_when_enabled(world, monkeypatch):
    c, e, vid, ch, pid, uid = world
    monkeypatch.setenv("EMAIL_VERIFICATION_REQUIRED", "true")
    r = _invite(c, e, pid)
    assert (r.status_code, r.json()["code"]) == (403, "email_not_verified")
    _db(c, "update users set email_verified_at=? where email='e@x.ru'", _past(minutes=1))
    assert _invite(c, e, pid).status_code == 201


# --- отклики кандидатов (E20-3, ADR-022) --------------------------------------------------


def _set_status(c, h, oid, status):
    return c.post(f"/offers/{oid}/status", json={"status": status}, headers=h).status_code


def test_public_vacancies_list(world):
    c, e, vid, ch, pid, uid = world
    draft = _vacancy(c, e, publish=False)
    r = c.get("/vacancies/public")  # без авторизации
    assert r.status_code == 200
    ids = [v["id"] for v in r.json()]
    assert vid in ids and draft not in ids
    v = r.json()[0]
    assert v["company"]["name"] == "Acme Labs" and "version" not in v
    assert c.get("/vacancies/public", params={"role": "frontend"}).json() == []
    assert c.get("/vacancies/public", params={"q": "back"}).json() != []


def test_apply_flow_and_statuses_visible_to_both(world):
    c, e, vid, ch, pid, uid = world
    r = c.post(f"/vacancies/{vid}/apply", json={"message": "Беру!"}, headers=ch)
    assert r.status_code == 201, r.text
    oid = r.json()["id"]
    assert r.json()["initiator"] == "candidate" and r.json()["status"] == "sent"
    assert (r.json()["salary_from"], r.json()["salary_to"]) == (200000, 300000)
    assert r.json()["awaiting_reply_from"] == "company"
    assert _events(c) == ["offer.sent"]
    # контакты раскрыты сразу
    assert _db(c, "select count(*) from contact_reveals") == [(1,)]
    # у кандидата: в откликах, а не среди приглашений
    assert [o["id"] for o in c.get("/candidates/me/applications", headers=ch).json()] == [oid]
    assert c.get("/candidates/me/offers?initiator=employer", headers=ch).json() == []
    # у компании: фильтр по инициатору, контакты, статус viewed после открытия
    lst = c.get("/offers", params={"initiator": "candidate"}, headers=e).json()
    assert [o["id"] for o in lst] == [oid] and lst[0]["status"] == "sent"
    full = c.get(f"/offers/{oid}", headers=e).json()
    assert full["status"] == "viewed" and full["contacts"]["email"] == "c@x.ru"
    assert c.get(f"/offers/{oid}/contacts", headers=e).status_code == 200
    assert c.get(f"/offers/{oid}", headers=ch).json()["status"] == "viewed"  # видно обеим
    assert c.get(f"/offers/{oid}", headers=ch).json()["status"] == "viewed"
    # компания продвигает отклик
    assert _set_status(c, e, oid, "interview") == 200
    assert _set_status(c, e, oid, "hired") == 200
    assert c.get("/candidates/me/applications", headers=ch).json()[0]["status"] == "hired"


def test_apply_twice_is_409(world):
    c, e, vid, ch, pid, uid = world
    assert c.post(f"/vacancies/{vid}/apply", headers=ch).status_code == 201
    r = c.post(f"/vacancies/{vid}/apply", headers=ch)
    assert r.status_code == 409 and r.json()["code"] == "already_applied"
    assert _db(c, "select count(*) from offers") == [(1,)]
    assert _events(c) == ["offer.sent"]


def test_apply_after_invitation_is_409(world):
    c, e, vid, ch, pid, uid = world
    assert _offer(c, e, vid, pid).status_code == 201
    assert c.post(f"/vacancies/{vid}/apply", headers=ch).status_code == 409


def test_apply_checks(world):
    c, e, vid, ch, pid, uid = world
    draft = _vacancy(c, e, publish=False)
    assert c.post(f"/vacancies/{draft}/apply", headers=ch).status_code == 404
    assert c.post(f"/vacancies/{uuid.uuid4()}/apply", headers=ch).status_code == 404
    assert c.post(f"/vacancies/{vid}/apply", headers=e).status_code == 403
    assert c.post(f"/vacancies/{vid}/apply").status_code == 401
    (company_id,) = _db(c, "select company_id from vacancies where id=?", vid.replace("-", ""))[0]
    cid = str(uuid.UUID(company_id))
    assert (
        c.put("/candidates/me/stoplist", json={"company_ids": [cid]}, headers=ch).status_code == 200
    )
    r = c.post(f"/vacancies/{vid}/apply", headers=ch)
    assert r.status_code == 409 and r.json()["code"] == "company_in_stoplist"


def test_foreign_application_is_404(world):
    c, e, vid, ch, pid, uid = world
    oid = c.post(f"/vacancies/{vid}/apply", headers=ch).json()["id"]
    e2 = _employer(c, "e2@x.ru", name="Other", inn="7736050003")
    ch2, _, _ = _candidate(c, "c2@x.ru", 2)
    for h in (e2, ch2):
        assert c.get(f"/offers/{oid}", headers=h).status_code == 404
    assert c.get(f"/offers/{oid}/contacts", headers=e2).status_code == 404
    assert c.post(f"/candidates/me/applications/{oid}/withdraw", headers=ch2).status_code == 404
    assert _set_status(c, e2, oid, "interview") == 404
    assert c.get("/offers?initiator=candidate", headers=e2).json() == []
    assert c.get("/candidates/me/applications", headers=ch2).json() == []
    assert _db(c, "select status from offers") == [("sent",)]  # чужие попытки ничего не изменили


def test_application_state_rules(world):
    c, e, vid, ch, pid, uid = world
    oid = c.post(f"/vacancies/{vid}/apply", headers=ch).json()["id"]
    assert c.post(f"/offers/{oid}/accept", headers=ch).status_code == 409  # не приглашение
    d = c.post(f"/offers/{oid}/decline", json={"reason": "other"}, headers=ch)
    assert d.status_code == 409
    assert c.post(f"/offers/{oid}/withdraw", headers=e).status_code == 409  # компания не отзывает
    # приглашение нельзя отозвать как отклик
    oid2 = _offer(c, e, _vacancy(c, e), pid).json()["id"]
    assert c.post(f"/candidates/me/applications/{oid2}/withdraw", headers=ch).status_code == 404
    # кандидат отзывает отклик, дальше менять нельзя
    r = c.post(f"/candidates/me/applications/{oid}/withdraw", headers=ch)
    assert r.status_code == 200 and r.json()["status"] == "withdrawn"
    assert c.post(f"/candidates/me/applications/{oid}/withdraw", headers=ch).status_code == 409
    assert _set_status(c, e, oid, "interview") == 409


def test_applications_do_not_count_toward_invitation_limits(world, monkeypatch):
    c, e, vid, ch, pid, uid = world
    monkeypatch.setattr(offers_router, "_LIMITS", service.OfferLimits(1, 1, 7))
    assert c.post(f"/vacancies/{vid}/apply", headers=ch).status_code == 201
    v2 = _vacancy(c, e)
    assert _offer(c, e, v2, pid).status_code == 201  # лимит приглашений не съеден откликом


def test_application_notifies_company_not_candidate(world):
    c, e, vid, ch, pid, uid = world
    c.post(f"/vacancies/{vid}/apply", headers=ch)
    rows = _db(c, "select type from notifications order by rowid")
    assert not rows or all(t[0] != "offer_new" for t in rows)


def test_salary_basis_default_inherit_and_override(world):
    """E32-5a: вилка «до НДФЛ» по умолчанию, берётся из вакансии, можно задать в приглашении."""
    c, e, vid, ch, pid, uid = world
    assert c.get(f"/vacancies/{vid}", headers=e).json()["salary_basis"] == "gross"
    v2 = c.post("/vacancies", headers=e, json={
        "title": "Net", "role": "backend", "grade_min": "middle", "grade_max": "senior",
        "formats": ["remote"], "employment_type": "full", "salary_from": 100000,
        "salary_to": 150000, "salary_basis": "net", "skills": [{"slug": "python"}],
    }).json()  # fmt: skip
    assert v2["salary_basis"] == "net"
    c.post(f"/vacancies/{v2['id']}/publish", headers=e)
    o1 = _offer(c, e, v2["id"], pid).json()
    assert o1["salary_basis"] == "net"
    assert c.get(f"/offers/{o1['id']}", headers=ch).json()["salary_basis"] == "net"
    ch2, pid2, _ = _candidate(c, "c2@x.ru", 2)
    o2 = _offer(c, e, vid, pid2, salary_basis="net").json()
    assert o2["salary_basis"] == "net"
    _, pid3, _ = _candidate(c, "c3@x.ru", 3)
    assert _offer(c, e, vid, pid3).json()["salary_basis"] == "gross"
    assert _offer(c, e, vid, pid3, salary_basis="bogus").status_code == 422


def test_revoke_contacts(world):
    """E32-5a: отзыв скрывает контакты у компании; чужой оффер и роль — проверки прав."""
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    r = c.post(f"/offers/{oid}/contacts/revoke", headers=ch)
    assert r.status_code == 409 and r.json()["code"] == "contacts_not_revealed"
    c.post(f"/offers/{oid}/accept", headers=ch)
    assert c.get(f"/offers/{oid}/contacts", headers=e).status_code == 200
    assert c.post(f"/offers/{oid}/contacts/revoke", headers=e).status_code == 403
    other_ch, _, _ = _candidate(c, "c9@x.ru", 9)
    assert c.post(f"/offers/{oid}/contacts/revoke", headers=other_ch).status_code == 404
    r = c.post(f"/offers/{oid}/contacts/revoke", headers=ch)
    assert r.status_code == 200 and r.json()["contacts_revoked_at"]
    assert c.post(f"/offers/{oid}/contacts/revoke", headers=ch).status_code == 200  # повтор
    r = c.get(f"/offers/{oid}/contacts", headers=e)
    assert r.status_code == 409 and r.json()["code"] == "contacts_revoked"
    assert c.get(f"/offers/{oid}", headers=e).json()["contacts"] is None
    assert _db(c, "select count(*) from contact_reveals") == [(1,)]


def test_verified_badge_is_voluntary(world):
    """E32-5a: компания сама решает, показывать ли метку «проверена» кандидатам."""
    c, e, vid, ch, pid, uid = world
    oid = _offer(c, e, vid, pid).json()["id"]
    assert c.get(f"/offers/{oid}", headers=ch).json()["company"]["verified"] is True
    r = c.patch("/companies/me", json={"show_verified_badge": False}, headers=e)
    assert r.status_code == 200 and r.json()["show_verified_badge"] is False
    assert c.get(f"/offers/{oid}", headers=ch).json()["company"]["verified"] is False
    pub = c.get("/vacancies/public").json()
    assert pub[0]["company"]["verified"] is False and pub[0]["salary_basis"] == "gross"
