"""Сквозной путь: тест через API → грейд → событие → выдача категории работодателю.

Тест: `/assessment/*`, `grades`, `candidate.category.changed`;
подбор: `GET /categories/{profession}/{grade}/candidates`, видимость, аналитика.
События из outbox доставляются обработчикам воркера core (`Worker.consumers`) без RabbitMQ.
"""

import uuid
from pathlib import Path

import pytest
from app.analytics.models import AnalyticsEventRow as AnalyticsEvent
from app.assessment import attempts
from app.assessment import families as registry
from app.assessment import service as assessment
from app.assessment.models import Attempt, FamilyRow, Response
from app.candidates.models import Candidate
from app.companies.models import Company
from app.config import Settings
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from app.worker import Worker
from core_helpers import assert_foreign_is_404, register
from fsp_contracts import Envelope
from fsp_platform.db import session_scope
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import func, select

TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"
INN = "7707083893"
PROFESSION, GRADE = "backend", "middle"
URL = f"/categories/{PROFESSION}/{GRADE}/candidates"


@pytest.fixture
async def taxonomy_loaded(factory):
    async with session_scope(factory) as s:
        await tax.sync(s, load_taxonomy(TAXONOMY))


@pytest.fixture
async def worker(db_url):
    w = Worker(Settings(database_url=db_url))
    yield w
    await w.engine.dispose()


def _consents(api, h, **granted: bool):
    body = {"consents": [{"type": t, "granted": g} for t, g in granted.items()]}
    r = api.put("/me/consents", json=body, headers=h)
    assert r.status_code == 200, r.text


def _employer(api, factory_name="Acme Labs"):
    h = register(api, role="employer")
    r = api.post("/companies", json={"name": factory_name, "inn": INN}, headers=h)
    assert r.status_code == 201, r.text
    return h, uuid.UUID(r.json()["id"])


async def _verify_company(factory, company_id):
    async with session_scope(factory) as s:
        (await s.get(Company, company_id)).status = "verified"


async def _key(factory, response_id: str):
    """Ключ пересобирается из `(family_id, seed)` — так же, как на сервере при проверке."""
    async with session_scope(factory) as s:
        resp = await s.get(Response, uuid.UUID(response_id))
        att = await s.get(Attempt, resp.attempt_id)
        row = await s.get(FamilyRow, resp.family_id)
    return attempts.build_item(registry.get(row.slug), resp.seed, att.plan["domain"]).key


