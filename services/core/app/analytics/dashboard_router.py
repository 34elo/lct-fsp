"""`GET /admin/dashboard` — воронка ФСП (E18-3), `GET /admin/summary` — «Что требует вас» (E39-29).

Только роль `fsp_admin`, только агрегаты.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import admin_summary, dashboard
from app.deps import get_session
from app.identity.deps import require_roles
from app.openapi_errors import problem_responses

router = APIRouter(prefix="/admin", tags=["admin-dashboard"])
_admin = require_roles("fsp_admin")


@router.get(
    "/dashboard", response_model=dashboard.DashboardOut, responses=problem_responses(401, 403, 422)
)
async def get_dashboard(
    days: int = Query(dashboard.DEFAULT_DAYS, ge=1, le=dashboard.MAX_DAYS),
    session: AsyncSession = Depends(get_session),
    _user=Depends(_admin),
) -> dashboard.DashboardOut:
    """Воронка регистрация → тест → категория → приглашение → ответ, доля с ФСП,
    конверсия навигатор → соревнование. Ячейки меньше 5 человек скрыты."""
    return await dashboard.build(session, days)


@router.get(
    "/summary", response_model=admin_summary.AdminSummaryOut, responses=problem_responses(401, 403)
)
async def get_summary(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user=Depends(_admin),
) -> admin_summary.AdminSummaryOut:
    """Счётчики очередей, где нужно решение админа: заявки ФСП, допуск заданий, слияния навыков,
    компании на проверке, открытые жалобы. Источник недоступен — `count: null`."""
    return await admin_summary.build(session, request)
