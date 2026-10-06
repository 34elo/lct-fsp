"""E22-4: грейды, кулдауны, история, доказательства `test`, события (§5, §11).

ADR-025: приглашение бонусного этапа (п.2), экспресс-режим E32-4a (п.7).
"""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from app.assessment import families as registry
from app.assessment import grading
from app.assessment import service as svc
from app.assessment.config import load_config
from app.assessment.families.base import BaseFamily, Item, Kind
from app.assessment.models import Attempt, Grade
from app.graph.models import Evidence
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from core_helpers import assert_foreign_is_404, register
from fsp_contracts.assessment import AttemptFinished, CategoryChanged, SkillType, TestGrade
from fsp_platform.db import session_scope
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import select

CFG = load_config()
TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"
J, M, S = TestGrade.junior, TestGrade.middle, TestGrade.senior


class _Fake(BaseFamily):
    kind = Kind.exact
    skill_type = SkillType.hard

    def __init__(self, slug: str, skill: str, level: int):
        self.slug, self.skill, self.level = slug, skill, level

    def generate(self, rng, world) -> Item:
        return Item(Kind.exact, f"{self.slug}: введите 1", "1")


@pytest.fixture
def fake_bank(monkeypatch):
    reg = {}
    for skill in ["python", "sql", "algorithms", "estimation", "debugging"]:
        for level in range(1, 6):
            for j in range(6):
                f = _Fake(f"t_{skill}_{level}_{j}", skill, level)
                reg[f.slug] = f
    monkeypatch.setattr(registry, "REGISTRY", reg)


@pytest.fixture
async def taxonomy_loaded(factory):
    async with session_scope(factory) as s:
        await tax.sync(s, load_taxonomy(TAXONOMY))


def _uid(api, h) -> uuid.UUID:
    return uuid.UUID(jwt.decode(h["Authorization"][7:], options={"verify_signature": False})["sub"])


def _start(api, h, grade="middle", profession="backend"):
    return api.post(
        "/assessment/attempts", json={"profession": profession, "declared_grade": grade}, headers=h
    )


def _run(api, h, aid, answer="1"):
    while True:
        body = api.get(f"/assessment/attempts/{aid}/next", headers=h).json()
        if body["done"]:
            return
        r = api.post(
            f"/assessment/attempts/{aid}/answers",
            json={"response_id": body["response_id"], "answer": answer},
            headers=h,
        )
        assert r.status_code == 200, r.text


async def _events(factory, type_: str) -> list[OutboxRecord]:
    async with session_scope(factory) as s:
        return list(
            await s.scalars(
                select(OutboxRecord).where(OutboxRecord.type == type_).order_by(OutboxRecord.id)
            )
        )


async def _set_cooldown_past(factory, uid, profession="backend"):
    async with session_scope(factory) as s:
        row = await s.get(Grade, (uid, profession))
        row.next_change_at = datetime.now(UTC) - timedelta(days=1)


async def test_pass_writes_grade_evidence_and_events(api, factory, taxonomy_loaded, fake_bank):
    h = register(api)
    uid = _uid(api, h)
    aid = _start(api, h).json()["id"]
    _run(api, h, aid)
    async with session_scope(factory) as s:
        row = await s.get(Grade, (uid, "backend"))
        att = await s.get(Attempt, uuid.UUID(aid))
        assert (row.grade, row.source, row.attempt_id) == ("middle", "test", att.id)
        assert row.theta == att.theta and 0 <= row.band_position <= 1
        assert row.integrity == 1.0 and not row.needs_confirmation
        span = (row.valid_until - row.confirmed_at).days
        assert span == 365 and (row.next_change_at - row.confirmed_at).days == 90
        ev = list(await s.scalars(select(Evidence).where(Evidence.candidate_id == uid)))
        assert ev and {e.source for e in ev} == {"test"} and {e.fact_id for e in ev} == {att.id}
        assert all(e.strength == pytest.approx(0.8) and e.details["theta"] for e in ev)
    (fin,) = await _events(factory, "assessment.attempt.finished")
    f = AttemptFinished.model_validate(fin.payload["payload"])
    assert (f.result, f.grade, f.declared_grade, f.stage) == ("passed", M, M, "bonus")
    cat = await _events(factory, "candidate.category.changed")
    assert len(cat) == 1
    c = CategoryChanged.model_validate(cat[0].payload["payload"])
    assert [(x.profession, x.grade) for x in c.categories] == [("backend", M)]
    res = api.get(f"/assessment/attempts/{aid}", headers=h).json()["result"]
    assert res["grade"] == "middle" and res["by_skill"] and res["theta"] == pytest.approx(att.theta)
    # повторное чтение и ответ после завершения событий не добавляют
    _run(api, h, aid)
    late = api.post(
        f"/assessment/attempts/{aid}/answers",
        json={"response_id": str(uuid.uuid4()), "answer": "1"},
        headers=h,
    )
    assert late.status_code == 404
    assert len(await _events(factory, "assessment.attempt.finished")) == 1


