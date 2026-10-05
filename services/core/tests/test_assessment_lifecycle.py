"""E22-9: жизненный цикл семейств (assessment.md §7): пороги, тревоги, карантин, пересчёт."""

import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random

import pytest
from app.assessment import attempts, lifecycle
from app.assessment import families as registry
from app.assessment.config import load_config
from app.assessment.families.base import BaseFamily, Item, Kind
from app.assessment.lifecycle import Answer, admission_failures, alarm_reasons, compute_stats
from app.assessment.models import Attempt, FamilyRow, Grade, Response
from app.assessment.psychometrics import p_correct
from app.notifications.models import Notification
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from core_helpers import PASSWORD, register
from fsp_contracts.assessment import FamilyStatusChanged, SkillType
from fsp_platform.db import session_scope
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import select

CFG = load_config()
TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"
T0 = datetime(2026, 9, 1, tzinfo=UTC)


def _good(n: int, b: float = 0.0, seed: int = 1) -> list[Answer]:
    """Исправное семейство: верность растёт с θ (Rasch)."""
    rng = Random(seed)
    out = []
    for i in range(n):
        th = rng.gauss(0.0, 1.0)
        y = 1.0 if rng.random() < p_correct(th, b) else 0.0
        out.append(Answer(score=y, theta=th, seed=i, fsp=i % 2 == 0))
    return out


def _broken(n: int, seed: int = 2) -> list[Answer]:
    """Испорченное семейство (неверный ключ): балл не зависит от θ."""
    rng = Random(seed)
    return [
        Answer(score=1.0 if rng.random() < 0.5 else 0.0, theta=rng.gauss(0.0, 1.0), seed=i)
        for i in range(n)
    ]


# --- формулы ----------------------------------------------------------------------------------


def test_config_matches_document():
    assert (CFG.admit_min_n, CFG.admit_min_rpb, CFG.admit_max_abs_b) == (30, 0.2, 3.0)
    assert (CFG.admit_max_seed_spread, CFG.admit_max_dif) == (0.15, 0.1)
    assert (CFG.alarm_min_n, CFG.alarm_min_rpb, CFG.leak_window) == (50, 0.05, 50)
    assert (CFG.leak_delta, CFG.alarm_appeals) == (0.2, 3)


def test_pearson_and_stats_basics():
    assert lifecycle.pearson([0, 1, 0, 1], [-1, 1, -1, 1]) == pytest.approx(1.0)
    assert lifecycle.pearson([1, 1, 1], [0, 1, 2]) is None  # нет разброса
    st = compute_stats([Answer(1.0, 0.0, 0), Answer(0.0, 0.0, 1), Answer(1.0, 0.0, 2)], 0.0, CFG)
    assert st.n == 3 and st.p == pytest.approx(2 / 3)
    assert st.seed_spread == pytest.approx(1.0)  # группы сидов 0, 1, 2: 1, 0, 1
    assert st.dif is None and st.leak is None


def test_good_family_meets_admission_thresholds():
    st = compute_stats(_good(600), 0.0, CFG)
    assert st.r_pb >= 0.2 and st.seed_spread <= 0.15 and st.dif <= 0.1
    assert admission_failures(st, 0.0, CFG) == []
    assert alarm_reasons(st, CFG) == []


def test_each_admission_threshold():
    assert admission_failures(compute_stats(_good(20), 0.0, CFG), 0.0, CFG)[0] == "n"
    st = compute_stats(_good(600), 0.0, CFG)
    assert admission_failures(st, 3.5, CFG) == ["b"]  # |b| > 3
    assert "r_pb" in admission_failures(compute_stats(_broken(600), 0.0, CFG), 0.0, CFG)
    # перекос: «с ФСП» всегда верно, «без ФСП» — всегда неверно
    skew = [Answer(float(i % 2 == 0), 0.0, i, fsp=i % 2 == 0) for i in range(60)]
    assert compute_stats(skew, 0.0, CFG).dif == pytest.approx(1.0)
    assert "dif" in admission_failures(compute_stats(skew, 0.0, CFG), 0.0, CFG)
    # разброс по группам сидов: группа 0 всегда верно, остальные — нет
    by_seed = [Answer(float(i % 3 == 0), 0.0, i) for i in range(90)]
    assert "seed_spread" in admission_failures(compute_stats(by_seed, 0.0, CFG), 0.0, CFG)


