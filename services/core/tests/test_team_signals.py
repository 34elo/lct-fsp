"""Командные сигналы L/T/R/G и K_soft: примеры из skills.md §8."""

import subprocess
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from app.candidates.models import Candidate
from app.graph.models import Evidence
from app.graph.recompute import recompute_profile
from app.graph.team_signals import (
    FspPerformance,
    RepoFact,
    TeamConfig,
    compute_team_signals,
    k_soft,
    strength_label,
)
from app.graph.trust import TrustConfig
from app.identity.models import User
from app.taxonomy.models import Skill
from fsp_platform.db import make_engine, make_session_factory, session_scope

CORE = Path(__file__).resolve().parents[1]
CFG = TeamConfig.load()
TODAY = date(2026, 6, 1)
NOW = datetime(2026, 6, 1, 12, tzinfo=UTC)


def _perf(**kw):
    base = {"fact_id": uuid.uuid4(), "observed_at": TODAY, "level": "regional"}
    return FspPerformance(**{**base, **kw})


def test_config_loaded_from_scoring_yaml():
    assert CFG == TeamConfig()


def test_leadership_example_from_docs():
    perfs = [
        _perf(level="national", place=2, participants=60, team_role="captain", team_size=5,
              observed_at=date(2025, 6, 1)),
        _perf(level="regional", place=5, participants=40, team_role="captain", team_size=4),
    ]  # fmt: skip
    s = compute_team_signals(perfs, [], TODAY, CFG)
    assert s.values["leadership"] == pytest.approx(0.47, abs=0.01)
    assert [f.contribution for f in s.facts["leadership"]] == pytest.approx([0.36, 0.18], abs=0.01)


def test_leadership_team_size_and_maintainer():
    solo = compute_team_signals([_perf(team_role="captain", team_size=1)], [], TODAY, CFG)
    assert "leadership" not in solo.values  # капитан одиночки — не лидерство
    two = compute_team_signals([_perf(team_role="captain", team_size=2, place=1)], [], TODAY, CFG)
    assert two.values["leadership"] == pytest.approx(0.5 * 0.6 * 1 * 0.25)
    repo = RepoFact(uuid.uuid4(), maintainer=True, external_authors_merged=5, active_authors=3)
    assert compute_team_signals([], [repo], TODAY, CFG).values["leadership"] == pytest.approx(0.15)
    not_maint = RepoFact(uuid.uuid4(), maintainer=False, external_authors_merged=50)
    assert compute_team_signals([], [not_maint], TODAY, CFG).values == {}


def test_leadership_decays():
    new = compute_team_signals([_perf(team_role="captain", team_size=5, place=1)], [], TODAY, CFG)
    old = compute_team_signals(
        [_perf(team_role="captain", team_size=5, place=1, observed_at=date(2023, 6, 1))],
        [], TODAY, CFG,
    )  # fmt: skip
    assert old.values["leadership"] == pytest.approx(new.values["leadership"] * 0.5, rel=0.01)


def test_teamwork_noisy_or_and_mates_bonus():
    p1 = _perf(level="national", team_role="member", team_size=3, teammates=("a", "b"))
    p2 = _perf(level="regional", team_role="member", team_size=3, teammates=("a", "c"))
    s = compute_team_signals([p1, p2], [], TODAY, CFG)
    tau1, tau2, b = 0.25 * 0.9, 0.25 * 0.6, 0.05 * 2  # напарники a, b, c
    assert s.values["teamwork"] == pytest.approx(1 - (1 - tau1) * (1 - tau2) * (1 - b), abs=1e-3)


