"""Навигатор (E12-1): следующий грейд, пробелы профессии, тест, соревнования ФСП."""

import uuid
from datetime import date, timedelta

from app.graph.fsp_models import FspCompetitionRow
from app.graph.models import CandidateSkill
from app.matching import navigator
from app.matching.uplift import UpliftConfig
from app.taxonomy.models import Discipline, DisciplineSkillRule, Role, RoleSkill, Skill
from core_helpers import register
from factories.assessment import make_graded_candidate
from fsp_contracts.assessment import TestGrade

UCFG = UpliftConfig.load()


def test_next_test_grade():
    assert navigator.next_test_grade(None) == "junior"
    assert navigator.next_test_grade("junior") == "middle"
    assert navigator.next_test_grade("middle") == "senior"
    assert navigator.next_test_grade("senior") is None


def test_pick_gaps_orders_by_weight_and_skips_confirmed():
    weights = {"python": 1.0, "docker": 0.8, "kafka": 0.5, "sql": 0.8}
    held = {"python": 0.9, "docker": 0.3, "sql": 0.0}
    gaps = navigator.pick_gaps(weights, held, 0.65)
    # python подтверждён; при равном весе слабее подтверждённый (sql) идёт раньше docker
    assert [g[0] for g in gaps] == ["sql", "docker", "kafka"]
    assert navigator.pick_gaps(weights, held, 0.65, limit=1) == [("sql", 0.8, 0.0)]


def test_assessment_path_matches_blocks_md():
    assert navigator.assessment_path("backend", "senior") == (
        "/me/assessment?profession=backend&grade=senior"
    )


async def test_compute_path_to_next_grade(session):
    today = date(2026, 6, 1)
    uid, _ = await make_graded_candidate(
        session, {"backend": TestGrade.middle}, primary_role="backend"
    )
    py = Skill(slug=f"py-{uuid.uuid4().hex[:4]}", name="Python", kind="hard", source="core")
    dk = Skill(slug=f"dk-{uuid.uuid4().hex[:4]}", name="Docker", kind="hard", source="core",
               testable=True)  # fmt: skip
    session.add_all(
        [
            py,
            dk,
            Role(slug="backend", name="Бэкенд", is_profession=True),
            Discipline(slug="dev", name="D"),
        ]
    )
    await session.flush()
    session.add_all([
        RoleSkill(role="backend", skill_id=py.id, weight=1.0),
        RoleSkill(role="backend", skill_id=dk.id, weight=0.8),
        CandidateSkill(candidate_id=uid, skill_id=py.id, confidence=0.9, level=4, sources=[],
                       top_evidence=[], claimed_only=False),
        DisciplineSkillRule(discipline="dev", skill_id=dk.id, weight=0.8),
        FspCompetitionRow(id="c1", title="Кубок DevOps", discipline="dev",
                          start_date=today + timedelta(days=20), status="registration"),
        FspCompetitionRow(id="c2", title="Далёкий", discipline="dev",
                          start_date=today + timedelta(days=300), status="announced"),
    ])  # fmt: skip
    await session.flush()
    from app.candidates.models import Candidate

    cand = await session.get(Candidate, uid)
    cand.grade_next = {"grade": "senior", "points_needed": 2.5, "hints": [{"text": "тест"}, "ещё"]}
    out = await navigator.compute(session, cand, [{"skill": "a"}] * 5, UCFG, today)

    assert out["target"] == {"role": "backend", "grade": "senior"}
    assert out["current_grade"]["grade"] == "middle"
    assert out["next_grade"] == {"points_needed": 2.5, "hints": ["тест", "ещё"]}
    assert out["test"]["path"] == "/me/assessment?profession=backend&grade=senior"
    assert [g["name"] for g in out["skill_gaps"]] == ["Docker"]  # Python уже подтверждён
    assert out["skill_gaps"][0]["testable"] is True
    (comp,) = out["competitions"]  # c2 дальше 120 дней
    assert comp["id"] == "c1" and comp["skills"] == [dk.slug]
    assert len(out["uplift"]) == 3  # топ-3


async def test_senior_has_no_next_grade(session):
    uid, _ = await make_graded_candidate(
        session, {"backend": TestGrade.senior}, primary_role="backend"
    )
    from app.candidates.models import Candidate

    out = await navigator.compute(session, await session.get(Candidate, uid), [], UCFG)
    assert out["target"] is None and out["test"] is None
    assert out["current_grade"]["grade"] == "senior" and out["skill_gaps"] == []


def test_endpoint_roles_and_empty_profile(api):
    assert api.get("/candidates/me/navigator").status_code == 401
    employer = register(api, "employer")
    assert api.get("/candidates/me/navigator", headers=employer).status_code == 403
    cand = register(api, "candidate")
    r = api.get("/candidates/me/navigator", headers=cand)
    assert r.status_code == 200
    assert r.json() == {"skill_gaps": [], "competitions": [], "uplift": []}