def test_broken_family_alarms_on_synthetic():
    assert alarm_reasons(compute_stats(_broken(49), 0.0, CFG), CFG) == []  # n < 50 — рано
    assert alarm_reasons(compute_stats(_broken(200), 0.0, CFG), CFG) == ["low_r_pb"]
    # утечка: последние 50 ответов почти все верные
    leak = [Answer(float(i % 3 == 0), 0.0, i) for i in range(100)]
    leak += [Answer(1.0, 0.0, 100 + i) for i in range(50)]
    st = compute_stats(leak, 0.0, CFG)
    assert st.leak == pytest.approx(1.0 - 34 / 100) and "leak" in alarm_reasons(st, CFG)
    st3 = compute_stats(_good(10), 0.0, CFG, appeals=3)
    assert alarm_reasons(st3, CFG) == ["appeals"]


# --- БД: тревоги, admin API, пересчёт ---------------------------------------------------------


async def _family(s, slug: str, status: str, answers: list[Answer], b: float = 0.0) -> FamilyRow:
    row = FamilyRow(
        id=uuid.uuid4(), slug=slug, kind="exact", source="spec", skill_id=uuid.uuid4(),
        skill_type="hard", level=3, b=b, status=status, stats={},
    )  # fmt: skip
    s.add(row)
    await s.flush()
    for i, a in enumerate(answers):
        at = T0 + timedelta(minutes=i)
        att = Attempt(
            candidate_id=uuid.uuid4(), profession="backend", declared_grade="middle",
            status="passed", theta=a.theta, se=0.3, finished_at=at, plan={},
        )  # fmt: skip
        s.add(att)
        await s.flush()
        s.add(
            Response(
                attempt_id=att.id, seq=1, family_id=row.id, seed=a.seed, score=a.score,
                answered_at=at,
            )
        )  # fmt: skip
    await s.flush()
    return row


async def _status_events(factory) -> list[FamilyStatusChanged]:
    async with session_scope(factory) as s:
        rows = await s.scalars(
            select(OutboxRecord)
            .where(OutboxRecord.type == "assessment.family.status_changed")
            .order_by(OutboxRecord.id)
        )
        return [FamilyStatusChanged.model_validate(r.payload["payload"]) for r in rows]


async def test_broken_active_family_goes_to_quarantine(factory):
    async with session_scope(factory) as s:
        await _family(s, "broken", "active", _broken(80))
        gd = await _family(s, "good", "active", _good(80))
    async with session_scope(factory) as s:
        brk = (await s.scalars(select(FamilyRow).where(FamilyRow.slug == "broken"))).one()
        assert await lifecycle.check_alarms(s, brk, CFG) == ["low_r_pb"]
        gd = (await s.scalars(select(FamilyRow).where(FamilyRow.slug == "good"))).one()
        assert await lifecycle.check_alarms(s, gd, CFG) == []
    async with session_scope(factory) as s:
        brk = (await s.scalars(select(FamilyRow).where(FamilyRow.slug == "broken"))).one()
        assert brk.status == "quarantine" and brk.stats["n"] == 80
        assert brk.stats["log"][-1]["reason"] == "alarm:low_r_pb"
        assert (await s.get(FamilyRow, gd.id)).status == "active"
        # повтор не меняет статус и не шлёт новое событие
        assert await lifecycle.check_alarms(s, brk, CFG) == []
    ev = await _status_events(factory)
    assert [(e.family_id, e.from_, e.to) for e in ev] == [(brk.id, "active", "quarantine")]


async def test_appeals_quarantine_on_third(factory):
    async with session_scope(factory) as s:
        row = await _family(s, "appealed", "active", _good(10))
    for k in range(3):
        async with session_scope(factory) as s:
            reasons = await lifecycle.register_appeal(s, row.id, CFG)
        assert reasons == ([] if k < 2 else ["appeals"])
    async with session_scope(factory) as s:
        assert (await s.get(FamilyRow, row.id)).status == "quarantine"