async def test_bonus_invites_instead_of_upgrade(api, factory, taxonomy_loaded, fake_bank):
    """ADR-025 п.2: бонус не меняет грейд, а приглашает на отдельный тест следующего грейда."""
    h = register(api)
    uid = _uid(api, h)
    aid = _start(api, h).json()["id"]
    _run(api, h, aid)
    out = api.get(f"/assessment/attempts/{aid}", headers=h).json()
    assert out["invited_grade"] == "senior" and out["result"]["grade"] == "middle"
    expires = datetime.fromisoformat(out["invite_expires_at"])
    assert (expires - datetime.now(UTC)).days in (29, 30)
    (fin,) = await _events(factory, "assessment.attempt.finished")
    f = AttemptFinished.model_validate(fin.payload["payload"])
    assert (f.grade, f.invited_grade, f.stage) == (M, S, "bonus")
    async with session_scope(factory) as s:
        assert (await s.get(Grade, (uid, "backend"))).grade == "middle"
    assert len(await _events(factory, "candidate.category.changed")) == 1

    # тест по приглашению: без кулдауна смены грейда, повтор возвращает ту же попытку
    assert_foreign_is_404(api, "POST", f"/assessment/attempts/{aid}/upgrade", register(api))
    r = api.post(f"/assessment/attempts/{aid}/upgrade", headers=h)
    assert r.status_code == 201, r.text
    inv = r.json()
    assert (inv["declared_grade"], inv["status"], inv["invited_by"]) == ("senior", "active", aid)
    again = api.post(f"/assessment/attempts/{aid}/upgrade", headers=h)
    assert again.status_code == 201 and again.json()["id"] == inv["id"]
    src = api.get(f"/assessment/attempts/{aid}", headers=h).json()
    assert src["invite_attempt_id"] == inv["id"]
    async with session_scope(factory) as s:
        assert (await s.get(Grade, (uid, "backend"))).grade == "middle"  # ещё не пройден
    _run(api, h, inv["id"])
    async with session_scope(factory) as s:
        row = await s.get(Grade, (uid, "backend"))
        assert (row.grade, str(row.attempt_id)) == ("senior", inv["id"])
    last = CategoryChanged.model_validate(
        (await _events(factory, "candidate.category.changed"))[-1].payload["payload"]
    )
    assert [(c.profession, c.grade) for c in last.categories] == [("backend", S)]


async def test_invited_failure_keeps_grade_and_retry_open(api, factory, taxonomy_loaded, fake_bank):
    """Провал приглашённого теста не меняет грейд и не закрывает повтор (ADR-025 п.2)."""
    h = register(api)
    uid = _uid(api, h)
    aid = _start(api, h).json()["id"]
    _run(api, h, aid)
    inv = api.post(f"/assessment/attempts/{aid}/upgrade", headers=h).json()
    _run(api, h, inv["id"], answer="0")
    assert api.get(f"/assessment/attempts/{inv['id']}", headers=h).json()["status"] == "failed"
    async with session_scope(factory) as s:
        assert (await s.get(Grade, (uid, "backend"))).grade == "middle"
        cds = await grading.cooldowns(s, uid, "backend", CFG)
        assert all(c.kind == "change" for c in cds)  # повтора после неудачи нет
    hist = api.get("/assessment/history", headers=h).json()
    assert hist["retries"] == []


