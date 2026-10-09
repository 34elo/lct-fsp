"""Грейд: сигналы, пороги, ограничения, уверенность, разбивка, next_grade (ml.md §5)."""

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from app.candidates.models import Candidate
from app.graph.grade import (
    FspResult,
    GradeConfig,
    GradeInputs,
    achievement_kind,
    compute_grade,
    experience_points,
    grade_for_points,
    theta_points,
)
from app.graph.models import Evidence
from app.graph.recompute import recompute_profile
from app.graph.trust import TrustConfig
from app.identity.models import User
from app.taxonomy.models import Skill
from core_helpers import upgrade_head
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import select

CORE = Path(__file__).resolve().parents[1]
CFG = GradeConfig.load()
NOW = datetime(2026, 6, 1, 12, tzinfo=UTC)


def test_config_loaded_from_scoring_yaml():
    assert CFG == GradeConfig()  # дефолты в коде совпадают с data/scoring.yaml


@pytest.mark.parametrize(
    ("months", "pts"),
    [(None, 0), (0, 0), (1, 1), (11, 1), (12, 3), (35, 3), (36, 5), (59, 5), (60, 7), (95, 7)]
    + [(96, 8), (200, 8)],
)
def test_experience_points(months, pts):
    assert experience_points(months, CFG) == pts


@pytest.mark.parametrize(
    ("theta", "pts"), [(None, 0), (-0.5, 0), (0, 1), (0.9, 1), (1, 2), (2, 2), (2.1, 3)]
)
def test_theta_points(theta, pts):
    assert theta_points(theta, CFG) == pts


def test_achievement_kinds():
    assert achievement_kind(FspResult("national", 2, True)) == "top_national"
    assert achievement_kind(FspResult("international", 3)) == "top_national"
    assert achievement_kind(FspResult("national", 10, True)) == "national_finalist"
    assert achievement_kind(FspResult("interregional", 1)) == "interregional_medalist"
    assert achievement_kind(FspResult("regional", 3)) == "regional_medalist"
    assert achievement_kind(FspResult("regional", 9)) == "participant"
    assert achievement_kind(FspResult("national", 10, False)) == "participant"


@pytest.mark.parametrize(
    ("pts", "grade"),
    [(0, "intern"), (1.9, "intern"), (2, "junior"), (4, "junior_plus"), (6, "middle")]
    + [(8.4, "middle"), (8.5, "middle_plus"), (10.5, "senior"), (12.9, "senior")],
)
def test_thresholds(pts, grade):
    assert grade_for_points(pts, CFG, leadership_ok=True) == grade


def test_lead_needs_leadership():
    assert grade_for_points(14, CFG, leadership_ok=True) == "lead"
    assert grade_for_points(14, CFG, leadership_ok=False) == "senior"


def test_olympiad_without_commercial_is_middle_example_from_docs():
    # призёр всероссийского финала 3 + КМС 2.5 + тесты (θ 1.5 → 2) = 7.5 → Middle
    inp = GradeInputs(fsp_results=[FspResult("national", 2, True)], fsp_rank="cms", test_theta=1.5)
    r = compute_grade(inp, CFG)
    assert (r.score, r.grade) == (7.5, "middle")
    signals = {b.signal: b.points for b in r.breakdown}
    assert signals == {"experience": 0, "fsp_achievement": 3.0, "fsp_rank": 2.5, "tests": 2.0}


def test_no_commercial_cap_applies_with_note():
    inp = GradeInputs(
        fsp_results=[FspResult("international", 1)],
        fsp_rank="ms",
        test_theta=2.5,
        code_maturity=1.0,
        interview_avg=2.5,
    )  # 3 + 3.5 + 3 + 2 + 1 = 12.5 → senior без ограничения
    r = compute_grade(inp, CFG)
    assert (r.score, r.grade) == (12.5, "middle")
    assert r.breakdown[-1].signal == "constraint_no_commercial_cap"
    assert compute_grade(replace(inp, experience_months=24), CFG).grade == ("senior")


def test_lead_and_leadership_points():
    base = {"experience_months": 100, "fsp_results": [FspResult("national", 1)]}  # 8 + 3
    inp = GradeInputs(**base, fsp_rank="ms", code_maturity=1.0)  # + 3.5 + 2 = 16.5
    r = compute_grade(inp, CFG)
    assert (r.grade, r.next_grade) == ("senior", r.next_grade)
    assert any(b.signal == "constraint_lead_requires_leadership" for b in r.breakdown)
    r2 = compute_grade(replace(inp, leadership=0.6), CFG)
    assert r2.grade == "lead" and r2.next_grade is None
    assert {b.signal: b.points for b in r2.breakdown}["leadership"] == 0.9
    r3 = compute_grade(replace(inp, management_confirmed=True), CFG)
    assert r3.grade == "lead"


def test_interview_threshold():
    low = compute_grade(GradeInputs(interview_avg=1.9), CFG)
    high = compute_grade(GradeInputs(interview_avg=2.0), CFG)
    assert high.score - low.score == 1.0


