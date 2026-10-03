"""API для логирования показов и реакций (E17-1).

POST /recs/feedback - отправить реакцию на показ кандидата.
"""

from typing import Any

from fastapi import APIRouter, Depends
from fsp_platform.app import ProblemError
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service as candidates
from app.deps import get_session
from app.identity.deps import require_roles
from app.identity.models import User
from app.recommendations import service

router = APIRouter(tags=["recommendations"], prefix="/recs")

_employer = require_roles("employer")


class FeedbackRequest(BaseModel):
    """Реакция на показ кандидата."""

    session_id: str
    candidate_pseudo_id: str
    event: str = Field(..., pattern="^(open|dwell|shortlist|dismiss)$")
    reason: str | None = None


@router.post("/feedback")
async def record_feedback(
    body: FeedbackRequest,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Записать реакцию на показ.

    События:
    - `open`: кандидат открыт для просмотра деталей
    - `dwell`: работодатель потратил время на карточку (>2с)
    - `shortlist`: добавлен в шорт-лист
    - `dismiss`: отклонен без оффера
    """
    company_id = await _get_company_id(session, user)
    cand = await candidates.get_by_pseudo_id(session, body.candidate_pseudo_id)
    impression = (
        await service.find_last_impression(session, company_id, body.session_id, cand.user_id)
        if cand is not None
        else None
    )
    # чужой/несуществующий показ неотличим → 404
    if impression is None:
        raise ProblemError(404, "impression_not_found", "Показ не найден")

    feedback = await service.record_feedback(
        session,
        impression_id=impression.id,
        company_id=impression.company_id,
        user_id=user.id,
        session_id=impression.session_id,
        candidate_id=impression.candidate_id,
        event=body.event,
        reason=body.reason,
    )
    await session.commit()

    return {
        "id": feedback.id,
        "impression_id": feedback.impression_id,
        "event": feedback.event,
        "created_at": feedback.created_at.isoformat(),
    }


async def _get_company_id(session: AsyncSession, user: User):
    """Получить ID компании для пользователя."""
    from app.companies import service as companies

    company, _ = await companies.require_company(session, user.id)
    return company.id