def _admin(api) -> dict[str, str]:
    email = f"root-{uuid.uuid4().hex[:6]}@example.test"
    r = api.post("/auth/register", json={"email": email, "password": PASSWORD, "role": "candidate"})
    with sqlite3.connect(api.db_path) as con:
        con.execute("update users set role='fsp_admin' where email=?", (email,))
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_admin_queue_and_approve(api, factory):
    async with session_scope(factory) as s:
        few = await _family(s, "pilot_few", "pilot", _good(10))
        ok = await _family(s, "pilot_ok", "pilot", _good(600))
    adm, cand = _admin(api), register(api)
    assert api.get("/admin/families", headers=cand).status_code == 403
    assert api.post(f"/admin/families/{ok.id}/approve", headers=cand).status_code == 403
    assert api.get("/admin/families").status_code == 401

    q = {f["slug"]: f for f in api.get("/admin/families?status=pilot", headers=adm).json()}
    assert set(q) == {"pilot_few", "pilot_ok"}
    assert "n" in q["pilot_few"]["failed_thresholds"] and q["pilot_ok"]["failed_thresholds"] == []
    assert q["pilot_ok"]["stats"]["n"] == 600
    assert q["pilot_ok"]["stats"]["dif"] is None  # нет кандидатов с ФСП — DIF не считается

    # без порогов допуска нет; без админа нет `active`
    r = api.post(f"/admin/families/{few.id}/approve", headers=adm)
    assert r.status_code == 409 and r.json()["code"] == "thresholds_not_met"
    r = api.post(f"/admin/families/{ok.id}/approve", headers=adm)
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert r.json()["log"][-1]["reason"] == "admin"
    assert api.post(f"/admin/families/{ok.id}/approve", headers=adm).status_code == 200  # повтор

    assert api.post(f"/admin/families/{ok.id}/quarantine", headers=adm).json()["status"] == (
        "quarantine"
    )
    assert api.post(f"/admin/families/{ok.id}/retire", headers=adm).json()["status"] == "retired"
    r = api.post(f"/admin/families/{ok.id}/approve", headers=adm)
    assert r.status_code == 409 and r.json()["code"] == "invalid_transition"
    assert api.post(f"/admin/families/{uuid.uuid4()}/retire", headers=adm).status_code == 404

    ev = [(e.from_, e.to) for e in await _status_events(factory) if e.family_id == ok.id]
    assert ev == [("pilot", "active"), ("active", "quarantine"), ("quarantine", "retired")]
    async with session_scope(factory) as s:
        assert (await s.get(FamilyRow, few.id)).status == "pilot"


async def test_new_code_family_starts_in_pilot(factory, monkeypatch):
    # стартовый банк — active; кодовые семейства, добавленные позже, — pilot (ждут допуска)
    first = _Fake("t_python_3_0", "python", 3)
    monkeypatch.setattr(registry, "REGISTRY", {first.slug: first})
    async with session_scope(factory) as s:
        await attempts.sync_code_families(s, CFG)
    later = _Fake("t_python_3_1", "python", 3)
    monkeypatch.setattr(registry, "REGISTRY", {first.slug: first, later.slug: later})
    async with session_scope(factory) as s:
        await attempts.sync_code_families(s, CFG)
        got = {r.slug: r.status for r in await s.scalars(select(FamilyRow))}
    assert got == {"t_python_3_0": "active", "t_python_3_1": "pilot"}


# --- пересчёт попыток при выводе семейства ----------------------------------------------------


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


def _run(api, h, aid):
    while True:
        body = api.get(f"/assessment/attempts/{aid}/next", headers=h).json()
        if body["done"]:
            return
        r = api.post(
            f"/assessment/attempts/{aid}/answers",
            json={"response_id": body["response_id"], "answer": "1"},
            headers=h,
        )
        assert r.status_code == 200, r.text


async def test_withdrawal_recomputes_attempts(api, factory, taxonomy_loaded, fake_bank):
    h = register(api)
    body = {"profession": "backend", "declared_grade": "middle"}
    aid = api.post("/assessment/attempts", json=body, headers=h).json()["id"]
    _run(api, h, aid)
    async with session_scope(factory) as s:
        att = await s.get(Attempt, uuid.UUID(aid))
        uid = att.candidate_id
        fams = list(
            await s.scalars(
                select(Response.family_id)
                .where(Response.attempt_id == att.id, Response.is_pilot.is_(False))
                .order_by(Response.seq)
            )
        )
        assert att.status == "passed" and (await s.get(Grade, (uid, "backend"))).grade == "middle"

    # одно семейство в карантин: решение SPRT то же — грейд остаётся, уведомления нет
    async with session_scope(factory) as s:
        await lifecycle.quarantine(s, fams[0], uid, CFG)
    async with session_scope(factory) as s:
        att = await s.get(Attempt, uuid.UUID(aid))
        assert att.plan.get("recomputed_at") and att.status == "passed"
        row = await s.get(Grade, (uid, "backend"))
        assert row.grade == "middle" and row.valid_until.replace(tzinfo=UTC) > datetime.now(UTC)
        assert not list(await s.scalars(select(Notification).where(Notification.user_id == uid)))

    # выводим все семейства попытки: оценивать нечем — решение меняется, кандидат уведомлён
    for fid in fams[1:]:
        async with session_scope(factory) as s:
            await lifecycle.retire(s, fid, uid, CFG)
    async with session_scope(factory) as s:
        att = await s.get(Attempt, uuid.UUID(aid))
        assert att.status == "failed"
        row = await s.get(Grade, (uid, "backend"))
        assert row.valid_until.replace(tzinfo=UTC) <= datetime.now(UTC)  # данные не удалены
        notes = list(await s.scalars(select(Notification).where(Notification.user_id == uid)))
        assert [n.type for n in notes] == ["assessment.regraded"]
