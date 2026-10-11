# ruff: noqa: F811
"""«Почему вы» и рейтинг ответственности компании: факторы, утечки, выборка."""

import pytest
from test_offers import (  # noqa: F401  (фикстуры и помощники)
    _candidate,
    _db,
    _employer,
    _past,
    _vacancy,
    c,
    template_db,
)
from test_offers_interest import _interest


def _own_skill(c, uid, slug="python", conf=0.8):
    (sid,) = _db(c, "select id from skills where slug=?", slug)[0]
    _db(
        c,
        "insert into candidate_skills (candidate_id, skill_id, confidence, level, sources,"
        " top_evidence, claimed_only) values (?,?,?,3,'[\"test\"]','[]',0)",
        uid, sid, conf,
    )  # fmt: skip


@pytest.fixture
def world(c):
    e = _employer(c, "e@x.ru")
    vid = _vacancy(c, e)
    ch, pid, uid = _candidate(c, "c@x.ru", 1, salary_min=250000, formats='["remote"]')
    return c, e, vid, ch, pid, uid


def test_why_you_factors_with_vacancy(world):
    c, e, vid, ch, pid, uid = world
    _own_skill(c, uid)
    iid = _interest(c, e, pid, vacancy_id=vid).json()["id"]
    why = c.get("/candidates/me/interests", headers=ch).json()["items"][0]["why_you"]
    codes = [f["code"] for f in why["factors"]]
    assert {"grade", "skills"} <= set(codes)
    assert 1 <= len(codes) <= 3
    assert [f["weight"] for f in why["factors"]] == sorted(
        (f["weight"] for f in why["factors"]), reverse=True
    )
    assert "skills" in codes and why["unconfirmed"] == []
    got = c.get(f"/offers/{iid}", headers=ch).json()
    assert got["why_you"]["factors"] == why["factors"]


def test_why_you_unconfirmed_and_salary_minus(world):
    c, e, vid, ch, pid, uid = world  # навыков у кандидата нет, вилка ниже ожиданий
    _interest(c, e, pid, vacancy_id=vid, salary_from=100000, salary_to=200000)
    why = c.get("/candidates/me/interests", headers=ch).json()["items"][0]["why_you"]
    assert any("не подтверждён" in t.lower() for t in why["unconfirmed"])
    assert any("ниже ваших ожиданий" in t for t in why["unconfirmed"])
    assert "salary" not in [f["code"] for f in why["factors"]]


def test_why_you_without_vacancy(world):
    c, e, vid, ch, pid, uid = world
    _own_skill(c, uid)
    _interest(c, e, pid)
    why = c.get("/candidates/me/interests", headers=ch).json()["items"][0]["why_you"]
    assert {"grade", "skills"} <= {f["code"] for f in why["factors"]}


def test_no_other_candidates_leak(world):
    c, e, vid, ch, pid, uid = world
    ch2, pid2, uid2 = _candidate(c, "c2@x.ru", 2, salary_min=1)
    _own_skill(c, uid2, conf=0.99)
    _interest(c, e, pid, vacancy_id=vid)
    _interest(c, e, pid2, vacancy_id=vid)
    raw = c.get("/candidates/me/interests", headers=ch).text
    assert pid2 not in raw and "pid0002" not in raw
    assert "Не подтверждён навык" in raw  # чужие подтверждения кандидату не засчитаны


def test_company_reliability_sample_and_rate(world):
    c, e, vid, ch, pid, uid = world
    _interest(c, e, pid)
    comp = c.get("/candidates/me/interests", headers=ch).json()["items"][0]["company"]
    assert comp["reliability"]["sample"] == 0 and comp["reliability"]["response_rate"] is None
    (cid,) = _db(c, "select id from companies")[0]
    (eid,) = _db(c, "select created_by from offers")[0]
    # 4 отклика: 3 с ответом (2 ч), 1 истёк без ответа
    for i in range(4):
        answered = i < 3
        _db(
            c,
            "insert into offers (id, company_id, created_by, salary_from, salary_to,"
            " salary_basis, initiator, status, expires_at, created_at, viewed_at,"
            " below_candidate_min) values (?,?,?,1,2,'gross','candidate',?,?,?,?,0)",
            f"{i:032x}", cid, eid, "viewed" if answered else "expired",
            _past(days=-1), _past(hours=10), _past(hours=8) if answered else None,
        )  # fmt: skip
    rel = c.get("/candidates/me/interests", headers=ch).json()["items"][0]["company"]["reliability"]
    assert rel["sample"] == 4 and rel["response_rate"] == 0.75
    assert rel["avg_response_hours"] == pytest.approx(2.0, abs=0.1)
