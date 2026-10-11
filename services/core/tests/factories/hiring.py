"""Фабрики работодателя, подбора и офферов."""

import uuid
from datetime import UTC, datetime, timedelta

from app.matching.models import Need
from app.offers.models import Offer
from fsp_contracts.ml import SearchFilters
from sqlalchemy.ext.asyncio import AsyncSession


async def factory_need(
    session: AsyncSession, company_id: uuid.UUID, text: str | None = None, **kw
) -> Need:
    """Потребность работодателя."""
    data = {
        "text": text or "Senior Python developer",
        "filters": SearchFilters().model_dump(mode="json"),
        "weights": {"python": 1.0, "postgresql": 0.5},
        "grades": ["middle", "senior"],
        "shortlist": [],
    }
    data.update(kw)
    need = Need(company_id=company_id, **data)
    session.add(need)
    await session.flush()
    return need


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