async def test_invite_errors(api, factory, taxonomy_loaded, fake_bank):
    h = register(api)
    uid = _uid(api, h)
    aid = _start(api, h, grade="junior").json()["id"]
    _run(api, h, aid, answer="0")
    r = api.post(f"/assessment/attempts/{aid}/upgrade", headers=h)
    assert (r.status_code, r.json()["code"]) == (409, "no_invite")

    h2 = register(api)
    uid = _uid(api, h2)
    aid = _start(api, h2).json()["id"]
    _run(api, h2, aid)
    async with session_scope(factory) as s:
        att = await s.get(Attempt, uuid.UUID(aid))
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        att.plan = {**att.plan, "invite_expires_at": past}
    r = api.post(f"/assessment/attempts/{aid}/upgrade", headers=h2)
    assert (r.status_code, r.json()["code"]) == (409, "invite_expired")
    async with session_scope(factory) as s:
        att = await s.get(Attempt, uuid.UUID(aid))
        att.plan = {**att.plan, "invite_expires_at": None}
        (await s.get(Grade, (uid, "backend"))).grade = "senior"
    r = api.post(f"/assessment/attempts/{aid}/upgrade", headers=h2)
    assert (r.status_code, r.json()["code"]) == (409, "invite_stale")


async def test_failure_keeps_grade_and_sets_retry_cooldown(
    api, factory, taxonomy_loaded, fake_bank
):
    h = register(api)
    uid = _uid(api, h)
    aid = _start(api, h).json()["id"]
    _run(api, h, aid, answer="0")
    async with session_scope(factory) as s:
        assert await s.get(Grade, (uid, "backend")) is None  # без грейда нечего «понижать»
    (fin,) = await _events(factory, "assessment.attempt.finished")
    f = AttemptFinished.model_validate(fin.payload["payload"])
    assert (f.result, f.grade) == ("failed", None)
    assert await _events(factory, "candidate.category.changed") == []
    r = _start(api, h)
    assert (r.status_code, r.json()["code"]) == (409, "cooldown")
    until = datetime.fromisoformat(r.json()["detail"].split()[0])
    assert 29 <= (until - datetime.now(UTC)).days <= 30
    assert _start(api, h, grade="junior").status_code == 201  # грейд ниже — сразу
    hist = api.get("/assessment/history", headers=h).json()
    assert [(x["profession"], x["grade"]) for x in hist["retries"]] == [("backend", "middle")]
    assert {a["status"] for a in hist["attempts"]} == {"failed", "active"}
    # через 30 дней повтор открыт
    async with session_scope(factory) as s:
        a = await s.get(Attempt, uuid.UUID(aid))
        a.finished_at = datetime.now(UTC) - timedelta(days=31)
        for x in await s.scalars(select(Attempt).where(Attempt.status == "active")):
            x.status, x.finished_at = "abandoned", datetime.now(UTC)
    assert _start(api, h).status_code == 201


async def test_grade_change_cooldown_90_days(api, factory, taxonomy_loaded, fake_bank):
    h = register(api)
    uid = _uid(api, h)
    aid = _start(api, h, grade="junior").json()["id"]
    _run(api, h, aid)  # junior подтверждён; повышение до middle кандидат не принял
    r = _start(api, h, grade="middle")
    assert (r.status_code, r.json()["code"]) == (409, "cooldown")
    until = datetime.fromisoformat(r.json()["detail"].split()[0])
    assert 89 <= (until - datetime.now(UTC)).days <= 90
    assert _start(api, h, grade="junior").status_code == 201  # подтверждение того же грейда
    await _set_cooldown_past(factory, uid)
    async with session_scope(factory) as s:
        for x in await s.scalars(select(Attempt).where(Attempt.status == "active")):
            x.status, x.finished_at = "abandoned", datetime.now(UTC)
    assert _start(api, h, grade="middle").status_code == 201


