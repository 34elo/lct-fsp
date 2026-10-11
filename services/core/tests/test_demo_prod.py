"""Демо в проде: пометка `is_demo`, сброс только демо, песочница жюри, статистика."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.analytics import dashboard, metrics
from app.analytics import service as analytics
from app.analytics.models import AnalyticsEventRow
from app.assessment.models import Grade
from app.candidates.models import Candidate
from app.companies import service as companies
from app.companies.models import Company
from app.demo import service as jury
from app.demo import snapshot as snap
from app.identity import service as identity
from app.identity.models import User
from app.offers import service as offers
from app.offers.models import Offer
from app.vacancies.models import Vacancy
from core_helpers import register
from factories.base import make_candidate, make_company, make_grade, make_vacancy
from factories.hiring import make_offer
from fsp_platform.db import session_scope
from sqlalchemy import func, insert, select

SALT = "dev-only-analytics-salt"  # Settings().analytics_salt по умолчанию
PSEUDO = "dev-only-pseudo-secret"


async def _demo_candidate(s, email: str | None = None) -> Candidate:
    cand = await make_candidate(s)
    user = await s.get(User, cand.user_id)
    user.is_demo = True
    user.email = email or f"{uuid.uuid4().hex[:8]}@demo.fsp.test"
    await s.flush()
    return cand


async def _demo_company(s) -> tuple[Company, User]:
    company, owner = await make_company(s, status="verified", is_demo=True, name="Демо-компания")
    owner.is_demo = True
    await s.flush()
    return company, owner


# --------------------------------------------------------------------------- пометка


async def test_demo_flag_follows_demo_email(session):
    demo = await identity.register(session, "hero@demo.fsp.test", "pass-12345678", "employer")
    real = await identity.register(session, "real@example.com", "pass-12345678", "employer")
    assert demo.is_demo and not real.is_demo
    demo_co = await companies.create_company(session, demo, {"name": "Демо"})
    real_co = await companies.create_company(session, real, {"name": "Реальная"})
    assert demo_co.is_demo and not real_co.is_demo


async def test_offer_is_demo_when_either_side_is_demo(session):
    demo_co, demo_hr = await _demo_company(session)
    real_co, real_hr = await make_company(session, status="verified")
    real_cand = await make_candidate(session)
    demo_cand = await _demo_candidate(session)
    limits = offers.OfferLimits()

    async def send(company, hr, cand) -> Offer:
        offer, _ = await offers.create(
            session, company=company, user_id=hr.id, vacancy=None, candidate=cand,
            salary_from=100_000, salary_to=150_000, message=None, title="Приглашение",
            idempotency_key=uuid.uuid4().hex, limits=limits,
        )  # fmt: skip
        return offer

    assert (await send(demo_co, demo_hr, real_cand)).is_demo
    assert (await send(real_co, real_hr, demo_cand)).is_demo
    assert not (await send(real_co, real_hr, real_cand)).is_demo


# --------------------------------------------------------------------------- статистика


async def test_landing_stats_without_demo(api, factory):
    async with session_scope(factory) as s:
        real_co, real_hr = await make_company(s, status="verified")
        real_vac = await make_vacancy(s, real_co)
        real = await make_candidate(s)
        await make_grade(s, real.user_id)
        await make_offer(s, real_vac, real.user_id, real_hr.id)

        demo_co, demo_hr = await _demo_company(s)
        demo_vac = await make_vacancy(s, demo_co, is_demo=True)
        for _ in range(3):
            d = await _demo_candidate(s)
            await make_grade(s, d.user_id)
            await make_offer(s, demo_vac, d.user_id, demo_hr.id, is_demo=True)
    body = api.get("/public/stats").json()
    assert body["candidates"] == 1
    assert body["companies"] == 1
    assert body["invitations"] == 1


async def test_dashboard_and_metrics_skip_demo_actors(session):
    real = [await make_candidate(session) for _ in range(5)]
    demo = [await _demo_candidate(session) for _ in range(6)]
    now = datetime.now(UTC)
    rows = [
        {"ts": now, "event": "signup_completed", "actor": analytics.pseudonym(SALT, c.user_id),
         "role": "candidate", "props": {}}
        for c in [*real, *demo]
    ]  # fmt: skip
    await session.execute(insert(AnalyticsEventRow), rows)
    await session.flush()

    everyone = await dashboard.build(session, 30)
    assert everyone.funnel[0].count == 11
    skip = await analytics.demo_actors(session, SALT)
    assert len(skip) == 6
    only_real = await dashboard.build(session, 30, exclude_actors=skip)
    assert only_real.funnel[0].count == 5
    m = await metrics.build(session, 30, exclude_actors=skip)
    assert m.candidate_funnel.stages[0].count == 5


# --------------------------------------------------------------------------- сброс только демо


async def _count(s, model, *where) -> int:
    return int(await s.scalar(select(func.count()).select_from(model).where(*where)) or 0)


async def test_reset_restores_demo_and_keeps_real_accounts(factory):
    # витрина после seed: демо-кандидат с грейдом, демо-компания с вакансией и приглашением
    async with session_scope(factory) as s:
        hero = await _demo_candidate(s, "hero@demo.fsp.test")
        await make_grade(s, hero.user_id, "backend")
        demo_co, demo_hr = await _demo_company(s)
        demo_vac = await make_vacancy(s, demo_co, is_demo=True)
        demo_offer = await make_offer(s, demo_vac, hero.user_id, demo_hr.id, is_demo=True)
        hero_id, demo_co_id, demo_offer_id = hero.user_id, demo_co.id, demo_offer.id
        await s.execute(
            insert(AnalyticsEventRow),
            [{"ts": datetime.now(UTC), "event": "signup_completed",
              "actor": analytics.pseudonym(SALT, hero_id), "role": "candidate", "props": {}}],
        )  # fmt: skip
        # песочница жюри, оставшаяся с прошлого показа, в снапшот не попадает
        old_sandbox, _, _ = await jury.enter(s, "employer", None, pseudo_secret=PSEUDO)
        old_sandbox_id = old_sandbox.id
    async with session_scope(factory) as s:
        stats = await snap.snapshot(s, SALT)
    assert stats["users"] == 2 and stats["companies"] == 1
    assert stats["offers"] == 1 and stats["grades"] == 1

    # после снапшота: реальная регистрация со своими данными и действия демо/жюри
    async with session_scope(factory) as s:
        real_co, real_hr = await make_company(s, status="verified", name="Реальная")
        real_vac = await make_vacancy(s, real_co)
        real = await make_candidate(s)
        await make_grade(s, real.user_id, "frontend")
        await make_offer(s, real_vac, real.user_id, real_hr.id)
        real_id, real_co_id = real.user_id, real_co.id
        # демо-компания пишет реальному кандидату — это демо-приглашение
        await make_offer(s, demo_vac, real.user_id, demo_hr.id, is_demo=True)
        # демо-герой получил новый грейд, приглашение принято
        await make_grade(s, hero_id, "frontend")
        (await s.get(Offer, demo_offer_id)).status = "accepted"
        # песочница жюри
        sandbox, _, created = await jury.enter(s, "candidate", None, pseudo_secret=PSEUDO)
        assert created and sandbox.is_demo
        sandbox_id = sandbox.id

    async with session_scope(factory) as s:
        res = await snap.reset(s, SALT)
    assert sandbox_id in res.demo_user_ids and hero_id in res.demo_user_ids
    assert real_id not in res.demo_user_ids

    async with session_scope(factory) as s:
        # реальный аккаунт на месте со своими данными
        assert await s.get(User, real_id) is not None
        assert await s.get(Candidate, real_id) is not None
        assert await s.get(Company, real_co_id) is not None
        assert await _count(s, Grade, Grade.candidate_id == real_id) == 1
        assert await _count(s, Offer, Offer.candidate_id == real_id, Offer.is_demo.is_(False)) == 1
        assert await _count(s, Vacancy, Vacancy.company_id == real_co_id) == 1
        # демо — как в снапшоте
        assert await _count(s, Offer, Offer.candidate_id == real_id, Offer.is_demo.is_(True)) == 0
        assert await s.get(User, sandbox_id) is None
        assert await s.get(User, old_sandbox_id) is None
        assert await _count(s, Company, Company.is_demo.is_(True)) == 1
        assert await s.get(Candidate, sandbox_id) is None
        assert await _count(s, Grade, Grade.candidate_id == hero_id) == 1
        assert (await s.get(Offer, demo_offer_id)).status == "sent"
        assert await s.get(Company, demo_co_id) is not None
        actor = analytics.pseudonym(SALT, hero_id)
        assert await _count(s, AnalyticsEventRow, AnalyticsEventRow.actor == actor) == 1

    # повторный сброс идемпотентен
    async with session_scope(factory) as s:
        again = await snap.reset(s, SALT)
    assert again.restored == res.restored


async def test_reset_without_snapshot_fails(session):
    try:
        await snap.reset(session, SALT)
    except snap.SnapshotMissing:
        return
    raise AssertionError("ждали SnapshotMissing")


# --------------------------------------------------------------------------- песочница жюри


def _jury(api, role: str, pair: str | None = None) -> tuple[dict[str, str], str, str]:
    r = api.post("/auth/jury", json={"role": role, "pair": pair})
    assert r.status_code == 200, r.text
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["pair"], body["user"]["id"]


def test_jury_entry_disabled_without_demo_mode(api):
    assert api.post("/auth/jury", json={"role": "candidate"}).status_code == 404


async def test_two_jury_entries_do_not_see_each_other(api, factory):
    api.app.state.settings.demo_mode = True
    cand_a, pair_a, cand_a_id = _jury(api, "candidate")
    hr_a, pair_a2, _ = _jury(api, "employer", pair_a)
    cand_b, pair_b, cand_b_id = _jury(api, "candidate")
    hr_b, _, _ = _jury(api, "employer", pair_b)
    assert pair_a == pair_a2 and pair_a != pair_b and cand_a_id != cand_b_id
    # повторный вход той же ролью — та же песочница
    assert _jury(api, "candidate", pair_a)[2] == cand_a_id

    co_a = api.get("/companies/me", headers=hr_a).json()
    co_b = api.get("/companies/me", headers=hr_b).json()
    assert co_a["id"] != co_b["id"]

    # работодатель A приглашает своего кандидата A
    async with session_scope(factory) as s:
        company = await s.get(Company, uuid.UUID(co_a["id"]))
        owner = await s.scalar(select(User).where(User.email == f"jury-{pair_a}-e@demo.fsp.test"))
        cand = await s.get(Candidate, uuid.UUID(cand_a_id))
        offer, _ = await offers.create(
            s, company=company, user_id=owner.id, vacancy=None, candidate=cand,
            salary_from=120_000, salary_to=180_000, message=None, title="Жюри: приглашение",
            idempotency_key="jury-a-1", limits=offers.OfferLimits(),
        )  # fmt: skip
        assert offer.is_demo

    mine = api.get("/candidates/me/offers", headers=cand_a).json()
    assert len(mine) == 1
    assert mine[0]["company"]["demo"] is False  # жюри — само демо, пометка не нужна
    assert api.get("/candidates/me/offers", headers=cand_b).json() == []
    assert len(api.get("/offers", headers=hr_a).json()) == 1
    assert api.get("/offers", headers=hr_b).json() == []


async def test_real_candidate_sees_demo_label(api, factory):
    real = register(api, "candidate")
    me = api.get("/me", headers=real).json()
    async with session_scope(factory) as s:
        cand = await s.get(Candidate, uuid.UUID(me["id"]))
        if cand is None:
            cand = Candidate(user_id=uuid.UUID(me["id"]), pseudonym="Pdemo", pseudo_id="pdemo1")
            s.add(cand)
            await s.flush()
        demo_co, demo_hr = await _demo_company(s)
        await offers.create(
            s, company=demo_co, user_id=demo_hr.id, vacancy=None, candidate=cand,
            salary_from=120_000, salary_to=180_000, message=None, title="Демо",
            idempotency_key="demo-real-1", limits=offers.OfferLimits(),
        )  # fmt: skip
    got = api.get("/candidates/me/offers", headers=real).json()
    assert len(got) == 1 and got[0]["company"]["demo"] is True
