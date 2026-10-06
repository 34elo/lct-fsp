"""`GET /admin/metrics` — онлайн-метрики v2 (E31-4). Только роль `fsp_admin`, только агрегаты."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import metrics
from app.analytics.dashboard import DEFAULT_DAYS, MAX_DAYS
from app.deps import get_session
from app.identity.deps import require_roles
from app.openapi_errors import problem_responses

router = APIRouter(prefix="/admin", tags=["admin-metrics"])
_admin = require_roles("fsp_admin")


@router.get(
    "/metrics", response_model=metrics.MetricsOut, responses=problem_responses(401, 403, 422)
)
async def get_metrics(
    days: int = Query(DEFAULT_DAYS, ge=1, le=MAX_DAYS),
    session: AsyncSession = Depends(get_session),
    _user=Depends(_admin),
) -> metrics.MetricsOut:
    """Воронки кандидата и работодателя, приглашения (время до первого, доля принятых,
    ответ за 72 ч, причины отказов), отклики. Ячейки меньше 5 скрыты."""
    return await metrics.build(session, days)