async def test_lower_grade_after_failure_once(factory, taxonomy_loaded):
    now = datetime.now(UTC)
    async with session_scope(factory) as s:
        uid = uuid.uuid4()
        from app.candidates.models import Candidate
        from app.identity.models import User

        s.add(User(id=uid, email=f"{uid.hex}@x.io", password_hash="x", role="candidate"))
        s.add(Candidate(user_id=uid, pseudonym=f"P{uid.hex}", pseudo_id=uid.hex[:12]))
        await s.flush()
        await svc.seed_grade(s, uid, "backend", "middle", 0.3, now=now)  # смена закрыта на 90 дней
        s.add(
            Attempt(
                candidate_id=uid,
                profession="backend",
                declared_grade="senior",
                status="failed",
                finished_at=now,
                plan={},
            )
        )
        await s.flush()
        with pytest.raises(Exception) as e:  # повтор senior — через 30 дней
            await grading.check_cooldown(s, uid, "backend", S, CFG, now)
        assert e.value.code == "cooldown"
        await grading.check_cooldown(s, uid, "backend", J, CFG, now)  # ниже — сразу
        s.add(
            Attempt(
                candidate_id=uid,
                profession="backend",
                declared_grade="junior",
                status="passed",
                finished_at=now,
                started_at=now + timedelta(seconds=1),
                plan={},
            )
        )
        await s.flush()
        with pytest.raises(Exception) as e2:  # попытка ниже — одна
            await grading.check_cooldown(s, uid, "backend", J, CFG, now)
        assert e2.value.code == "cooldown"
        await grading.check_cooldown(s, uid, "backend", M, CFG, now)  # подтверждение того же грейда
        cds = await grading.cooldowns(s, uid, "backend", CFG, now)
        assert {c.kind for c in cds} == {"retry", "change"}


async def test_no_downgrade_on_lower_pass(api, factory, taxonomy_loaded, fake_bank):
    h = register(api)
    uid = _uid(api, h)
    api.put("/assessment/survey", json={"profession": "backend"}, headers=h)  # создаёт кандидата
    async with session_scope(factory) as s:
        await svc.seed_grade(s, uid, "backend", "senior", 1.4)
        row = await s.get(Grade, (uid, "backend"))
        row.next_change_at = datetime.now(UTC) - timedelta(days=1)
    before = len(await _events(factory, "candidate.category.changed"))
    aid = _start(api, h, grade="middle").json()["id"]
    _run(api, h, aid)
    async with session_scope(factory) as s:
        row = await s.get(Grade, (uid, "backend"))
        assert row.grade == "senior" and row.source == "seed"  # грейд не понижается и не трогается
    assert len(await _events(factory, "candidate.category.changed")) == before
    (fin,) = await _events(factory, "assessment.attempt.finished")
    assert AttemptFinished.model_validate(fin.payload["payload"]).grade == S


async def test_low_integrity_caps_evidence_and_flags_grade(
    api, factory, taxonomy_loaded, fake_bank
):
    h = register(api)
    uid = _uid(api, h)
    aid = _start(api, h).json()["id"]
    now = datetime.now(UTC)
    async with session_scope(factory) as s:
        att = await s.get(Attempt, uuid.UUID(aid))
        # честность I < 0.6 (считает E22-5); здесь — как если бы попытка уже завершилась с ней
        att.integrity = 0.5
    _run(api, h, aid)
    async with session_scope(factory) as s:
        att = await s.get(Attempt, uuid.UUID(aid))
        att.integrity = 0.5
        await grading._write_grade(s, att, M, CFG, now, low_confidence=False)
        await grading._write_evidence(s, att, CFG, now)
        row = await s.get(Grade, (uid, "backend"))
        assert row.needs_confirmation and row.integrity == 0.5
        ev = list(await s.scalars(select(Evidence).where(Evidence.candidate_id == uid)))
        assert ev and all(e.strength <= 0.59 for e in ev)
    got = await _grade_dto(factory, uid)
    assert got.needs_confirmation


async def _grade_dto(factory, uid):
    async with session_scope(factory) as s:
        return await svc.get_grade(s, uid, "backend")