def test_confidence_and_preliminary():
    r = compute_grade(GradeInputs(experience_months=30), CFG)
    assert (r.confidence, r.preliminary) == (0.25, True)
    r = compute_grade(GradeInputs(experience_months=30, test_theta=1.0), CFG)
    assert (r.confidence, r.preliminary) == (0.5, False)  # «предварительно» только < 0.5
    full = GradeInputs(experience_months=30, test_theta=1.0, code_maturity=0.5, fsp_rank="rank_3")
    assert compute_grade(full, CFG).confidence == 1.0
    assert compute_grade(GradeInputs(), CFG).confidence == 0.0


def test_next_grade_and_hints():
    r = compute_grade(GradeInputs(experience_months=30, test_theta=0.5), CFG, role_skill="python")
    assert r.score == 4.0 and r.grade == "junior_plus"
    n = r.next_grade
    assert (n.grade, n.points_needed) == ("middle", 2.0)
    texts = {h.signal: h.text for h in n.hints}
    assert texts["tests"] == "пройди тест по python: до +2"
    assert texts["code_maturity"] == "подключи GitHub: до +2"
    assert "fsp" in texts and "experience" not in texts
    assert [h.max_gain for h in n.hints] == sorted((h.max_gain for h in n.hints), reverse=True)
    best = compute_grade(GradeInputs(experience_months=30, test_theta=3, code_maturity=1), CFG)
    assert "tests" not in {h.signal for h in best.next_grade.hints}


def test_breakdown_carries_evidence_ids():
    eid = uuid.uuid4()
    r = compute_grade(GradeInputs(test_theta=1.5, test_evidence=(eid,)), CFG)
    tests = next(b for b in r.breakdown if b.signal == "tests")
    assert tests.as_json() == {
        "signal": "tests",
        "value": 1.5,
        "points": 2.0,
        "evidence_ids": [str(eid)],
    }


# ---------- интеграция с recompute_profile ----------


@pytest.fixture
def factory(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'g.db'}"
    upgrade_head(url)
    return make_session_factory(make_engine(url))


def _evidence(uid, sid, source, fact_type, details, strength=0.6):
    return Evidence(
        candidate_id=uid, skill_id=sid, source=source, strength=strength,
        observed_at=date(2026, 5, 1), fact_type=fact_type, fact_id=uuid.uuid4(),
        details=details,
    )  # fmt: skip


async def _seed(factory, months=None):
    uid = uuid.uuid4()
    async with session_scope(factory) as s:
        s.add(User(id=uid, email=f"{uid.hex}@x.io", password_hash="x", role="candidate"))
        s.add(
            Candidate(
                user_id=uid,
                pseudonym=f"P{uid.hex}",
                pseudo_id=uid.hex[:12],
                experience_months=months,
            )
        )
        sk = Skill(slug=f"py-{uid.hex[:6]}", name="py", kind="hard", source="core", status="active")
        s.add(sk)
        await s.flush()
        return uid, sk.id


async def test_recompute_writes_grade_and_event_diff(factory):
    uid, sid = await _seed(factory, months=40)
    cfg = TrustConfig.load()
    async with session_scope(factory) as s:
        s.add(_evidence(uid, sid, "test", "test_session", {"theta": 1.5}))
        s.add(_evidence(uid, sid, "fsp", "fsp_result", {"level": "regional", "place": 2}))
        s.add(_evidence(uid, sid, "fsp", "fsp_rank", {"rank": "rank_2"}))
        s.add(_evidence(uid, sid, "github", "repo", {"code_maturity": 0.5}))
    async with session_scope(factory) as s:
        r = await recompute_profile(s, uid, None, cfg, now=NOW)
        assert r.changed
    async with session_scope(factory) as s:
        c = await s.get(Candidate, uid)
        # стаж 5 + регион-призёр 1 + разряд 1 + тесты 2 + код 1 = 10 → middle_plus
        assert (c.grade, c.grade_score, c.grade_confidence) == ("middle_plus", 10.0, 1.0)
        assert {b["signal"] for b in c.grade_breakdown} == {
            "experience", "fsp_achievement", "fsp_rank", "tests", "code_maturity",
        }  # fmt: skip
        assert c.grade_next["grade"] == "senior" and c.grade_next["points_needed"] == 0.5
        ev = [
            o for o in await s.scalars(select(OutboxRecord)) if o.type == "skills.profile.updated"
        ]
        assert ev[-1].payload["payload"]["diff"]["grade"] == {"from": None, "to": "middle_plus"}
        version = c.profile_version
    async with session_scope(factory) as s:  # повтор без изменений ничего не меняет
        r = await recompute_profile(s, uid, None, cfg, now=NOW)
        assert not r.changed and r.profile_version == version


async def test_recompute_grade_change_emits_diff(factory):
    uid, sid = await _seed(factory)
    cfg = TrustConfig.load()
    async with session_scope(factory) as s:
        await recompute_profile(s, uid, None, cfg, now=NOW)
        c = await s.get(Candidate, uid)
        assert c.grade == "intern"
        c.experience_months = 70  # 7 баллов → middle
        await recompute_profile(s, uid, None, cfg, now=NOW)
        assert c.grade == "middle"
        evs = [
            o.payload["payload"]["diff"].get("grade")
            for o in await s.scalars(select(OutboxRecord))
            if o.type == "skills.profile.updated"
        ]
        assert {"from": None, "to": "intern"} in evs and {"from": "intern", "to": "middle"} in evs
