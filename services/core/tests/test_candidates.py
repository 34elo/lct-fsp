import json
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import fakeredis
import pytest
from app.candidates import service
from app.candidates.models import Candidate
from app.config import Settings
from app.identity.models import utcnow
from app.main import build_app
from core_helpers import upgrade_head
from fastapi.testclient import TestClient
from fsp_platform.ratelimit import RateLimiter

CORE = Path(__file__).resolve().parents[1]
PWD = "correct-horse-battery"


@pytest.fixture
def c(tmp_path):
    db = tmp_path / "c.db"
    upgrade_head(f"sqlite+aiosqlite:///{db}")
    app = build_app(Settings(database_url=f"sqlite+aiosqlite:///{db}", ui_bus_enabled=False))
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        client.app_ = app
        yield client


def _user(c, email, role="candidate", consent=True):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": role})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if consent:
        body = {"consents": [{"type": "pd_processing", "granted": True}]}
        assert c.put("/me/consents", json=body, headers=h).status_code == 200
    return h


def test_pseudo_id_hmac():
    uid = uuid.uuid4()
    a = service.make_pseudo_id("s1", uid)
    assert len(a) == 12 and a != uid.hex[:12]
    assert a == service.make_pseudo_id("s1", uid)
    assert a != service.make_pseudo_id("s2", uid)
    assert a != service.make_pseudo_id("s1", uuid.uuid4())


def test_profile_lazy_create_stable(c):
    h = _user(c, "a@x.io")
    p1 = c.get("/candidates/me/profile", headers=h).json()
    p2 = c.get("/candidates/me/profile", headers=h).json()
    assert p1["pseudonym"] == p2["pseudonym"] and p1["pseudonym"].startswith("Candidate #")
    assert p1["search_status"] == "open" and p1["preferences"]["formats"] == []
    assert p1["visibility"] == {  # ADR-027: ФИО скрыто, опыт/компании/ФСП/регион видны
        "full_name": False,
        "companies": True,
        "fsp": True,
        "region": True,
        "education": False,
        "repos": False,
        "public_profile": False,
        "teams": True,
    }
    assert "pseudo_id" not in p1 and "user_id" not in p1


def test_roles_and_auth(c):
    assert c.get("/candidates/me/profile").status_code == 401
    e = _user(c, "e@x.io", role="employer")
    assert c.get("/candidates/me/profile", headers=e).status_code == 403


def test_preferences_patch_and_active_window(c):
    h = _user(c, "a@x.io")
    r = c.patch(
        "/candidates/me/preferences",
        json={
            "salary_min": 200000,
            "formats": ["remote", "hybrid", "remote"],
            "employment_types": ["full"],
            "city": "Казань",
            "relocation": True,
            "search_status": "active",
        },
        headers=h,
    )
    assert r.status_code == 200
    j = r.json()
    assert j["search_status"] == "active" and j["active_until"]
    assert j["preferences"] == {
        "salary_min": 200000,
        "formats": ["hybrid", "remote"],
        "employment_types": ["full"],
        "city": "Казань",
        "relocation": True,
    }
    # частичное обновление не трогает остальное; null очищает
    j = c.patch("/candidates/me/preferences", json={"salary_min": None}, headers=h).json()
    assert j["preferences"]["salary_min"] is None and j["preferences"]["city"] == "Казань"
    assert j["search_status"] == "active"
    j = c.patch("/candidates/me/preferences", json={"search_status": "dnd"}, headers=h).json()
    assert j["search_status"] == "dnd" and j["active_until"] is None
    bad = c.patch("/candidates/me/preferences", json={"formats": ["moon"]}, headers=h)
    assert bad.status_code == 422
    assert (
        c.patch("/candidates/me/preferences", json={"salary_min": -1}, headers=h).status_code == 422
    )


def test_active_expires_to_open():
    cand = Candidate(search_status="active", active_until=utcnow() - timedelta(seconds=1))
    assert service.effective_status(cand) == "open"
    cand.active_until = utcnow() + timedelta(days=1)
    assert service.effective_status(cand) == "active"


