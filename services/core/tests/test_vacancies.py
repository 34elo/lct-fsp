import json
import sqlite3
import uuid
from pathlib import Path

import fakeredis
import pytest
from app.config import Settings
from app.main import build_app
from core_helpers import upgrade_head
from fastapi.testclient import TestClient
from fsp_platform.ratelimit import RateLimiter

CORE = Path(__file__).resolve().parents[1]
PWD = "correct-horse-battery"
INN = "7707083893"


@pytest.fixture
def c(tmp_path):
    db = tmp_path / "v.db"
    upgrade_head(f"sqlite+aiosqlite:///{db}")
    with sqlite3.connect(db) as con:
        for slug, status in (("python", "active"), ("fastapi", "active"), ("old", "rejected")):
            con.execute(
                "insert into skills (id, slug, name, kind, status, source, support_candidates,"
                " support_vacancies, testable) values (?,?,?,?,?,?,0,0,0)",
                (uuid.uuid4().hex, slug, slug, "tech", status, "seed"),
            )
    app = build_app(Settings(database_url=f"sqlite+aiosqlite:///{db}", ui_bus_enabled=False))
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        client.db = db
        yield client


def _employer(c, email, *, verified=True, name="Acme Labs"):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": "employer"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    co = c.post("/companies", json={"name": name, "inn": INN}, headers=h).json()
    if verified:
        with sqlite3.connect(c.db) as con:
            con.execute(
                "update companies set status='verified' where id=?", (co["id"].replace("-", ""),)
            )
    return h


def _body(**over):
    body = {
        "title": "Backend-разработчик",
        "role": "backend",
        "grade_min": "middle",
        "grade_max": "senior",
        "formats": ["remote", "hybrid"],
        "employment_type": "full",
        "city": "Москва",
        "salary_from": 200000,
        "salary_to": 300000,
        "important_qualities": ["teamwork"],
        "skills": [
            {"slug": "python", "required": True, "min_level": 3, "weight": 2},
            {"slug": "fastapi", "required": False},
        ],
    }
    body.update(over)
    return body


def _events(c):
    with sqlite3.connect(c.db) as con:
        rows = con.execute(
            "select type, payload from outbox where type like 'vacancy.%' order by id"
        )
        return [(t, json.loads(p)["payload"]) for t, p in rows]


def test_create_get_list_patch(c):
    h = _employer(c, "e@x.io")
    r = c.post("/vacancies", json=_body(), headers=h)
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["status"] == "draft" and v["version"] == 1 and v["range_too_wide"] is False
    assert [s["slug"] for s in v["skills"]] == ["python", "fastapi"]
    assert v["skills"][0]["min_level"] == 3 and v["skills"][1]["min_level"] == 2
    assert c.get(f"/vacancies/{v['id']}", headers=h).json()["id"] == v["id"]
    assert [x["id"] for x in c.get("/vacancies", headers=h).json()] == [v["id"]]
    assert c.get("/vacancies?status=closed", headers=h).json() == []

    p = c.patch(
        f"/vacancies/{v['id']}",
        json={"salary_to": 400000, "skills": [{"slug": "python"}]},
        headers=h,
    ).json()
    assert p["version"] == 2 and p["range_too_wide"] is True and len(p["skills"]) == 1
    assert _events(c) == []  # черновик событий не порождает
    same = c.patch(f"/vacancies/{v['id']}", json={}, headers=h).json()
    assert same["version"] == 2