async def _pass_test(api, factory, h, *, wrong=(2,)) -> str:
    """Проходит тест через API: правильные ответы по ключу, на позициях `wrong` — неверные."""
    r = api.post(
        "/assessment/attempts",
        json={"profession": PROFESSION, "declared_grade": GRADE},
        headers=h,
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    for n in range(1, 41):
        item = api.get(f"/assessment/attempts/{aid}/next", headers=h).json()
        if item["done"]:
            break
        answer = "wrong" if n in wrong else await _key(factory, item["response_id"])
        a = api.post(
            f"/assessment/attempts/{aid}/answers",
            json={"response_id": item["response_id"], "answer": answer, "rt_ms": 5000},
            headers=h,
        )
        assert a.status_code == 200 and a.json()["accepted"], a.text
    final = api.get(f"/assessment/attempts/{aid}", headers=h).json()
    assert final["status"] == "passed", final
    return aid


async def _deliver(worker, factory, *, times: int = 2) -> list[str]:
    """Доставляет неотправленные события outbox всем очередям core (каждое — `times` раз)."""
    types: list[str] = []
    for _ in range(10):  # обработчики могут породить новые события (recompute → profile.updated)
        async with session_scope(factory) as s:
            recs = list(
                await s.scalars(
                    select(OutboxRecord)
                    .where(OutboxRecord.published_at.is_(None))
                    .order_by(OutboxRecord.id)
                )
            )
            for rec in recs:
                rec.published_at = func.now()
        if not recs:
            return types
        for rec in recs:
            env = Envelope.model_validate(rec.payload)
            types.append(env.type)
            for _ in range(times):
                for consumer in worker.consumers.values():
                    await consumer.dispatch(env)
    raise AssertionError("outbox не опустел")


async def _candidate_id(api, h, factory) -> tuple[uuid.UUID, str]:
    me = api.get("/me", headers=h).json()
    uid = uuid.UUID(me["id"])
    async with session_scope(factory) as s:
        cand = await s.get(Candidate, uid)
        return uid, cand.pseudo_id


def _page(api, emp, **params):
    r = api.get(URL, params=params, headers=emp)
    assert r.status_code == 200, r.text
    return {i["pseudo_id"]: i for i in r.json()["items"]}


async def test_attempt_to_grade_to_category(api, factory, worker, taxonomy_loaded):
    emp, company_id = _employer(api)
    await _verify_company(factory, company_id)

    # кандидат с согласием на публикацию проходит тест через API
    h = register(api)
    _consents(api, h, pd_processing=True, profile_publication=True)
    aid = await _pass_test(api, factory, h)
    uid, pid = await _candidate_id(api, h, factory)

    # грейд записан тестом, событие в outbox
    async with session_scope(factory) as s:
        g = await assessment.get_grade(s, uid, PROFESSION)
        changed = list(
            await s.scalars(
                select(OutboxRecord).where(OutboxRecord.type == "candidate.category.changed")
            )
        )
    assert g is not None and g.source == "test" and g.grade == GRADE
    assert str(g.attempt_id) == aid and 0.0 <= g.band_position <= 1.0
    assert [r.payload["payload"]["categories"] for r in changed] == [
        [{"profession": PROFESSION, "grade": GRADE}]
    ]

    # доставка событий потребителям (граф, подбор, аналитика) — дважды, результат тот же
    delivered = await _deliver(worker, factory)
    assert "candidate.category.changed" in delivered
    async with session_scope(factory) as s:
        rows = list(
            await s.scalars(
                select(AnalyticsEvent).where(AnalyticsEvent.event == "category_changed")
            )
        )
    assert [(r.props["profession"], r.props["grade"]) for r in rows] == [(PROFESSION, GRADE)]

    # кандидат виден в категории, T в силе профиля — из теста
    items = _page(api, emp)
    assert pid in items, f"кандидат после теста не виден в {URL}: {list(items)}"
    card = items[pid]
    assert {"profession": PROFESSION, "grade": GRADE} in card["categories"]
    terms = {t["code"]: t["value"] for t in card["strength"]["top"]}
    assert terms["T"] == pytest.approx(round(g.band_position, 4))
    assert "user_id" not in card and str(uid) not in str(card)

    # повторная доставка всего outbox ничего не меняет
    async with session_scope(factory) as s:
        await s.execute(OutboxRecord.__table__.update().values(published_at=None))
    await _deliver(worker, factory, times=1)
    async with session_scope(factory) as s:
        n = await s.scalar(
            select(func.count())
            .select_from(AnalyticsEvent)
            .where(AnalyticsEvent.event == "category_changed")
        )
    assert n == 1
    assert _page(api, emp)[pid]["strength"] == card["strength"]


async def test_category_visibility_rules(api, factory, worker, taxonomy_loaded):
    emp, company_id = _employer(api)
    await _verify_company(factory, company_id)

    # без согласия profile_publication — не виден
    hidden = register(api)
    _consents(api, hidden, pd_processing=True)
    await _pass_test(api, factory, hidden)
    _, hidden_pid = await _candidate_id(api, hidden, factory)

    # 15–17 лет без согласия родителя — не виден
    minor = register(api)
    _consents(api, minor, pd_processing=True, profile_publication=True)
    r = api.patch("/candidates/me/profile", json={"age_group": "minor"}, headers=minor)
    assert r.status_code == 200 and r.json()["publishable"] is False, r.text
    await _pass_test(api, factory, minor)
    _, minor_pid = await _candidate_id(api, minor, factory)

    await _deliver(worker, factory)
    items = _page(api, emp)
    assert hidden_pid not in items and minor_pid not in items

    # согласие выдано — оба появляются
    _consents(api, hidden, profile_publication=True)
    r = api.patch("/candidates/me/profile", json={"parent_consent": True}, headers=minor)
    assert r.status_code == 200 and r.json()["publishable"] is True, r.text
    await _deliver(worker, factory)
    items = _page(api, emp)
    assert {hidden_pid, minor_pid} <= set(items)

    # отзыв согласия — снова скрыт
    _consents(api, hidden, profile_publication=False)
    assert hidden_pid not in _page(api, emp)


async def test_foreign_resources_are_404(api, factory, taxonomy_loaded):
    owner = register(api)
    _consents(api, owner, pd_processing=True, profile_publication=True)
    aid = await _pass_test(api, factory, owner)
    intruder = register(api)
    assert_foreign_is_404(api, "GET", f"/assessment/attempts/{aid}", intruder)
    assert_foreign_is_404(api, "GET", f"/assessment/attempts/{aid}/next", intruder)

    emp, company_id = _employer(api)
    other, other_id = _employer(api, "Other Co")
    await _verify_company(factory, company_id)
    await _verify_company(factory, other_id)
    need = api.post("/needs", json={"filters": {"skills_must": [{"slug": "python"}]}}, headers=emp)
    assert need.status_code == 201, need.text
    nid = need.json()["id"]
    assert_foreign_is_404(api, "GET", f"{URL}?need_id={nid}", other)
    assert_foreign_is_404(api, "GET", f"/needs/{nid}/categories", other)
    # кандидату выдача категории недоступна вовсе
    assert api.get(URL, headers=owner).status_code == 403