def test_visibility_and_public_consent(c):
    h = _user(c, "a@x.io")
    j = c.patch("/candidates/me/visibility", json={"companies": True}, headers=h).json()
    assert j["visibility"]["companies"] is True and j["visibility"]["teams"] is True
    r = c.patch("/candidates/me/visibility", json={"public_profile": True}, headers=h)
    assert r.status_code == 403 and r.json()["code"] == "consent_required"
    c.put(
        "/me/consents",
        json={"consents": [{"type": "public_profile", "granted": True}]},
        headers=h,
    )
    j = c.patch("/candidates/me/visibility", json={"public_profile": True}, headers=h).json()
    assert j["visibility"]["public_profile"] is True and j["visibility"]["companies"] is True


def _events(c, type_):
    import sqlite3

    c.db_path = Path(c.app_.state.settings.database_url.split("///")[1])
    with sqlite3.connect(c.db_path) as con:
        rows = con.execute("select payload from outbox where type=? order by id", (type_,))
        out = [json.loads(r[0]) for r in rows]
    return [d.get("payload", d) for d in out]


def test_visibility_privacy_switches_saved_and_evented(c):
    """E36-4: ФИО/ФСП/регион/компании сохраняются, событие только об изменившемся."""
    h = _user(c, "a@x.io")
    j = c.patch(
        "/candidates/me/visibility", json={"full_name": True, "region": False}, headers=h
    ).json()
    assert j["visibility"]["full_name"] is True and j["visibility"]["region"] is False
    assert j["visibility"]["fsp"] is True and j["visibility"]["companies"] is True
    # повтор тех же значений события не создаёт
    c.patch("/candidates/me/visibility", json={"full_name": True}, headers=h)
    j = c.patch("/candidates/me/visibility", json={"fsp": False, "companies": False}, headers=h)
    assert j.json()["visibility"]["full_name"] is True  # прошлые значения сохранились
    p = c.get("/candidates/me/profile", headers=h).json()["visibility"]
    assert (p["full_name"], p["region"], p["fsp"], p["companies"]) == (True, False, False, False)
    evs = _events(c, "candidate.visibility.changed")
    assert [e["changed"] for e in evs] == [
        {"full_name": True, "region": False},
        {"companies": False, "fsp": False},
    ]
    assert all("contacts" not in e["visibility"] for e in evs)


def test_visibility_rejects_unknown_keys_and_other_roles(c):
    h = _user(c, "a@x.io")
    assert (
        c.patch("/candidates/me/visibility", json={"contacts": True}, headers=h).status_code == 422
    )
    e = _user(c, "e@x.io", role="employer")
    assert c.patch("/candidates/me/visibility", json={"fsp": False}, headers=e).status_code == 403
    assert c.patch("/candidates/me/visibility", json={"fsp": False}).status_code == 401


def test_visibility_missing_keys_use_defaults(c):
    class _C:
        visibility = {"companies": False}

    v = service.visibility_of(_C())
    assert v["companies"] is False and v["region"] is True and v["fsp"] is True
    assert v["full_name"] is False and v["education"] is False


def test_stoplist_idempotent_and_isolated(c):
    h1, h2 = _user(c, "a@x.io"), _user(c, "b@x.io")
    ids = [str(uuid.uuid4()) for _ in range(2)]
    for _ in range(2):
        r = c.put("/candidates/me/stoplist", json={"company_ids": ids + ids[:1]}, headers=h1)
        assert r.status_code == 200 and sorted(r.json()["company_ids"]) == sorted(ids)
    assert (
        c.put("/candidates/me/stoplist", json={"company_ids": ["x"]}, headers=h1).status_code == 422
    )
    c.get("/candidates/me/profile", headers=h2)
    # чужой стоп-лист не виден и не меняется
    assert c.put("/candidates/me/stoplist", json={"company_ids": []}, headers=h2).json() == {
        "company_ids": []
    }
    assert sorted(
        c.put("/candidates/me/stoplist", json={"company_ids": ids}, headers=h1).json()[
            "company_ids"
        ]
    ) == sorted(ids)


