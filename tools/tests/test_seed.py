"""Тесты tools/seed: детерминизм плана, объёмы, герои, данные fsp-mock и наполнение core."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.seed import __main__ as seed_cli  # noqa: E402
from tools.seed.plan import build_plan, load_config  # noqa: E402

ANCHOR = date(2026, 10, 3)


@pytest.fixture(scope="module")
def plan():
    return build_plan(seed=7, anchor=ANCHOR)


def test_deterministic_by_seed(plan):
    again = build_plan(seed=7, anchor=ANCHOR)
    other = build_plan(seed=8, anchor=ANCHOR)
    assert again["hash"] == plan["hash"]
    assert other["hash"] != plan["hash"]
    assert json.dumps(again, sort_keys=True, default=str) == json.dumps(
        plan, sort_keys=True, default=str
    )


def test_volumes_from_doc(plan):
    cfg = load_config()["counts"]
    cands = [c for c in plan["candidates"] if not c["hero"]]
    assert len(cands) == cfg["candidates"] == 400
    assert len(plan["companies"]) == 25
    assert sum(1 for c in plan["companies"] if c["status"] == "pending") == 2
    assert len(plan["vacancies"]) == 80
    assert len(plan["offers"]) == 300
    fsp = plan["fsp"]
    assert len(fsp["participants"]) == 600
    past = [c for c in fsp["competitions"] if c["status"] == "finished"]
    upcoming = [c for c in fsp["competitions"] if c["status"] != "finished"]
    assert len(past) == 45 and 6 <= len(upcoming) <= 8
    share_fsp = sum(1 for c in cands if c["fsp"]) / len(cands)
    assert 0.3 < share_fsp < 0.55
    assert (
        0.35
        < sum(1 for c in cands if any(e["source"] == "github" for e in c["evidence"])) / len(cands)
        < 0.7
    )


def test_heroes(plan):
    heroes = {c["hero"]: c for c in plan["candidates"] if c["hero"]}
    assert set(heroes) == {"anya", "dima"}
    anya = heroes["anya"]
    assert anya["fsp"] is None and anya["resume"]["experience"] == []  # привязка к ФСП — шаг демо
    fsp = plan["fsp"]
    res = fsp["results"]["p-anya"]
    assert res[0]["place"] == 2 and res[0]["team_role"] == "captain"
    team = next(t for t in fsp["teams"] if t["id"] == "t-north-lights")
    assert {m["participant_id"] for m in team["members"]} == {"p-anya", "p-m01", "p-m02"}
    assert fsp["results"]["p-m01"][0]["team_id"] == "t-north-lights"
    olga = next(c for c in plan["companies"] if c.get("hero") == "olga")
    assert olga["name"] == "Северный код" and olga["status"] == "verified"
    assert any(v["hero"] and v["company_idx"] == olga["idx"] for v in plan["vacancies"])


def test_only_fictional_and_unique(plan):
    emails = [c["email"] for c in plan["candidates"]] + [c["email"] for c in plan["companies"]]
    assert len(emails) == len(set(emails))
    assert all(e.endswith("@demo.fsp.test") for e in emails)
    assert all(p["email"].endswith("@example.test") for p in plan["fsp"]["participants"])
    ids = [p["id"] for p in plan["fsp"]["participants"]]
    assert len(ids) == len(set(ids))
    # у каждой пары (участник, соревнование) не больше одного результата
    for pid, rows in plan["fsp"]["results"].items():
        keys = [(r["competition_id"], r["stage"]) for r in rows]
        assert len(keys) == len(set(keys)), pid


def test_linked_candidates_have_results_in_mock(plan):
    res = plan["fsp"]["results"]
    linked = [c for c in plan["candidates"] if c["fsp"]]
    assert linked
    assert all(res[c["fsp"]["participant_id"]] for c in linked if c["fsp"])
    comp_ids = {c["id"] for c in plan["fsp"]["competitions"]}
    assert all(r["competition_id"] in comp_ids for rows in res.values() for r in rows)


def test_offer_plan_is_consistent(plan):
    for o in plan["offers"]:
        if o["outcome"] in ("sent", "viewed"):
            assert o["days_ago"] <= 5 and o["respond_hours"] is None
        if o["outcome"] == "expired":
            assert o["days_ago"] >= 9
        if o["respond_hours"] is not None:
            assert o["respond_hours"] < 7 * 24 and o["days_ago"] * 24 > o["respond_hours"]
        assert (o["decline_reason"] is not None) == (o["outcome"] == "declined")


def test_mock_json_loads_into_fsp_mock(plan, tmp_path):
    from fastapi.testclient import TestClient
    from fsp_mock.config import Settings
    from fsp_mock.main import build_app

    out = seed_cli.write_mock(plan, tmp_path / "mock.json")
    app = build_app(Settings(fsp_mock_data=str(out)))
    c = TestClient(app)
    h = {"X-Api-Key": "dev-mock-key"}
    r = c.get("/api/v1/participants/p-anya", headers=h)
    assert r.status_code == 200 and r.json()["last_name"] == "Волкова"
    rows = c.get("/api/v1/participants/p-anya/results", headers=h).json()
    assert rows[0]["place"] == 2 and rows[0]["team_role"] == "captain"
    comps = c.get("/api/v1/competitions", headers=h).json()
    assert len(comps) == len(plan["fsp"]["competitions"])
    st = c.get("/api/v1/competitions/c-002/standings", headers=h)
    assert st.status_code == 200 and st.json()
    team = c.get("/api/v1/teams/t-north-lights", headers=h).json()
    assert len(team["members"]) == 3
    assert c.get("/api/v1/participants/p-0001", headers=h).status_code in (200, 404)


# ------------------------------------------------------------------ наполнение core
CORE = ROOT / "services/core"


@pytest.fixture
def factory(tmp_path):
    from fsp_platform.db import make_engine, make_session_factory

    url = f"sqlite+aiosqlite:///{tmp_path / 'seed.db'}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url}", "upgrade", "head"],
        cwd=CORE,
        check=True,
        capture_output=True,
    )
    return make_session_factory(make_engine(url))


async def _load_taxonomy(factory):
    from app.taxonomy import service
    from app.taxonomy.loader import load_taxonomy
    from fsp_platform.db import session_scope

    data = load_taxonomy(ROOT / "data/taxonomy", ROOT / "data/fsp/discipline_rules.yaml")
    async with session_scope(factory) as s:
        await service.sync(s, data)


SMALL = {
    "candidates": 40,
    "companies": 6,
    "companies_pending": 1,
    "vacancies": 12,
    "vacancies_closed": 2,
    "offers": 25,
    "fsp_participants": 120,
    "provisional_skills": 20,
}


async def test_seed_core_end_to_end_and_idempotent(factory):
    from app.candidates.models import Candidate
    from app.companies.models import Company
    from app.graph.models import CandidateSkill, Evidence
    from app.identity.models import User
    from app.matching.models import Match
    from app.offers.models import Offer
    from app.taxonomy.models import Skill
    from app.vacancies.models import Vacancy
    from fsp_platform.db import session_scope
    from sqlalchemy import func, select

    from tools.seed.loader import Seeder

    await _load_taxonomy(factory)
    plan = build_plan(seed=3, anchor=date.today(), counts=SMALL)

    def seeder():
        return Seeder(
            plan, factory, password="demo-pass-1234", pseudo_secret="t", analytics_salt="t"
        )

    stats = await seeder().run()
    assert stats["candidates"] == 42 and stats["companies"] == 6 and stats["vacancies"] == 12
    assert stats.get("offers", 0) >= 3, dict(stats)

    async def counts():
        async with session_scope(factory) as s:
            return {
                m.__name__: await s.scalar(select(func.count()).select_from(m))
                for m in (User, Candidate, Company, Vacancy, Match, Offer, Evidence, CandidateSkill)
            }

    first = await counts()
    async with session_scope(factory) as s:
        # доверие, категория и грейд посчитаны сервисами core
        graded = await s.scalar(
            select(func.count()).select_from(Candidate).where(Candidate.grade.is_not(None))
        )
        assert graded >= 40
        fsp_ev = await s.scalar(
            select(func.count()).select_from(Evidence).where(Evidence.source == "fsp")
        )
        assert fsp_ev > 0
        # герои: Аня ●○○○ (только резюме), Дима с опытом; Ольга — владелец «Северного кода»
        anya = await s.scalar(select(User).where(User.email == "anya@demo.fsp.test"))
        rows = list(
            await s.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == anya.id))
        )
        assert rows and max(r.level for r in rows) <= 1
        olga = await s.scalar(select(User).where(User.email == "olga@demo.fsp.test"))
        assert olga is not None
        sev = await s.scalar(select(Company).where(Company.name == "Северный код"))
        assert sev.status == "verified"
        pending = await s.scalar(
            select(func.count()).select_from(Company).where(Company.status == "pending")
        )
        assert pending == 1
        prov = await s.scalar(
            select(func.count()).select_from(Skill).where(Skill.status == "provisional")
        )
        assert prov >= 20
        # у офферов есть вилка, статусы разные
        statuses = set(await s.scalars(select(Offer.status).distinct()))
        assert len(statuses) >= 3
        assert all(o.salary_from and o.salary_to for o in await s.scalars(select(Offer)))
        closed = await s.scalar(
            select(func.count()).select_from(Vacancy).where(Vacancy.status == "closed")
        )
        assert closed == 2

    again = await seeder().run()
    assert again.get("candidates", 0) == 0 and again.get("offers", 0) == 0
    assert await counts() == first  # повторный запуск ничего не меняет


# ------------------------------------------------------------------ seed-грейды блока 1
def test_grades_plan_distribution_and_coverage(plan):
    from collections import Counter

    from tools.seed.grades import PROFESSIONS, plan_grades

    g = plan_grades(plan)
    assert plan_grades(plan) == g  # детерминизм
    cells = {(e["profession"], e["grade"]) for es in g.values() for e in es}
    assert cells == {(p, gr) for p in PROFESSIONS for gr in ("junior", "middle", "senior")}
    first = Counter(es[0]["grade"] for k, es in g.items() if not k.startswith("hero-"))
    n = sum(first.values())
    assert abs(first["junior"] / n - 0.4) < 0.02 and abs(first["senior"] / n - 0.2) < 0.02
    flags = sum(es[0]["needs_confirmation"] for k, es in g.items() if not k.startswith("hero-"))
    assert flags == round(n * 0.05)
    assert g["hero-anya"][0]["grade"] == "junior" and g["hero-dima"][0]["grade"] == "middle"
    assert plan_grades(build_plan(seed=8, anchor=ANCHOR)) != g


def test_grades_hidden_professions_match_taxonomy():
    """E36-2: скрытые в `roles.yaml` профессии = `HIDDEN_PROFESSIONS`; герои — в видимых."""
    import yaml

    from tools.seed.grades import HERO_GRADES, HIDDEN_PROFESSIONS, PROFESSIONS

    roles = yaml.safe_load((ROOT / "data/taxonomy/roles.yaml").read_text(encoding="utf-8"))
    hidden = {
        r["slug"] for r in roles["roles"] if r.get("profession") and not r.get("active", True)
    }
    assert hidden == HIDDEN_PROFESSIONS and HIDDEN_PROFESSIONS <= set(PROFESSIONS)
    assert all(p not in HIDDEN_PROFESSIONS for p, *_ in HERO_GRADES.values())


async def test_seed_grades_core_and_idempotent(factory):
    from app.assessment import service as assessment
    from app.identity.models import User
    from fsp_platform.db import session_scope
    from sqlalchemy import select

    from tools.seed.grades import PROFESSIONS, seed_grades

    await _load_taxonomy(factory)
    plan = build_plan(seed=3, anchor=date.today(), counts=SMALL)
    from tools.seed.loader import Seeder

    seeder = Seeder(plan, factory, password="demo-pass-1234", pseudo_secret="t", analytics_salt="t")
    stats = await seeder.run()  # E23-1: грейды пишутся до подбора, иначе выдача пуста
    assert stats["grades"] >= 42 and stats["matched_vacancies"] > 0
    async with session_scope(factory) as s:
        counts = await assessment.category_counts(s)
        anya = await s.scalar(select(User).where(User.email == "anya@demo.fsp.test"))
        dima = await s.scalar(select(User).where(User.email == "dima@demo.fsp.test"))
        assert {(g.profession, g.grade) for g in await assessment.get_grades(s, anya.id)} == {
            ("backend", "junior")
        }
        assert [g.grade for g in await assessment.get_grades(s, dima.id)] == ["middle"]
    assert {(p, g) for p in PROFESSIONS for g in ("junior", "middle", "senior")} <= set(counts)
    assert await seed_grades(factory, plan, seeder.user_ids) == {
        "grades": 0,
        "grades_candidates": 0,
    }
    async with session_scope(factory) as s:
        assert await assessment.category_counts(s) == counts


def test_jury_accounts_in_config():
    """E32-4b: демо-аккаунты жюри заданы в config.yaml и не пересекаются с планом витрины."""
    from tools.seed.jury import jury_emails

    emails = jury_emails()
    assert emails["candidate"] != emails["employer"]
    plan = build_plan(seed=7, anchor=ANCHOR)
    taken = {c["email"] for c in plan["candidates"]} | {co["email"] for co in plan["companies"]}
    assert not set(emails.values()) & taken


async def test_seed_jury_idempotent(factory):
    """E32-4b: аккаунты жюри создаются один раз, кандидат без грейда, компания проверена."""
    from app.assessment import service as assessment
    from app.companies import service as companies
    from app.identity import service as identity
    from app.identity.models import User
    from fsp_platform.db import session_scope
    from sqlalchemy import select

    from tools.seed.jury import jury_emails, seed_jury

    emails = jury_emails()
    first = await seed_jury(factory, password="demo-pass-1234", pseudo_secret="t")
    assert first == {"jury_candidate": 1, "jury_employer": 1}
    assert await seed_jury(factory, password="demo-pass-1234", pseudo_secret="t") == {
        "jury_candidate": 0,
        "jury_employer": 0,
    }
    async with session_scope(factory) as s:
        cand = await s.scalar(select(User).where(User.email == emails["candidate"]))
        hr = await s.scalar(select(User).where(User.email == emails["employer"]))
        assert (cand.role, hr.role) == ("candidate", "employer")
        assert await assessment.get_grades(s, cand.id) == []
        company = await companies.membership(s, hr.id)
        assert company is not None
        assert identity.normalize_email(emails["candidate"]) == cand.email


def test_demo_v2_data_consistent(plan):
    """E34-1: герои v2 покрывают сценарии, ссылки в данных замкнуты, email уникальны."""
    from tools.seed.demo_v2 import load_data, plan_attempts
    from tools.seed.plan import _hero_candidate

    d = load_data()
    cfg = load_config()
    heroes = {h["key"]: h for h in d["heroes"]}
    hist = plan_attempts(d)
    assert plan_attempts(d) == hist  # детерминизм
    modes = {a.get("mode", "standard") for v in hist.values() for a in v}
    assert "express" in modes
    assert any(a.get("integrity", 1.0) < 0.7 for v in hist.values() for a in v)
    assert any(a["result"] == "failed" for v in hist.values() for a in v)
    ages = {h["key"]: (h["age"], h["parent_consent"]) for h in d["heroes"] if h.get("age")}
    assert sorted(ages.values()) == [("minor", False), ("minor", True)]
    for v in hist.values():  # старые попытки раньше новых
        assert [a["days_ago"] for a in v] == sorted((a["days_ago"] for a in v), reverse=True)
    emails = [h["email"] for h in d["heroes"]] + [c["email"] for c in d["companies"]]
    plan_emails = {c["email"] for c in plan["candidates"]} | {c["email"] for c in plan["companies"]}
    assert len(emails) == len(set(emails)) and not set(emails) & plan_emails
    vac = {v["key"] for v in d["vacancies"]} | {"olga"}
    cos = {c["key"] for c in d["companies"]}
    people = set(heroes) | {"anya", "dima"}
    assert all(v["company"] in cos for v in d["vacancies"])
    assert all(
        o["vacancy"] in vac and o["candidate"] in people for o in d["offers"] + d["applications"]
    )
    assert len({o["n"] for o in d["offers"]}) == len(d["offers"])
    assert all(t["company"] in cos and set(t["answers"]) <= people for t in d["tasks"])
    assert all("example.test" in c["site"] for c in d["companies"])  # компании вымышленные
    c = _hero_candidate(cfg, date(2026, 10, 3), heroes["boris"])
    assert c["hero"] == "boris" and c["fsp"] is None