def test_band_position_matches_service():
    for g in (J, M, S):
        for th in (-2.0, -0.7, 0.0, 0.4, 1.0, 1.6, 3.0):
            assert grading.band_position(g, th, CFG) == pytest.approx(svc._band_position(g, th))


# --- E32-4a: экспресс-режим (ADR-025 п.7) -----------------------------------------------------


def _start_express(api, h, grade="middle"):
    return api.post(
        "/assessment/attempts",
        json={"profession": "backend", "declared_grade": grade, "mode": "express"},
        headers=h,
    )


def test_express_config_bounds():
    from app.assessment import sprt

    ex = CFG.for_mode("express")
    assert (ex.min_items, ex.max_items, ex.bonus_enabled, ex.pilot_slots) == (6, 8, False, 0)
    lo, hi = sprt.bounds(ex)
    assert hi == pytest.approx(1.735, abs=1e-3) and lo == pytest.approx(-1.735, abs=1e-3)
    assert CFG.for_mode("standard") is CFG


async def test_express_pass_marks_grade_and_event(api, factory, taxonomy_loaded, fake_bank):
    h = register(api)
    uid = _uid(api, h)
    r = _start_express(api, h)
    assert r.status_code == 201, r.text
    assert r.json()["mode"] == "express"
    aid = r.json()["id"]
    _run(api, h, aid)
    out = api.get(f"/assessment/attempts/{aid}", headers=h).json()
    # 6 заданий (минимум), без бонуса и приглашения
    assert (out["answered"], out["stage"], out["invited_grade"]) == (6, "main", None)
    assert out["result"]["grade"] == "middle"
    async with session_scope(factory) as s:
        (g,) = await svc.get_grades(s, uid)
        assert (g.grade, g.mode, g.source) == (M, "express", "test")
    (fin,) = await _events(factory, "assessment.attempt.finished")
    f = AttemptFinished.model_validate(fin.payload["payload"])
    assert (f.mode, f.stage, f.invited_grade, f.grade) == ("express", "main", None, M)


async def test_standard_replaces_express_without_cooldown(api, factory, taxonomy_loaded, fake_bank):
    h = register(api)
    uid = _uid(api, h)
    _run(api, h, _start_express(api, h).json()["id"])
    # обычный тест на грейд ниже: кулдаун смены грейда экспресса не держит, грейд заменяется
    r = _start(api, h, grade="junior")
    assert r.status_code == 201, r.text
    _run(api, h, r.json()["id"])
    async with session_scope(factory) as s:
        row = await s.get(Grade, (uid, "backend"))
        assert (row.grade, row.mode) == ("junior", "standard")


async def test_express_does_not_override_standard(api, factory, taxonomy_loaded, fake_bank):
    h = register(api)
    uid = _uid(api, h)
    _run(api, h, _start(api, h).json()["id"])  # обычный middle
    r = _start_express(api, h, grade="senior")
    assert (r.status_code, r.json()["code"]) == (409, "cooldown")  # правила грейда те же
    await _set_cooldown_past(factory, uid)
    _run(api, h, _start_express(api, h, grade="senior").json()["id"])
    async with session_scope(factory) as s:
        row = await s.get(Grade, (uid, "backend"))
        assert (row.grade, row.mode) == ("middle", "standard")


async def test_express_failure_does_not_block_standard(api, factory, taxonomy_loaded, fake_bank):
    h = register(api)
    aid = _start_express(api, h).json()["id"]
    _run(api, h, aid, answer="0")
    assert api.get(f"/assessment/attempts/{aid}", headers=h).json()["status"] == "failed"
    again = _start_express(api, h)
    assert (again.status_code, again.json()["code"]) == (409, "cooldown")
    assert _start(api, h).status_code == 201


async def test_express_disabled_is_422():
    from dataclasses import replace

    from app.assessment import attempts
    from fsp_platform.app import ProblemError

    with pytest.raises(ProblemError) as e:
        await attempts.create_attempt(
            None, uuid.uuid4(), "backend", M, replace(CFG, express_enabled=False), mode="express"
        )
    assert (e.value.status, e.value.code) == (422, "express_disabled")