def test_writes_need_pd_consent(c):
    h = _user(c, "a@x.io", consent=False)
    assert c.get("/candidates/me/profile", headers=h).status_code == 200
    r = c.patch("/candidates/me/preferences", json={"city": "X"}, headers=h)
    assert r.status_code == 403 and r.json()["code"] == "consent_required"


def test_distinct_pseudonyms_and_pseudo_ids(c):
    hs = [_user(c, f"u{i}@x.io") for i in range(5)]
    names = {c.get("/candidates/me/profile", headers=h).json()["pseudonym"] for h in hs}
    assert len(names) == 5


def _seed_graph(c, uid, h_slug="python"):
    """Рёбра графа и результаты пересчёта, как их оставляет `recompute_profile`."""
    import json
    import sqlite3

    sid, ev_id, fact = uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex
    with sqlite3.connect(c.db_path) as con:
        con.execute(
            "insert into skills (id, slug, name, kind, grp, status, source, support_candidates,"
            " support_vacancies, testable) values (?,?,?,?,?,?,?,0,0,0)",
            (sid, h_slug, "Python", "hard", "language", "active", "seed"),
        )
        con.execute(
            "insert into evidence (id, candidate_id, skill_id, source, strength, observed_at,"
            " fact_type, fact_id, details, verified, is_active) values (?,?,?,?,?,?,?,?,?,1,1)",
            (ev_id, uid, sid, "fsp", 0.9, "2026-01-10", "fsp_result", fact,
             json.dumps({"label": "Кубок ФСП, финал, 2 место из 120", "level": "national",
                        "place": 2, "participants": 120, "team_role": "captain"})),
        )  # fmt: skip
        con.execute(
            "insert into candidate_skills (candidate_id, skill_id, confidence, level, sources,"
            " top_evidence, claimed_only, derived) values (?,?,?,?,?,?,0,0)",
            (uid, sid, 0.8, 3, json.dumps(["fsp"]), json.dumps([ev_id])),
        )
        con.execute(
            "update candidates set primary_role=?, roles=?, primary_stack=?, grade=?,"
            " grade_score=?, grade_confidence=?, grade_breakdown=?, grade_next=?, team_signals=?"
            " where user_id=?",
            (
                "backend",
                json.dumps([{"role": "backend", "weight": 0.9}]),
                json.dumps(["python"]),
                "junior_plus",
                4.5,
                0.5,
                json.dumps([{"signal": "experience", "value": 12, "points": 3.0,
                             "evidence_ids": []},
                            {"signal": "fsp_achievement", "value": "national_finalist",
                             "points": 2.0, "evidence_ids": [ev_id]}]),
                json.dumps({"grade": "middle", "points_needed": 1.5,
                            "hints": [{"signal": "tests", "max_gain": 3, "text": "Пройдите тест"}],
                            }),
                json.dumps({
                    "leadership": {"value": 0.7, "facts": [
                        {"kind": "captain", "fact_id": fact, "contribution": 0.7,
                         "level": "national", "place": 2, "year": 2026}]},
                    "growth": {"value": 0.1, "facts": []},
                }),
                uid,
            ),
        )  # fmt: skip
    return sid, ev_id


def _uid(c, h):
    me = c.get("/me", headers=h)
    assert me.status_code == 200, me.text
    return me.json()["id"].replace("-", "")


