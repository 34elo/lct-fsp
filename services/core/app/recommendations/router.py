"""API для логирования показов и реакций (E17-1).

POST /recs/feedback - отправить реакцию на показ кандидата.
GET/DELETE /recs/sessions/{id} - учтённая подстройка сессии (E17-4) / сброс.
"""

from typing import Any

from fastapi import APIRouter, Depends, Response
from fsp_platform.app import ProblemError
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service as candidates
from app.deps import get_redis, get_session
from app.identity.deps import require_roles
from app.identity.models import User
from app.openapi_errors import problem_responses
from app.recommendations import service
from app.recommendations.tuning import TuningConfig

router = APIRouter(tags=["recommendations"], prefix="/recs")

_employer = require_roles("employer")
_TUNING = TuningConfig.load()


class FeedbackRequest(BaseModel):
    """Реакция на показ кандидата."""

    session_id: str
    candidate_pseudo_id: str
    event: str = Field(..., pattern="^(open|dwell|shortlist|dismiss)$")
    reason: str | None = Field(default=None, max_length=500)


class Chip(BaseModel):
    feature: str
    text: str
    change: float


class Hint(BaseModel):
    kind: str
    reason: str
    text: str
    count: int


class WeightOut(BaseModel):
    feature: str
    start: float
    current: float
    change: float


class SessionTuning(BaseModel):
    """Учтённая подстройка сессии (matching.md §7): чипсы «Учли: …» и подсказки фильтров."""

    session_id: str
    active: bool
    signals: int
    min_signals: int
    weights: list[WeightOut]
    chips: list[Chip]
    hints: list[Hint]


class FeedbackOut(BaseModel):
    id: int
    impression_id: int
    event: str
    created_at: str
    tuning: SessionTuning


@router.post(
    "/feedback", response_model=FeedbackOut, responses=problem_responses(401, 403, 404, 422)
)
async def record_feedback(
    body: FeedbackRequest,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
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
    tuning = await _tuning(session, redis, user, impression.session_id)
    await session.commit()

    return {
        "id": feedback.id,
        "impression_id": feedback.impression_id,
        "event": feedback.event,
        "created_at": feedback.created_at.isoformat(),
        "tuning": tuning,
    }


async def _tuning(session: AsyncSession, redis: Redis, user: User, session_id: str) -> dict:
    signals, features = await service.session_signals(session, redis, user.id, session_id, _TUNING)
    return {"session_id": session_id, **service.summary(signals, features, _TUNING)}


async def _own_session(session: AsyncSession, user: User, session_id: str) -> None:
    if not await service.session_owned(session, user.id, session_id):  # чужая — как нет
        raise ProblemError(404, "rec_session_not_found", "Сессия не найдена")


@router.get(
    "/sessions/{session_id}",
    response_model=SessionTuning,
    responses=problem_responses(401, 403, 404),
)
async def get_session_tuning(
    session_id: str,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    """Учтённые подстройки сессии: веса признаков, чипсы «Учли: …», подсказки фильтров."""
    await _own_session(session, user, session_id)
    return await _tuning(session, redis, user, session_id)


@router.delete(
    "/sessions/{session_id}", status_code=204, responses=problem_responses(401, 403, 404)
)
async def reset_session_tuning(
    session_id: str,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> Response:
    """Сброс подстройки (крестик на чипсе): реакции до сброса больше не учитываются."""
    await _own_session(session, user, session_id)
    await service.reset_session(session, redis, user.id, session_id)
    return Response(status_code=204)


async def _get_company_id(session: AsyncSession, user: User):
    """Получить ID компании для пользователя."""
    from app.companies import service as companies

    company, _ = await companies.require_company(session, user.id)
    return company.id