def test_teamwork_individual_none_and_repo_bonus_and_cap():
    assert compute_team_signals([_perf(team_role="individual")], [], TODAY, CFG).values == {}
    shared = RepoFact(uuid.uuid4(), active_authors=3)
    s = compute_team_signals([], [shared], TODAY, CFG)
    assert s.values["teamwork"] == pytest.approx(0.05)
    mates = tuple(str(i) for i in range(8))
    p = _perf(level="international", team_role="member", team_size=9, teammates=mates)
    s2 = compute_team_signals([p], [shared], TODAY, CFG)
    assert s2.values["teamwork"] == pytest.approx(1 - (1 - 0.25) * (1 - 0.15))  # b ≤ 0.15


def test_results_bayesian_average():
    assert "results" not in compute_team_signals([_perf(final=True)], [], TODAY, CFG).values
    two = [_perf(final=True), _perf(place=30, participants=40)]
    assert compute_team_signals(two, [], TODAY, CFG).values["results"] == pytest.approx(2 / 5)
    four = [_perf(place=1, participants=10)] * 3 + [_perf(place=9, participants=10)]
    assert compute_team_signals(four, [], TODAY, CFG).values["results"] == pytest.approx(
        4 / 7, abs=1e-3
    )
    top25 = [_perf(place=5, participants=20), _perf(place=6, participants=20)]
    assert compute_team_signals(top25, [], TODAY, CFG).values["results"] == pytest.approx(2 / 5)


def test_growth_needs_enough_history_and_threshold():
    def seasons(places, years):
        return [
            _perf(place=p, participants=100, observed_at=date(y, 6, 1))
            for p, y in zip(places, years, strict=True)
        ]

    assert (
        "growth" not in compute_team_signals(seasons([50, 20], [2024, 2025]), [], TODAY, CFG).values
    )
    same_year = seasons([50, 40, 30], [2025, 2025, 2025])
    assert "growth" not in compute_team_signals(same_year, [], TODAY, CFG).values
    up = compute_team_signals(seasons([60, 40, 20], [2024, 2025, 2026]), [], TODAY, CFG)
    assert up.values["growth"] == pytest.approx(0.5 + 2 * 0.2)  # slope 0.2 в год
    flat = seasons([40, 40, 40], [2024, 2025, 2026])
    assert "growth" not in compute_team_signals(flat, [], TODAY, CFG).values  # G=0.5 < 0.6
    down = seasons([20, 40, 60], [2024, 2025, 2026])
    assert "growth" not in compute_team_signals(down, [], TODAY, CFG).values  # не штрафуем


def test_no_facts_no_signals():
    s = compute_team_signals([], [], TODAY, CFG)
    assert s.values == {} and s.as_json() is None


def test_k_soft_example_from_docs():
    k = k_soft({"leadership": 0.47, "teamwork": 0.6, "results": 0.6}, "middle", CFG)
    assert k == pytest.approx(1.039, abs=1e-3)
    assert min(1.0, 0.85 * k) == pytest.approx(0.883, abs=1e-3)


def test_k_soft_ceiling_emphasis_and_absence():
    assert k_soft({}, "senior", CFG) == 1.0  # отсутствие сигналов не штрафует
    full = dict.fromkeys(("leadership", "teamwork", "results", "growth"), 1.0)
    assert k_soft(full, "middle", CFG) == pytest.approx(1.06)
    assert k_soft(full, "lead", CFG) == pytest.approx(1.12)
    assert k_soft(full, "middle", CFG, emphasis={"leadership"}) == pytest.approx(1.08)
    # α_L удваивается: 0.04·0.5 + 0.03·0 — ниже потолка
    assert k_soft({"leadership": 0.5}, "middle", CFG, emphasis={"leadership"}) == pytest.approx(
        1.02
    )
    assert k_soft(full, "lead", CFG, emphasis={"leadership"}) == pytest.approx(1.12)  # ≤ 0.12


def test_grade_groups():
    s = {"leadership": 1.0}
    assert k_soft(s, "junior", CFG) == pytest.approx(1.01)
    assert k_soft(s, "middle_plus", CFG) == pytest.approx(1.02)
    assert k_soft(s, "senior", CFG) == pytest.approx(1.04)


