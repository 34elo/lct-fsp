"""Сервис для логирования показов и реакций (E17-1).

Каждая выдача в поиске/подборке должна логировать impressions.
Работодатель может отправить rec_feedback на любую impression.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.recommendations.models import Impression, RecFeedback


async def record_impression(
    session: AsyncSession,
    company_id: UUID,
    user_id: UUID,
    session_id: str,
    context_type: str,  # vacancy | search | similar
    context_id: str,
    candidate_id: UUID,
    position: int,
    score: float,
    features: dict[str, Any] | None = None,
    model_version: str | None = None,
) -> Impression:
    """Записать показ кандидата в выдаче."""
    impression = Impression(
        company_id=company_id,
        user_id=user_id,
        session_id=session_id,
        context_type=context_type,
        context_id=context_id,
        candidate_id=candidate_id,
        position=position,
        score=score,
        features=features,
        model_version=model_version,
    )
    session.add(impression)
    await session.flush()
    return impression


async def record_feedback(
    session: AsyncSession,
    impression_id: int,
    company_id: UUID,
    user_id: UUID,
    session_id: str,
    candidate_id: UUID,
    event: str,  # open | dwell | shortlist | dismiss | offer
    reason: str | None = None,
) -> RecFeedback:
    """Записать реакцию на показ."""
    feedback = RecFeedback(
        impression_id=impression_id,
        company_id=company_id,
        user_id=user_id,
        session_id=session_id,
        candidate_id=candidate_id,
        event=event,
        reason=reason,
    )
    session.add(feedback)
    await session.flush()
    return feedback


async def get_impression_by_id(session: AsyncSession, impression_id: int) -> Impression | None:
    """Получить impression по ID."""
    return await session.get(Impression, impression_id)


async def get_session_impressions(session: AsyncSession, session_id: str) -> list[Impression]:
    """Получить все impressions для сессии."""
    result = await session.execute(
        select(Impression).where(Impression.session_id == session_id).order_by(Impression.position)
    )
    return result.scalars().all()


async def get_session_feedback(session: AsyncSession, session_id: str) -> list[RecFeedback]:
    """Получить все feedback для сессии."""
    result = await session.execute(
        select(RecFeedback)
        .where(RecFeedback.session_id == session_id)
        .order_by(RecFeedback.created_at)
    )
    return result.scalars().all()
