# ruff: noqa: F811
"""Команды ФСП и командный оффер: список, права, идемпотентность, откат."""

import uuid

import pytest
from test_offers import (  # noqa: F401  (фикстуры и помощники)
    _candidate,
    _db,
    _employer,
    _vacancy,
    c,
    template_db,
)


def _team(c, team_id, members, *, name="Бинарники", competition="comp1", place=3):
    """Команда ФСП с участниками платформы: members = [(user_id, role)]."""
    _db(
        c,
        "insert or ignore into fsp_competitions (id, title, discipline) values (?,?,?)",
        competition,
        "Кубок",
        "algo",
    )
    _db(c, "insert into fsp_teams (id, name, competition_id) values (?,?,?)",
        team_id, name, competition)  # fmt: skip
    for i, (uid, role) in enumerate(members):
        _db(
            c, "insert into fsp_team_members (team_id, participant_id, candidate_id, role)"
            " values (?,?,?,?)", team_id, f"p-{team_id}-{i}", uid, role,
        )  # fmt: skip
        _db(
            c, "insert into fsp_results (id, candidate_id, participant_id, competition_id, stage,"
            " team_id, place, is_active) values (?,?,?,?,?,?,?,1)",
            uuid.uuid4().hex, uid, f"p-{team_id}-{i}", competition, "final", team_id, place,
        )  # fmt: skip


@pytest.fixture
def world(c):
    e = _employer(c, "e@x.ru")
    vid = _vacancy(c, e)
    h1, p1, u1 = _candidate(c, "c1@x.ru", 1)
    h2, p2, u2 = _candidate(c, "c2@x.ru", 2)
    _team(c, "t1", [(u1, "captain"), (u2, "member")])
    return c, e, vid, (h1, p1, u1), (h2, p2, u2)


def _body(vid, p1, p2, team="t1"):
    return {
        "vacancy_id": vid, "fsp_team_id": team, "message": "Привет, команда",
        "salary_per_member": [
            {"candidate_pseudo_id": p1, "salary_from": 250000, "salary_to": 320000},
            {"candidate_pseudo_id": p2, "salary_from": 200000, "salary_to": 280000},
        ],
    }  # fmt: skip


def _post(c, e, body, key="k1"):
    return c.post("/team-offers", json=body, headers={**e, "Idempotency-Key": key})


def test_list_teams_anonymous_and_filters(world):
    c, e, vid, (_, p1, _), (_, p2, _) = world
    r = c.get("/teams", headers=e)
    assert r.status_code == 200
    (team,) = r.json()
    assert team["id"] == "t1" and team["discipline"] == "algo" and team["best_place"] == 3
    assert {m["pseudo_id"] for m in team["members"]} == {p1, p2}
    assert "email" not in str(team) and "user_id" not in str(team)
    assert c.get("/teams?discipline=algo&min_place=3", headers=e).json()
    assert c.get("/teams?discipline=ml", headers=e).json() == []
    assert c.get("/teams?min_place=2", headers=e).json() == []


def test_hidden_member_drops_team(world):
    c, e, vid, (_, p1, u1), _ = world
    _db(c, "update candidates set visibility=? where user_id=?", '{"teams": false}', u1)
    assert c.get("/teams", headers=e).json() == []
    assert _post(c, e, _body(vid, p1, "pid0002")).status_code == 404  # team_not_found


def test_teams_roles(world):
    c, e, vid, (h1, _, _), _ = world
    assert c.get("/teams", headers=h1).status_code == 403
    assert c.get("/teams").status_code == 401


def test_create_team_offer(world):
    c, e, vid, (h1, p1, _), (h2, p2, _) = world
    r = _post(c, e, _body(vid, p1, p2))
    assert r.status_code == 201, r.text
    data = r.json()
    assert len(data["offers"]) == 2 and data["team_name"] == "Бинарники"
    assert {o["team_offer_id"] for o in data["offers"]} == {data["team_offer_id"]}
    assert sorted(o["salary_from"] for o in data["offers"]) == [200000, 250000]
    rows = _db(c, "select team_offer_id, status from offers")
    assert len({t for t, _ in rows}) == 1 and {s for _, s in rows} == {"sent"}
    # каждый участник отвечает за свой оффер
    mine = c.get("/candidates/me/offers", headers=h1).json()
    assert len(mine) == 1 and mine[0]["team_offer_id"] == data["team_offer_id"]
    assert c.post(f"/offers/{mine[0]['id']}/accept", headers=h1).status_code == 200
    other = c.get("/candidates/me/offers", headers=h2).json()[0]
    assert other["status"] in ("sent", "viewed")


def test_team_offer_idempotent(world):
    c, e, vid, _, (_, p2, _) = world
    p1 = "pid0001"
    first = _post(c, e, _body(vid, p1, p2))
    again = _post(c, e, _body(vid, p1, p2))
    assert again.status_code == 201 and again.headers["Idempotent-Replay"] == "true"
    assert again.json()["team_offer_id"] == first.json()["team_offer_id"]
    assert _db(c, "select count(*) from offers")[0][0] == 2
    assert _db(c, "select count(*) from outbox where type='offer.sent'")[0][0] == 2


def test_requires_idempotency_key(world):
    c, e, vid, _, _ = world
    r = c.post("/team-offers", json=_body(vid, "pid0001", "pid0002"), headers=e)
    assert r.status_code == 422 and r.json()["code"] == "idempotency_key_required"


def test_foreign_member_and_unknown_team_404(world):
    c, e, vid, _, _ = world
    h3, p3, _ = _candidate(c, "c3@x.ru", 3)
    r = _post(c, e, _body(vid, "pid0001", p3))
    assert r.status_code == 404 and r.json()["code"] == "candidate_not_found"
    assert _db(c, "select count(*) from offers")[0][0] == 0
    r = _post(c, e, _body(vid, "pid0001", "pid0002", team="nope"), key="k2")
    assert r.status_code == 404 and r.json()["code"] == "team_not_found"


def test_other_company_vacancy_404(world):
    c, e, vid, _, _ = world
    other = _employer(c, "o@x.ru", name="Other Co", inn="7736050003")
    r = _post(c, other, _body(vid, "pid0001", "pid0002"))
    assert r.status_code == 404


def test_member_error_rolls_back_all(world):
    c, e, vid, _, _ = world
    body = _body(vid, "pid0001", "pid0002")
    body["salary_per_member"][1]["salary_to"] = 100  # < salary_from
    r = _post(c, e, body)
    assert r.status_code == 422
    assert _db(c, "select count(*) from offers")[0][0] == 0


def test_needs_two_distinct_members(world):
    c, e, vid, _, _ = world
    body = _body(vid, "pid0001", "pid0001")
    r = _post(c, e, body)
    assert r.status_code == 422 and r.json()["code"] == "team_members_invalid"