def test_profile_has_category_grade_skills_team_signals(c):
    h = _user(c, "a@x.io")
    c.get("/candidates/me/profile", headers=h)
    c.db_path = Path(c.app_.state.settings.database_url.split("///")[1])
    _seed_graph(c, _uid(c, h))
    p = c.get("/candidates/me/profile", headers=h).json()
    assert p["category"]["primary_role"] == "backend"
    assert p["category"]["primary_stack"] == ["python"]
    g = p["grade"]
    assert (g["grade"], g["preliminary"], g["confidence"]) == ("junior_plus", False, 0.5)
    assert [b["label"] for b in g["breakdown"]][:2] == [
        "Стаж",
        "Достижение на соревнованиях ФСП",
    ]
    assert g["next_grade"] == {"grade": "middle", "points_needed": 1.5, "hints": ["Пройдите тест"]}
    (s,) = p["skills"]
    assert s["skill"]["slug"] == "python" and s["level"] == 3 and s["sources"] == ["fsp"]
    assert s["top_evidence"][0]["title"] == "Кубок ФСП, финал, 2 место из 120"
    (a,) = p["fsp"]["achievements"]  # один факт — одно достижение
    assert (a["title"], a["level"], a["place"], a["of"], a["year"], a["team_role"]) == (
        "Кубок ФСП, финал, 2 место из 120",
        "national",
        2,
        120,
        2026,
        "captain",
    )
    assert p["fsp"]["verified"] is True and p["fsp"]["ranks"] == []
    (t,) = p["team_signals"]  # growth 0.1 < 0.3 не показываем
    assert (t["signal"], t["label"]) == ("leadership", "present" if t["value"] < 0.6 else "strong")
    assert t["facts"][0]["title"] == "Капитан команды, всероссийский уровень, 2 место, 2026"


def test_empty_profile_has_null_category_and_no_skills(c):
    h = _user(c, "a@x.io")
    p = c.get("/candidates/me/profile", headers=h).json()
    assert p["category"] is None and p["skills"] == [] and p["team_signals"] == []
    assert p["fsp"] is None
    assert p["grade"]["grade"] is None and p["grade"]["preliminary"] is True


def test_skill_evidence_by_slug_and_id_and_ownership(c):
    h = _user(c, "a@x.io")
    c.get("/candidates/me/profile", headers=h)
    c.db_path = Path(c.app_.state.settings.database_url.split("///")[1])
    sid, ev_id = _seed_graph(c, _uid(c, h))
    for ref in ("python", str(uuid.UUID(sid))):
        r = c.get(f"/candidates/me/skills/{ref}/evidence", headers=h)
        assert r.status_code == 200, r.text
        (e,) = r.json()
        assert e["id"] == str(uuid.UUID(ev_id)) and e["source"] == "fsp" and e["verified"]
        assert e["title"] == "Кубок ФСП, финал, 2 место из 120"
    # другой кандидат: навык есть в таксономии, но не его — 404
    other = _user(c, "b@x.io")
    r = c.get("/candidates/me/skills/python/evidence", headers=other)
    assert r.status_code == 404 and r.json()["code"] == "skill_not_found"
    assert c.get("/candidates/me/skills/nope/evidence", headers=h).status_code == 404
    assert c.get("/candidates/me/skills/python/evidence").status_code == 401
    e = _user(c, "e@x.io", role="employer")
    assert c.get("/candidates/me/skills/python/evidence", headers=e).status_code == 403


async def test_pseudonym_collision_retries(tmp_path, monkeypatch):
    """Коллизия 4-значного псевдонима (при сотнях кандидатов частая) решается повтором."""
    from app.identity.models import User
    from fsp_platform.db import make_engine, make_session_factory, session_scope

    url = f"sqlite+aiosqlite:///{tmp_path / 'p.db'}"
    subprocess.run(  # noqa: ASYNC221
        [sys.executable, "-m", "alembic", "-x", f"url={url}", "upgrade", "head"],
        cwd=CORE,
        check=True,
        capture_output=True,
    )
    factory = make_session_factory(make_engine(url))
    names = iter(["Candidate #1111", "Candidate #1111", "Candidate #2222"])
    monkeypatch.setattr(service, "make_pseudonym", lambda: next(names))
    async with session_scope(factory) as s:
        u1, u2 = uuid.uuid4(), uuid.uuid4()
        s.add_all(
            [
                User(id=u, email=f"{u.hex[:6]}@x.io", password_hash="x", role="candidate")
                for u in (u1, u2)
            ]
        )
        await s.flush()
        a = await service.get_or_create(s, u1, "secret")
        b = await service.get_or_create(s, u2, "secret")
        assert a.pseudonym == "Candidate #1111" and b.pseudonym == "Candidate #2222"


