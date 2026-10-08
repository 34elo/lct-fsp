import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from app.candidates.models import Candidate
from app.graph.fsp_ingest import mate_ref, result_id
from app.graph.fsp_models import FspParticipant, FspResultRow, FspTeamMember
from app.graph.fsp_strength import FspStrengthConfig, result_strength
from app.graph.handlers import register
from app.graph.models import Evidence
from app.graph.recompute import recompute_profile
from app.graph.trust import TrustConfig
from app.identity.models import User
from app.taxonomy.models import Discipline, DisciplineSkillRule, Skill
from core_helpers import upgrade_head
from fsp_contracts import new_envelope
from fsp_contracts.events import (
    FspCompetitionsUpdated,
    FspLinked,
    FspResultsImported,
)
from fsp_contracts.fsp import FspCompetition, FspRank, FspResult, FspTeam
from fsp_contracts.fsp import FspTeamMember as TM
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.messaging import QUEUES, Consumer
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import select

CORE = Path(__file__).resolve().parents[1]
CFG = TrustConfig.load()
NOW = datetime(2026, 6, 1, 12, tzinfo=UTC)
D = date(2026, 3, 1)


# --- формулы (ml.md §3.2) -------------------------------------------------------
def test_strength_examples_from_docs():
    cfg = FspStrengthConfig.from_dict({"evidence_sources": {"fsp": {}}})
    # призёр всероссийского финала по алгоритмике: 1.0 · 0.9 · 1.0 · 1.0
    s = result_strength(1.0, level="national", place=2, total=40, stage="final", cfg=cfg)
    assert s == 0.9
    # участник регионального этапа: 1.0 · 0.6 · 0.55 (отборочный 0.85 из yaml применим отдельно)
    assert (
        result_strength(1.0, level="regional", place=None, total=None, stage="final", cfg=cfg)
        == 0.33
    )
    # процентили и потолок
    assert (
        result_strength(1.0, level="international", place=4, total=40, stage="final", cfg=cfg)
        == 0.9
    )
    assert (
        result_strength(1.0, level="national", place=15, total=40, stage="final", cfg=cfg)
        == 0.9 * 0.7
    )
    assert (
        result_strength(1.0, level="international", place=1, total=5, stage="final", cfg=cfg)
        == 0.95
    )
    assert (
        result_strength(1.0, level="national", place=1, total=5, stage="qualifier", cfg=cfg)
        == 0.765
    )


def test_strength_config_matches_scoring_yaml():
    assert CFG.fsp.stage_k["qualifier"] == 0.85 and CFG.fsp.level_k["interregional"] == 0.75


# --- каркас ---------------------------------------------------------------------
@pytest.fixture
def factory(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'f.db'}"
    upgrade_head(url)
    return make_session_factory(make_engine(url))


@pytest.fixture
def consumer(factory):
    consumers = {"core.ingest": Consumer(QUEUES["core.ingest"])}
    register(
        {
            **consumers,
            "core.recompute": Consumer(QUEUES["core.recompute"]),
            "core.handlers": Consumer(QUEUES["core.handlers"]),
        },
        factory,
        CFG,
    )
    return consumers["core.ingest"]


async def _seed(factory):
    uid = uuid.uuid4()
    tag = uid.hex[:6]
    async with session_scope(factory) as s:
        s.add(User(id=uid, email=f"{tag}@x.io", password_hash="x", role="candidate"))
        s.add(Candidate(user_id=uid, pseudonym=f"P{tag}", pseudo_id=tag))
        sk = {
            slug: Skill(slug=f"{slug}-{tag}", name=slug, kind=kind, source="core")
            for slug, kind in (
                ("backend", "hard"),
                ("frontend", "hard"),
                ("python", "hard"),
                ("teamwork", "soft"),
            )
        }
        s.add_all(sk.values())
        s.add(Discipline(slug="product", name="Продуктовое"))
        await s.flush()
        for slug, w, track in (
            ("backend", 0.6, None),
            ("teamwork", 0.8, None),
            ("frontend", 0.5, None),
            ("frontend", 0.7, "web"),
            ("python", 0.6, "ml"),
        ):
            s.add(
                DisciplineSkillRule(
                    discipline="product", skill_id=sk[slug].id, weight=w, track=track
                )
            )
        return uid, tag, {k: v.id for k, v in sk.items()}


def _comp(cid="c-002", level="national"):
    return FspCompetition(
        id=cid,
        title="Кубок России, продуктовое программирование",
        discipline="product",
        level=level,
        format="offline",
        start_date=date(2026, 2, 27),
        end_date=D,
        status="finished",
        tracks=["web"],
    )


def _res(cid="c-002", stage="final", place=2, role="captain", track="web", team="t1"):
    return FspResult(
        competition_id=cid,
        discipline="product",
        stage=stage,
        team_id=team if role != "individual" else None,
        team_role=role,
        place=place,
        participants_total=40,
        score=87.5,
        track=track,
        date=D,
    )