def test_validation(c):
    h = _employer(c, "e@x.io")
    bad = [
        _body(grade_min="senior", grade_max="junior"),
        _body(salary_from=300000, salary_to=200000),
        _body(formats=[]),
        _body(skills=[{"slug": "python"}, {"slug": "python"}]),
        _body(skills=[{"slug": "nope"}]),
        _body(skills=[{"slug": "old"}]),
        _body(role="wizard"),
        _body(status="published"),
    ]
    codes = [c.post("/vacancies", json=b, headers=h).status_code for b in bad]
    assert codes == [422] * len(bad)
    r = c.post("/vacancies", json=_body(skills=[{"slug": "nope"}]), headers=h)
    assert r.json()["code"] == "unknown_skill"
    vid = c.post("/vacancies", json=_body(), headers=h).json()["id"]
    r = c.patch(f"/vacancies/{vid}", json={"grade_max": "junior"}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "invalid_grade_range"
    assert c.patch(f"/vacancies/{vid}", json={"title": None}, headers=h).status_code == 422


def test_roles_and_foreign_resource_404(c):
    h1 = _employer(c, "a@x.io", name="Acme One")
    h2 = _employer(c, "b@x.io", name="Acme Two")
    vid = c.post("/vacancies", json=_body(), headers=h1).json()["id"]
    for call in (
        lambda: c.get(f"/vacancies/{vid}", headers=h2),
        lambda: c.patch(f"/vacancies/{vid}", json={"title": "Другое"}, headers=h2),
        lambda: c.delete(f"/vacancies/{vid}", headers=h2),
        lambda: c.post(f"/vacancies/{vid}/publish", headers=h2),
        lambda: c.post(f"/vacancies/{vid}/close", headers=h2),
    ):
        assert call().status_code == 404
    assert c.get("/vacancies", headers=h2).json() == []
    assert c.get(f"/vacancies/{uuid.uuid4()}", headers=h1).status_code == 404
    r = c.post("/auth/register", json={"email": "k@x.io", "password": PWD, "role": "candidate"})
    cand = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert c.get("/vacancies", headers=cand).status_code == 403
    assert c.get("/vacancies").status_code == 401


def test_employer_without_company(c):
    r = c.post("/auth/register", json={"email": "n@x.io", "password": PWD, "role": "employer"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert c.post("/vacancies", json=_body(), headers=h).status_code == 404


def test_publish_close_events_and_idempotency(c):
    h = _employer(c, "e@x.io")
    vid = c.post("/vacancies", json=_body(), headers=h).json()["id"]
    p = c.post(f"/vacancies/{vid}/publish", headers=h)
    assert p.status_code == 200 and p.json()["status"] == "published"
    assert p.json()["published_at"] and p.json()["version"] == 2
    assert c.post(f"/vacancies/{vid}/publish", headers=h).json()["version"] == 2  # повтор

    u = c.patch(f"/vacancies/{vid}", json={"title": "Senior backend"}, headers=h).json()
    assert u["version"] == 3
    assert c.delete(f"/vacancies/{vid}", headers=h).status_code == 409

    cl = c.post(f"/vacancies/{vid}/close", headers=h).json()
    assert cl["status"] == "closed" and cl["version"] == 4
    assert c.post(f"/vacancies/{vid}/close", headers=h).json()["version"] == 4
    assert c.patch(f"/vacancies/{vid}", json={"title": "Ещё"}, headers=h).status_code == 409
    assert c.post(f"/vacancies/{vid}/publish", headers=h).status_code == 409
    assert _events(c) == [
        ("vacancy.published", {"vacancy_id": vid, "version": 2}),
        ("vacancy.updated", {"vacancy_id": vid, "version": 3}),
        ("vacancy.closed", {"vacancy_id": vid, "version": 4}),
    ]


def test_publish_requires_verified_company_and_required_skill(c):
    h = _employer(c, "e@x.io", verified=False)
    vid = c.post("/vacancies", json=_body(), headers=h).json()["id"]
    r = c.post(f"/vacancies/{vid}/publish", headers=h)
    assert r.status_code == 403 and r.json()["code"] == "company_not_verified"
    assert c.get(f"/vacancies/{vid}", headers=h).json()["status"] == "draft"

    h2 = _employer(c, "f@x.io", name="Acme Two")
    v2 = c.post(
        "/vacancies", json=_body(skills=[{"slug": "fastapi", "required": False}]), headers=h2
    )
    r = c.post(f"/vacancies/{v2.json()['id']}/publish", headers=h2)
    assert r.status_code == 422 and r.json()["code"] == "no_required_skills"
    assert _events(c) == []


def test_delete_draft(c):
    h = _employer(c, "e@x.io")
    vid = c.post("/vacancies", json=_body(), headers=h).json()["id"]
    assert c.delete(f"/vacancies/{vid}", headers=h).status_code == 204
    assert c.get(f"/vacancies/{vid}", headers=h).status_code == 404
    with sqlite3.connect(c.db) as con:
        assert con.execute("select count(*) from vacancy_skills").fetchone() == (0,)


def test_range_too_wide_threshold(c):
    """range_too_wide: (до − от) / от > 0.5 equals salary_to/from > 1.5; backend uses 1.6 (EU)."""
    h = _employer(c, "e@x.io")
    # 200k → 300k: 300/200 = 1.5, не попадает в > 1.6
    v1 = c.post("/vacancies", json=_body(salary_from=200000, salary_to=300000), headers=h).json()
    assert v1["range_too_wide"] is False
    # 200k → 320k: 320/200 = 1.6, равен пороговому значению, не попадает в > 1.6
    v2 = c.post("/vacancies", json=_body(salary_from=200000, salary_to=320000), headers=h).json()
    assert v2["range_too_wide"] is False
    # 200k → 321k: 321/200 = 1.605, попадает в > 1.6
    v3 = c.post("/vacancies", json=_body(salary_from=200000, salary_to=321000), headers=h).json()
    assert v3["range_too_wide"] is True
    # 100k → 160k: граничное значение 1.6x
    v4 = c.post("/vacancies", json=_body(salary_from=100000, salary_to=160000), headers=h).json()
    assert v4["range_too_wide"] is False
    # 100k → 161k: чуть выше 1.6x
    v5 = c.post("/vacancies", json=_body(salary_from=100000, salary_to=161000), headers=h).json()
    assert v5["range_too_wide"] is True
