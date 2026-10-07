"""E25-1: регулярные задания — рассылка по категории и согласию, ответы, рубрика, права."""

import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from app.assessment import service as svc
from app.assessment import tasks as tasks_svc
from app.assessment.models import RegularTask, TaskSubmission
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from core_helpers import PASSWORD, assert_foreign_is_404, register
from fsp_contracts.assessment import RegularTaskPublished
from fsp_platform.db import session_scope
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import func, select

TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"
EXACT = {
    "title": "Секунды",
    "skill": "python",
    "level": 3,
    "kind": "exact",
    "stem": "{{n}} запросов по {{k}} мс. Сколько секунд?",
    "params": {"n": {"min": 10, "max": 90, "step": 10}, "k": {"values": [100, 200, 500]}},
    "derived": {"total_ms": "n * k"},
    "answer": "total_ms / 1000",
}
OPEN = {
    "title": "Разбор инцидента",
    "skill": "python",
    "level": 3,
    "kind": "open",
    "stem": "Как бы вы нашли узкое место в сервисе {{service}}?",
    "rubric": ["Найдено узкое место", "Предложено измерение до и после"],
}


@pytest.fixture
async def taxonomy_loaded(factory):
    async with session_scope(factory) as s:
        await tax.sync(s, load_taxonomy(TAXONOMY))


def _uid(h) -> uuid.UUID:
    return uuid.UUID(jwt.decode(h["Authorization"][7:], options={"verify_signature": False})["sub"])


def _employer(api, inn: str = "7707083893") -> dict[str, str]:
    h = register(api, "employer")
    r = api.post("/companies", json={"name": "Acme Labs", "inn": inn}, headers=h)
    assert r.status_code < 300
    return h


def _admin(api) -> dict[str, str]:
    email = f"root-{uuid.uuid4().hex[:6]}@example.test"
    r = api.post("/auth/register", json={"email": email, "password": PASSWORD, "role": "candidate"})
    with sqlite3.connect(api.db_path) as con:
        con.execute("update users set role='fsp_admin' where email=?", (email,))
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _grade(factory, h, grade="middle", profession="backend", consent=True, api=None):
    uid = _uid(h)
    async with session_scope(factory) as s:
        from app.candidates import service as cands

        await cands.get_or_create(s, uid, "dev-only-pseudo-secret")
        await svc.seed_grade(s, uid, profession, grade, 0.0 if grade == "middle" else 1.0)
    if consent:
        r = api.put(
            "/me/consents",
            json={"consents": [{"type": "profile_publication", "granted": True}]},
            headers=h,
        )
        assert r.status_code == 200, r.text
    return uid