@pytest.mark.parametrize(
    ("v", "label"),
    [(0.7, "strong"), (0.6, "strong"), (0.45, "present"), (0.3, "present"), (0.29, None)],
)
def test_strength_label(v, label):
    assert strength_label(v) == label


# ---- пересчёт профиля ----


@pytest.fixture
def factory(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 't.db'}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url}", "upgrade", "head"],
        cwd=CORE, check=True, capture_output=True,
    )  # fmt: skip
    return make_session_factory(make_engine(url))


def _ev(uid, sid, fact_id, details, observed=date(2026, 5, 1), verified=True):
    return Evidence(
        candidate_id=uid, skill_id=sid, source="fsp", strength=0.7, observed_at=observed,
        fact_type="fsp_result", fact_id=fact_id, details=details, verified=verified,
    )  # fmt: skip


async def _seed(factory):
    uid = uuid.uuid4()
    async with session_scope(factory) as s:
        s.add(User(id=uid, email=f"{uid.hex}@x.io", password_hash="x", role="candidate"))
        s.add(
            Candidate(
                user_id=uid, pseudonym=f"P{uid.hex}", pseudo_id=uid.hex[:12],
                team_signals={"management_confirmed": True},
            )
        )  # fmt: skip
        sks = [Skill(slug=f"s{i}-{uid.hex[:6]}", name="s", kind="hard", source="core",
                     status="active") for i in range(2)]  # fmt: skip
        s.add_all(sks)
        await s.flush()
        return uid, [k.id for k in sks]


async def test_recompute_writes_signals_dedups_facts_and_feeds_grade(factory):
    uid, (s1, s2) = await _seed(factory)
    cfg = TrustConfig.load()
    cap = {"level": "national", "place": 2, "participants": 60, "final": True,
           "team_role": "captain", "team_size": 5, "teammates": ["a", "b", "c", "d"]}  # fmt: skip
    fid = uuid.uuid4()
    async with session_scope(factory) as s:
        # одно соревнование, два навыка: считается один раз
        s.add_all([_ev(uid, s1, fid, cap), _ev(uid, s2, fid, cap)])
        # неверифицированная привязка не даёт сигналов
        s.add(_ev(uid, s1, uuid.uuid4(), {**cap, "place": 1}, verified=False))
        await s.flush()
        await recompute_profile(s, uid, None, cfg, now=NOW)
        c = await s.get(Candidate, uid)
        ts = c.team_signals
        assert ts["management_confirmed"] is True
        assert ts["leadership"]["value"] == pytest.approx(
            0.5 * 0.9 * 1 * 1 * 0.5 ** (31 / 365.25 / 3), abs=1e-3
        )
        assert len(ts["leadership"]["facts"]) == 1
        assert "teammates" not in str(ts)  # ПДн/идентификаторы напарников не сохраняются
        lead_pts = {b["signal"]: b["points"] for b in c.grade_breakdown}["leadership"]
        assert lead_pts == pytest.approx(1.5 * ts["leadership"]["value"], abs=0.01)
        v = c.profile_version
        r = await recompute_profile(s, uid, None, cfg, now=NOW)  # повтор не меняет результат
        assert not r.changed and c.profile_version == v


async def test_recompute_drops_signals_when_facts_gone(factory):
    uid, (s1, _) = await _seed(factory)
    cfg = TrustConfig.load()
    async with session_scope(factory) as s:
        ev = _ev(
            uid, s1, uuid.uuid4(), {"level": "national", "team_role": "captain", "team_size": 5}
        )
        s.add(ev)
        await s.flush()
        await recompute_profile(s, uid, None, cfg, now=NOW)
        c = await s.get(Candidate, uid)
        assert "leadership" in c.team_signals
        ev.is_active = False
        await s.flush()
        await recompute_profile(s, uid, None, cfg, now=NOW)
        assert c.team_signals == {"management_confirmed": True}