def _team():
    return FspTeam(
        id="t1",
        name="Северное сияние",
        competition_id="c-002",
        members=[
            TM(participant_id=p, role=r)
            for p, r in (("p-anya", "captain"), ("p-m01", "member"), ("p-m02", "member"))
        ],
    )


async def _send(consumer, type_, payload, *, msg=None):
    env = new_envelope(type_, "fsp-connector", payload)
    if msg is not None:
        env = msg
    await consumer.dispatch(env)
    return env


async def _fsp_ev(factory, uid):
    async with factory() as s:
        return list(
            await s.scalars(
                select(Evidence).where(Evidence.candidate_id == uid, Evidence.source == "fsp")
            )
        )


async def _outbox(factory, type_):
    async with factory() as s:
        return list(await s.scalars(select(OutboxRecord).where(OutboxRecord.type == type_)))


async def _import(consumer, uid, *, results=None, ranks=(), new=True, teams=None):
    return await _send(
        consumer,
        "fsp.results.imported",
        FspResultsImported(
            candidate_id=uid,
            participant_id="p-anya",
            results=[_res()] if results is None else results,
            ranks=list(ranks),
            teams=[_team()] if teams is None else teams,
            new=new,
        ),
    )


# --- сценарии -------------------------------------------------------------------
async def test_import_builds_evidence_with_details_for_grade_and_team_signals(factory, consumer):
    uid, tag, sk = await _seed(factory)
    await _send(
        consumer,
        "fsp.linked",
        FspLinked(candidate_id=uid, participant_id="p-anya", verified=True, method="oauth"),
    )
    await _send(
        consumer, "fsp.competitions.updated", FspCompetitionsUpdated(competitions=[_comp()])
    )
    await _import(
        consumer,
        uid,
        ranks=[FspRank(discipline="product", rank="cms", assigned_at=date(2025, 6, 1))],
    )

    evs = await _fsp_ev(factory, uid)
    by_skill = {(e.skill_id, e.fact_type): e for e in evs}
    # frontend: max(0.5, 0.7 трека web) · 0.9 · 1.0 · 1.0; teamwork (soft) и python (трек ml) — нет
    assert by_skill[(sk["frontend"], "fsp_result")].strength == 0.63
    assert by_skill[(sk["backend"], "fsp_result")].strength == 0.54
    assert (sk["teamwork"], "fsp_result") not in by_skill and (
        sk["python"],
        "fsp_result",
    ) not in by_skill
    d = by_skill[(sk["backend"], "fsp_result")].details
    assert d["level"] == "national" and d["place"] == 2 and d["participants"] == 40
    assert d["stage"] == "final" and d["final"] is True
    assert d["team_role"] == "captain" and d["team_size"] == 3
    assert d["teammates"] == sorted([mate_ref("p-m01"), mate_ref("p-m02")])
    assert "p-m01" not in str(d) and "капитан" in d["label"] and "2 место из 40" in d["label"]
    assert all(e.verified for e in evs)
    (rank_ev,) = [e for e in evs if e.fact_type == "fsp_rank"]
    assert rank_ev.strength == 0 and rank_ev.details["rank"] == "cms"

    # вход в грейд и командные сигналы (recompute читает именно эти details)
    async with session_scope(factory) as s:
        await recompute_profile(s, uid, None, CFG, now=NOW)
    async with factory() as s:
        cand = await s.get(Candidate, uid)
        sigs = {b["signal"]: b for b in cand.grade_breakdown}
        assert sigs["fsp_achievement"]["points"] == 3.0 and sigs["fsp_rank"]["points"] == 2.5
        assert cand.team_signals["leadership"]["value"] > 0
        assert cand.team_signals["teamwork"]["value"] > 0


async def test_redelivery_and_replay_change_nothing(factory, consumer):
    uid, _, _ = await _seed(factory)
    await _send(
        consumer, "fsp.competitions.updated", FspCompetitionsUpdated(competitions=[_comp()])
    )
    env = await _import(consumer, uid)
    before = {e.id: (e.strength, e.details) for e in await _fsp_ev(factory, uid)}
    n_changed = len(await _outbox(factory, "evidence.changed"))
    n_recompute = len(await _outbox(factory, "core.recompute"))
    assert before and n_changed == 1

    await consumer.dispatch(env)  # та же доставка: inbox
    await _import(consumer, uid)  # новое сообщение с теми же данными: upsert ничего не меняет
    await _send(
        consumer, "fsp.competitions.updated", FspCompetitionsUpdated(competitions=[_comp()])
    )
    assert {e.id: (e.strength, e.details) for e in await _fsp_ev(factory, uid)} == before
    assert len(await _outbox(factory, "evidence.changed")) == n_changed
    assert len(await _outbox(factory, "core.recompute")) == n_recompute
    async with factory() as s:
        assert len(list(await s.scalars(select(FspResultRow)))) == 1