def test_category_explanation_and_dispute(c):
    h = _user(c, "a@x.io")
    c.get("/candidates/me/profile", headers=h)
    c.db_path = Path(c.app_.state.settings.database_url.split("///")[1])
    _seed_graph(c, _uid(c, h))
    r = c.get("/candidates/me/category", headers=h)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["grade"]["grade"] == "junior_plus" and j["grade"]["next_grade"]["hints"]
    assert j["dispute"] is None and isinstance(j["explanation"], list)

    body = {"claimed_role": "frontend", "claimed_grade": "middle", "comment": " Я фронтендер "}
    d = c.post("/candidates/me/category/dispute", json=body, headers=h)
    assert d.status_code == 201, d.text
    assert d.json()["status"] == "open" and d.json()["comment"] == "Я фронтендер"
    assert c.post("/candidates/me/category/dispute", json=body, headers=h).status_code == 409
    assert (
        c.get("/candidates/me/category", headers=h).json()["dispute"]["claimed_role"] == "frontend"
    )

    import sqlite3

    with sqlite3.connect(c.db_path) as con:
        (payload,) = con.execute(
            "select payload from outbox where type='category.disputed'"
        ).fetchone()
    assert "фронтендер" not in payload and "frontend" in payload


def test_category_dispute_validation_and_access(c):
    h = _user(c, "a@x.io")
    bad = {"claimed_role": "wizard", "claimed_grade": "middle"}
    assert c.post("/candidates/me/category/dispute", json=bad, headers=h).status_code == 422
    ok = {"claimed_role": "backend", "claimed_grade": "senior"}
    emp = _user(c, "e@x.io", role="employer")
    assert c.get("/candidates/me/category", headers=emp).status_code == 403
    assert c.post("/candidates/me/category/dispute", json=ok, headers=emp).status_code == 403
    noc = _user(c, "n@x.io", consent=False)
    assert c.post("/candidates/me/category/dispute", json=ok, headers=noc).status_code == 403
    h2 = _user(c, "b@x.io")  # чужое оспаривание не видно
    c.post("/candidates/me/category/dispute", json=ok, headers=h)
    assert c.get("/candidates/me/category", headers=h2).json()["dispute"] is None


async def test_pseudonym_exhausted_uses_unique_fallback(tmp_path, monkeypatch):
    """E42-3: 20 коллизий подряд не роняют создание: псевдоним берётся от pseudo_id."""
    from app.identity.models import User
    from fsp_platform.db import make_engine, make_session_factory, session_scope

    url = f"sqlite+aiosqlite:///{tmp_path / 'p.db'}"
    subprocess.run(  # noqa: ASYNC221
        [sys.executable, "-m", "alembic", "-x", f"url={url}", "upgrade", "head"],
        cwd=CORE,
        check=True,
        capture_output=True,
    )
    factory = make_session_factory(make_engine(url))
    monkeypatch.setattr(service, "make_pseudonym", lambda: "Candidate #1111")
    async with session_scope(factory) as s:
        ids = [uuid.uuid4() for _ in range(3)]
        s.add_all(
            [
                User(id=u, email=f"{u.hex[:6]}@x.io", password_hash="x", role="candidate")
                for u in ids
            ]
        )
        await s.flush()
        got = [await service.get_or_create(s, u, "secret") for u in ids]
        assert got[0].pseudonym == "Candidate #1111"
        assert len({c.pseudonym for c in got}) == 3
        assert got[1].pseudonym == f"Candidate #{got[1].pseudo_id[:8]}"