def _task(api, emp, spec=EXACT, **kw) -> dict:
    fam = api.post("/families", json=spec, headers=emp)
    assert fam.status_code == 201, fam.text
    r = api.post(
        "/employer/tasks",
        json={"family_id": fam.json()["id"], "profession": "backend", "grade": "middle", **kw},
        headers=emp,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _events(factory) -> list[RegularTaskPublished]:
    async with session_scope(factory) as s:
        rows = await s.scalars(
            select(OutboxRecord).where(OutboxRecord.type == "regular_task.published")
        )
        return [RegularTaskPublished.model_validate(r.payload["payload"]) for r in rows]


async def test_publish_goes_to_category_with_consent_only(api, factory, taxonomy_loaded):
    emp = _employer(api)
    ok = register(api)
    no_consent, other_grade, other_prof = register(api), register(api), register(api)
    uid = await _grade(factory, ok, api=api)
    await _grade(factory, no_consent, consent=False, api=api)
    await _grade(factory, other_grade, grade="senior", api=api)
    await _grade(factory, other_prof, profession="qa", api=api)

    task = _task(api, emp)
    assert task["status"] == "draft" and task["round"] == 0 and task["kind"] == "exact"
    r = api.post(f"/employer/tasks/{task['id']}/publish", headers=emp)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "open" and r.json()["round"] == 1 and r.json()["delivered"]
    evs = await _events(factory)
    assert len(evs) == 1 and evs[0].recipients == [uid] and evs[0].round == 1

    # повторная публикация в пределах периода не рассылает и не плодит события
    again = api.post(f"/employer/tasks/{task['id']}/publish", headers=emp).json()
    assert again["round"] == 1 and again["delivered"] is False
    assert len(await _events(factory)) == 1

    # кандидат видит задание только своей категории и с согласием
    assert [t["id"] for t in api.get("/assessment/tasks", headers=ok).json()] == [task["id"]]
    for h in (no_consent, other_grade, other_prof):
        assert api.get("/assessment/tasks", headers=h).json() == []
        assert api.get(f"/assessment/tasks/{task['id']}", headers=h).status_code == 404


async def test_minor_without_parent_consent_gets_no_tasks(api, factory, taxonomy_loaded):
    """E32-5b: профиль 15–17 лет без согласия родителя не получает рассылку и не видит задания."""
    emp, minor = _employer(api), register(api)
    uid = await _grade(factory, minor, api=api)
    async with session_scope(factory) as s:
        from app.candidates.models import Candidate

        (await s.get(Candidate, uid)).age_group = "minor"
    task = _task(api, emp)
    assert api.post(f"/employer/tasks/{task['id']}/publish", headers=emp).status_code == 200
    assert (await _events(factory))[0].recipients == []
    assert api.get("/assessment/tasks", headers=minor).json() == []
    assert api.get(f"/assessment/tasks/{task['id']}", headers=minor).status_code == 404

    async with session_scope(factory) as s:
        from app.candidates.models import Candidate
        from app.identity.models import utcnow

        (await s.get(Candidate, uid)).parent_consent_at = utcnow()
    assert [t["id"] for t in api.get("/assessment/tasks", headers=minor).json()] == [task["id"]]


async def test_new_round_after_period(api, factory, taxonomy_loaded):
    emp, cand = _employer(api), register(api)
    uid = await _grade(factory, cand, api=api)
    task = _task(api, emp, period_days=7)
    api.post(f"/employer/tasks/{task['id']}/publish", headers=emp)
    api.post(f"/assessment/tasks/{task['id']}/answer", json={"answer": 1}, headers=cand)
    async with session_scope(factory) as s:
        t = await s.get(RegularTask, uuid.UUID(task["id"]))
        t, delivered = await tasks_svc.publish(s, t, now=datetime.now(UTC) + timedelta(days=8))
        assert delivered and t.round == 2
    evs = await _events(factory)
    assert [e.round for e in evs] == [1, 2] and evs[1].recipients == [uid]
    # в новом раунде снова можно ответить; прошлый ответ остался
    d = api.get(f"/assessment/tasks/{task['id']}", headers=cand).json()
    assert d["round"] == 2 and d["submitted"] is False
    assert api.post(f"/assessment/tasks/{task['id']}/answer", json={"answer": 1}, headers=cand)
    async with session_scope(factory) as s:
        assert await s.scalar(select(func.count()).select_from(TaskSubmission)) == 2


async def test_auto_scored_answer_is_idempotent_and_hides_key(api, factory, taxonomy_loaded):
    emp, cand = _employer(api), register(api)
    uid = await _grade(factory, cand, api=api)
    task = _task(api, emp)
    api.post(f"/employer/tasks/{task['id']}/publish", headers=emp)

    d = api.get(f"/assessment/tasks/{task['id']}", headers=cand).json()
    assert d["item"]["kind"] == "exact" and "key" not in d["item"] and d["submitted"] is False
    assert "rubric" not in d
    async with session_scope(factory) as s:
        from app.assessment.attempts import build_item, family_of
        from app.assessment.models import FamilyRow

        t = await s.get(RegularTask, uuid.UUID(task["id"]))
        fam = family_of(await s.get(FamilyRow, t.family_id))
        key = build_item(fam, tasks_svc._seed(uid, t), None).key

    r = api.post(f"/assessment/tasks/{task['id']}/answer", json={"answer": key}, headers=cand)
    assert r.status_code == 200 and r.json()["submitted"] and r.json()["score"] == 1.0
    # повтор с другим ответом ничего не меняет
    r = api.post(f"/assessment/tasks/{task['id']}/answer", json={"answer": -1}, headers=cand)
    assert r.json()["score"] == 1.0
    async with session_scope(factory) as s:
        rows = list(await s.scalars(select(TaskSubmission)))
        assert len(rows) == 1 and rows[0].scored_by == "auto" and rows[0].answer == key
        from app.analytics.models import AnalyticsEventRow

        ev = list(
            await s.scalars(
                select(AnalyticsEventRow).where(AnalyticsEventRow.event.like("regular_task_%"))
            )
        )
        assert sorted(e.event for e in ev) == ["regular_task_answered", "regular_task_sent"]
        ans = next(e for e in ev if e.event == "regular_task_answered")
        assert set(ans.props) <= {"task_kind", "profession", "grade", "latency_h"}
        assert str(key) not in str(ans.props)
        # свежесть R: ответ на задание — активность
        assert await svc.last_activity_at(s, uid) >= rows[0].created_at.replace(tzinfo=UTC)

    subs = api.get(f"/employer/tasks/{task['id']}/submissions", headers=emp).json()
    assert len(subs) == 1 and subs[0]["score"] == 1.0
    assert (
        subs[0]["invite_url"]
        == f"/employer/offers/new?candidate={subs[0]['pseudo_id']}&source=regular_task"
    )
    assert str(uid) not in str(subs[0])  # анонимно: только pseudo_id
    assert api.get(f"/employer/tasks/{task['id']}", headers=emp).json()["submissions"] == 1


async def test_open_task_rubric_checklist(api, factory, taxonomy_loaded):
    emp, cand = _employer(api), register(api)
    await _grade(factory, cand, api=api)
    task = _task(api, emp, spec=OPEN)
    assert task["rubric"] == OPEN["rubric"] and task["kind"] == "open"
    api.post(f"/employer/tasks/{task['id']}/publish", headers=emp)
    r = api.post(
        f"/assessment/tasks/{task['id']}/answer",
        json={"answer": {"text": "профилирование"}},
        headers=cand,
    )
    assert r.json()["submitted"] and r.json()["score"] is None  # ждёт работодателя

    sub = api.get(f"/employer/tasks/{task['id']}/submissions", headers=emp).json()[0]
    url = f"/employer/tasks/{task['id']}/submissions/{sub['id']}/score"
    assert api.put(url, json={"marks": [True]}, headers=emp).status_code == 422
    r = api.put(url, json={"marks": [True, False]}, headers=emp)
    assert r.status_code == 200 and r.json()["score"] == 0.5 and r.json()["scored_by"] == "employer"
    assert api.get(f"/employer/tasks/{task['id']}", headers=emp).json()["scored"] == 1
    assert (
        api.get(f"/assessment/tasks/{task['id']}", headers=cand).json()["submission_score"] == 0.5
    )

    # рубрика есть только у открытых
    exact = _task(api, emp)
    api.post(f"/employer/tasks/{exact['id']}/publish", headers=emp)
    api.post(f"/assessment/tasks/{exact['id']}/answer", json={"answer": 1}, headers=cand)
    sub2 = api.get(f"/employer/tasks/{exact['id']}/submissions", headers=emp).json()[0]
    r = api.put(
        f"/employer/tasks/{exact['id']}/submissions/{sub2['id']}/score",
        json={"marks": [True]},
        headers=emp,
    )
    assert r.status_code == 409 and r.json()["code"] == "not_open_task"


async def test_permissions_and_foreign_is_404(api, factory, taxonomy_loaded):
    emp, other = _employer(api), _employer(api, inn="7736050003")
    cand = register(api)
    await _grade(factory, cand, api=api)
    task = _task(api, emp)
    api.post(f"/employer/tasks/{task['id']}/publish", headers=emp)

    for method, url in [
        ("GET", f"/employer/tasks/{task['id']}"),
        ("POST", f"/employer/tasks/{task['id']}/publish"),
        ("POST", f"/employer/tasks/{task['id']}/close"),
        ("GET", f"/employer/tasks/{task['id']}/submissions"),
    ]:
        assert_foreign_is_404(api, method, url, other)
    assert api.get("/employer/tasks", headers=other).json() == []
    # чужое семейство компании нельзя взять в задание
    fam = api.post("/families", json=EXACT, headers=emp).json()
    r = api.post(
        "/employer/tasks",
        json={"family_id": fam["id"], "profession": "backend", "grade": "middle"},
        headers=other,
    )
    assert r.status_code == 404
    # роли
    assert api.get("/employer/tasks", headers=cand).status_code == 403
    assert api.get("/assessment/tasks", headers=emp).status_code == 403
    # закрытое задание пропадает у кандидата и не публикуется
    assert api.post(f"/employer/tasks/{task['id']}/close", headers=emp).json()["status"] == "closed"
    assert api.get("/assessment/tasks", headers=cand).json() == []
    r = api.post(f"/employer/tasks/{task['id']}/publish", headers=emp)
    assert r.status_code == 409 and r.json()["code"] == "task_closed"


async def test_bank_family_and_validation(api, factory, taxonomy_loaded):
    emp, adm = _employer(api), _admin(api)
    fam = api.post("/families", json=EXACT, headers=adm).json()  # админ → pilot, банк
    ok = {"family_id": fam["id"], "profession": "backend", "grade": "middle"}
    assert api.post("/employer/tasks", json=ok, headers=emp).status_code == 201
    r = api.post("/employer/tasks", json={**ok, "profession": "nope"}, headers=emp)
    assert (r.status_code, r.json()["code"]) == (422, "unknown_profession")
    assert (
        api.post("/employer/tasks", json={**ok, "period_days": 30}, headers=emp).status_code == 422
    )
    bad = {**ok, "family_id": str(uuid.uuid4())}
    assert api.post("/employer/tasks", json=bad, headers=emp).status_code == 404
    # черновик компании-чужака в банке не виден
    other = _employer(api, inn="7736050003")
    mine = api.post("/families", json=EXACT, headers=other).json()  # draft компании
    r = api.post("/employer/tasks", json={**ok, "family_id": mine["id"]}, headers=emp)
    assert r.status_code == 404
