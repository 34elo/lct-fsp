"""Каркас тестов (E29-1): фабрики, make_grade через seed_grade, хелперы 404 и повтора."""

from app.assessment import service as assessment
from app.offers.models import Offer
from core_helpers import assert_foreign_is_404, assert_idempotent_delivery, register
from factories.assessment import make_graded_candidate
from factories.base import make_candidate, make_company, make_grade, make_vacancy
from factories.hiring import make_offer
from fsp_contracts.assessment import TestGrade
from fsp_platform.db import session_scope
from fsp_platform.outbox import claim_inbox
from sqlalchemy import func, select


def test_endpoint_in_ten_lines(api):
    h = register(api)
    assert api.get("/candidates/me/profile", headers=h).status_code == 200
    assert_foreign_is_404(api, "GET", "/offers/00000000-0000-0000-0000-000000000001", h)


async def test_factories_and_make_grade(factory):
    async with session_scope(factory) as s:
        company, owner = await make_company(s)
        vac = await make_vacancy(s, company)
        cid, _ = await make_graded_candidate(s, {"backend": TestGrade.senior})
        cand = await make_candidate(s)
        await make_grade(s, cand.user_id, "qa", "junior")
        offer = await make_offer(s, vac, cid, owner.id)
    async with session_scope(factory) as s:
        got = await assessment.get_grades(s, cid)
        assert [(g.profession, g.grade) for g in got] == [("backend", TestGrade.senior)]
        assert (await s.get(Offer, offer.id)).status == "sent"


async def test_idempotent_delivery_helper(factory):
    import uuid

    msg = uuid.uuid4()

    async def deliver():
        async with session_scope(factory) as s:
            if await claim_inbox(s, msg, "scaffold"):
                await make_candidate(s)

    async def snapshot():
        async with session_scope(factory) as s:
            from app.candidates.models import Candidate

            return (await s.execute(select(func.count()).select_from(Candidate))).scalar_one()

    await assert_idempotent_delivery(deliver, snapshot, times=3)
