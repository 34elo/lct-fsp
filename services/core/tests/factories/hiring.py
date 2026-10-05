"""Фабрики блока 2 (работодатель, подбор, офферы)."""

from datetime import UTC, datetime, timedelta

from app.offers.models import Offer
from sqlalchemy.ext.asyncio import AsyncSession


async def make_offer(session: AsyncSession, vacancy, candidate_id, created_by, **kw) -> Offer:
    data = {
        "salary_from": vacancy.salary_from,
        "salary_to": vacancy.salary_to,
        "status": "sent",
        "expires_at": datetime.now(UTC) + timedelta(days=7),
    }
    data.update(kw)
    offer = Offer(
        vacancy_id=vacancy.id,
        candidate_id=candidate_id,
        company_id=vacancy.company_id,
        created_by=created_by,
        **data,
    )
    session.add(offer)
    await session.flush()
    return offer