async def test_result_before_calendar_gets_evidence_when_competition_arrives(factory, consumer):
    uid, _, _ = await _seed(factory)
    await _import(consumer, uid)
    assert await _fsp_ev(factory, uid) == []  # уровня соревнования ещё нет
    await _send(
        consumer, "fsp.competitions.updated", FspCompetitionsUpdated(competitions=[_comp()])
    )
    assert {e.fact_type for e in await _fsp_ev(factory, uid)} == {"fsp_result"}
    # смена уровня в календаре обновляет силу
    await _send(
        consumer,
        "fsp.competitions.updated",
        FspCompetitionsUpdated(competitions=[_comp(level="international")]),
    )
    assert {e.details["level"] for e in await _fsp_ev(factory, uid)} == {"international"}


async def test_full_sync_deactivates_vanished_results_but_incremental_does_not(factory, consumer):
    uid, _, _ = await _seed(factory)
    comps = [_comp(), _comp("c-003", "regional")]
    await _send(consumer, "fsp.competitions.updated", FspCompetitionsUpdated(competitions=comps))
    await _import(
        consumer,
        uid,
        results=[_res(), _res("c-003", stage="qualifier", place=9, role="individual")],
    )
    assert len([e for e in await _fsp_ev(factory, uid) if e.is_active]) > 0
    await _import(consumer, uid, results=[_res()], new=False)  # инкремент: ничего не гасим
    assert {e.details["competition_id"] for e in await _fsp_ev(factory, uid) if e.is_active} == {
        "c-002",
        "c-003",
    }
    await _import(consumer, uid, results=[_res()], new=True)  # полная выгрузка без c-003
    active = [e for e in await _fsp_ev(factory, uid) if e.is_active]
    assert {e.details["competition_id"] for e in active} == {"c-002"}
    async with factory() as s:  # строка факта осталась (аудит)
        rows = {r.competition_id: r.is_active for r in await s.scalars(select(FspResultRow))}
    assert rows == {"c-002": True, "c-003": False}
    await _import(
        consumer,
        uid,
        results=[_res(), _res("c-003", stage="qualifier", place=9, role="individual")],
    )
    assert len([e for e in await _fsp_ev(factory, uid) if e.is_active]) == len(
        await _fsp_ev(factory, uid)
    )


async def test_linked_stores_participant_requests_sync_and_updates_verified(factory, consumer):
    uid, _, _ = await _seed(factory)
    await _send(
        consumer, "fsp.competitions.updated", FspCompetitionsUpdated(competitions=[_comp()])
    )
    linked = FspLinked(candidate_id=uid, participant_id="p-anya", verified=False, method="manual")
    env = await _send(consumer, "fsp.linked", linked)
    await _send(consumer, "fsp.linked", linked)  # повтор по содержанию
    cmds = await _outbox(factory, "fsp.sync")
    assert len(cmds) == 1 and cmds[0].payload["payload"]["reason"] == "linked"
    async with factory() as s:
        assert (await s.get(FspParticipant, uid)).verified is False
    await _import(consumer, uid)
    assert not any(e.verified for e in await _fsp_ev(factory, uid))
    await _send(
        consumer,
        "fsp.linked",
        FspLinked(candidate_id=uid, participant_id="p-anya", verified=True, method="code"),
    )
    assert all(e.verified for e in await _fsp_ev(factory, uid))
    assert len(await _outbox(factory, "fsp.sync")) == 1  # синхронизацию просим один раз
    await consumer.dispatch(env)


async def test_team_member_gets_candidate_id_when_teammate_links_later(factory, consumer):
    uid, _, _ = await _seed(factory)
    mate = uuid.uuid4()
    async with session_scope(factory) as s:
        s.add(User(id=mate, email=f"{mate.hex}@x.io", password_hash="x", role="candidate"))
        s.add(Candidate(user_id=mate, pseudonym=f"P{mate.hex}", pseudo_id=mate.hex[:12]))
    await _import(consumer, uid)
    await _send(
        consumer,
        "fsp.linked",
        FspLinked(candidate_id=mate, participant_id="p-m01", verified=True, method="oauth"),
    )
    async with factory() as s:
        m = {x.participant_id: x.candidate_id for x in await s.scalars(select(FspTeamMember))}
    assert m["p-m01"] == mate and m["p-m02"] is None


async def test_unknown_candidate_is_ignored(factory, consumer):
    ghost = uuid.uuid4()
    await _send(
        consumer,
        "fsp.linked",
        FspLinked(candidate_id=ghost, participant_id="p-x", verified=True, method="oauth"),
    )
    await _import(consumer, ghost)
    async with factory() as s:
        assert list(await s.scalars(select(FspResultRow))) == []


async def test_best_rank_wins_in_grade(factory, consumer):
    uid, _, _ = await _seed(factory)
    await _import(
        consumer, uid, results=[], teams=[], ranks=[FspRank(discipline="product", rank="rank_1")]
    )
    async with session_scope(factory) as s:
        await recompute_profile(s, uid, None, CFG, now=NOW)
    async with factory() as s:
        sig = {b["signal"]: b for b in (await s.get(Candidate, uid)).grade_breakdown}
        assert sig["fsp_rank"]["value"] == "rank_1"
    assert result_id("p", "c", "final") == result_id("p", "c", "final")
