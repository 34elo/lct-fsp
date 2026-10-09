# ruff: noqa: F811
"""Сила профиля и место в категории кандидата (E35-12a): формула места, права, приватность."""

import pytest
from app.matching.standing import gap_to_next_ten, median, place, relative_strength
from test_offers import (  # noqa: F401  (фикстуры и помощники)
    _candidate,
    _db,
    _employer,
    _vacancy,
    c,
    template_db,
)


def test_place_formula():
    assert place([0.9, 0.5, 0.2], 0.5) == (2, 67)  # 2 из 3 -> ceil(66.7)
    assert place([0.9, 0.5, 0.2], 0.9) == (1, 34)
    assert place([0.4, 0.4, 0.4], 0.4) == (1, 34)  # равные делят место
    assert place([0.7], 0.7) == (1, 100)


def test_relative_strength_and_gap():
    assert relative_strength(0.57, 0.75) == 76.0  # 0.57 / 0.75
    assert relative_strength(0.75, 0.75) == 100.0
    assert relative_strength(0.0, 0.0) == 100.0
    vals = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05]
    # место 5 (топ-50): граница топ-40 -> 4-й по силе (0.6): (0.6 - 0.5)/0.9 = 11.1 п.п.
    g = gap_to_next_ten(vals, 0.5, 50)
    assert g is not None and g.top_percent == 40 and g.gap_relative == 11.1
    assert gap_to_next_ten(vals, 0.9, 10) is None  # топ-10 % — выше некуда
    assert gap_to_next_ten(vals, 0.8, 20).top_percent == 10


def test_median():
    assert median([]) is None
    assert median([5]) == 5
    assert median([1, 9, 3]) == 3
    assert median([100, 200]) == 150
    assert median([100, 201]) == 150  # округление


def _set_band(c, uid, band):
    _db(c, "update grades set band_position=? where candidate_id=?", band, uid)


def test_roles_and_no_grade(c):
    e = _employer(c, "e@x.ru")
    assert c.get("/candidates/me/standing", headers=e).status_code == 403
    assert c.get("/candidates/me/standing").status_code == 401
    h, _, uid = _candidate(c, "c@x.ru", 1)
    _db(c, "delete from grades where candidate_id=?", uid)
    r = c.get("/candidates/me/standing", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["strength"] is None and body["category_size"] == 0 and body["peers"] == []


@pytest.fixture
def world(c):
    ha, _, ua = _candidate(c, "a@x.ru", 1, salary_min=100000)
    hb, _, ub = _candidate(c, "b@x.ru", 2, salary_min=200000)
    hc, _, uc = _candidate(c, "c@x.ru", 3, salary_min=300000)
    _set_band(c, ua, 0.2)
    _set_band(c, ub, 0.5)
    _set_band(c, uc, 0.9)
    return c, (ha, hb, hc), (ua, ub, uc)


def test_rank_within_category(world):
    c, (ha, hb, hc), _ = world
    heads = dict(zip("abc", (ha, hb, hc), strict=True))
    got = {n: c.get("/candidates/me/standing", headers=h).json() for n, h in heads.items()}
    assert [got[n]["strength"]["rank"] for n in "abc"] == [3, 2, 1]
    assert [got[n]["strength"]["top_percent"] for n in "abc"] == [100, 67, 34]
    b = got["b"]
    assert (b["profession"], b["grade"], b["category_size"]) == ("backend", "middle", 3)
    assert b["peers"][0]["strength"] == b["strength"]["value"]  # свой пункт первым
    assert sorted(p["salary_min"] for p in b["peers"]) == [100000, 200000, 300000]
    assert b["strength"]["parts"] and b["strength"]["parts"][0]["code"] == "T"
    assert 0 <= b["strength"]["value"] <= 1
    assert (
        got["c"]["strength"]["relative"] == 100.0
        and got["c"]["strength"]["gap_to_next_ten"] is None
    )
    assert 0 < b["strength"]["relative"] < 100
    assert b["leader"] == {"grade": "middle", "relative": 100.0}
    assert b["strength"]["gap_to_next_ten"]["top_percent"] == 60


def test_other_category_not_counted_and_no_leaks(world):
    c, (ha, hb, hc), (ua, ub, uc) = world
    _db(c, "update grades set grade='junior' where candidate_id=?", uc)  # ушёл в другую категорию
    b = c.get("/candidates/me/standing", headers=hb).json()
    assert b["category_size"] == 2 and b["strength"]["rank"] == 1
    text = str(b)
    for secret in ("pid000", "a@x.ru", "b@x.ru", str(ua), str(ub)):
        assert secret not in text
    assert set(b["peers"][0]) == {"strength", "salary_min", "theta"}


def test_category_stats_and_theta(world):
    c, (ha, hb, hc), (ua, ub, uc) = world
    st = c.get("/candidates/me/standing", headers=hb).json()["category_stats"]
    assert st == {
        "candidates": 3, "interests": 0, "interest_salary_from_median": None,
        "interest_salary_to_median": None, "companies_searching": 0,
    }  # fmt: skip
    e = _employer(c, "e@x.ru")
    _vacancy(c, e)  # backend, middle..senior, опубликована
    pid = _db(c, "select pseudo_id from candidates where user_id=?", ua)[0][0]
    assert c.post("/interests", headers=e, json={
        "candidate_pseudo_id": pid, "salary_from": 200000, "salary_to": 260000,
        "message": "Интересно",
    }).status_code == 201  # fmt: skip
    b = c.get("/candidates/me/standing", headers=hb).json()
    assert b["category_stats"]["interests"] == 1
    assert b["category_stats"]["interest_salary_from_median"] == 200000
    assert b["category_stats"]["interest_salary_to_median"] == 260000
    assert b["category_stats"]["companies_searching"] == 1
    assert all(isinstance(p["theta"], float) for p in b["peers"])
    assert str(ua) not in str(b) and pid not in str(b)
