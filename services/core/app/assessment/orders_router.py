"""HTTP `/admin/assessment/generate` — заказ LLM-заданий из «Допуска заданий»."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fsp_contracts.ml import FamilyKind
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import orders
from app.assessment.models import FamilyOrder
from app.deps import get_session
from app.identity.deps import require_roles
from app.identity.models import User
from app.openapi_errors import problem_responses

router = APIRouter(prefix="/admin/assessment", tags=["admin"])
_admin = require_roles("fsp_admin")

OrderStatus = Literal["queued", "running", "done", "failed"]


class FamilyOrderIn(BaseModel):
    skill: str = Field(min_length=1, max_length=80)
    kind: FamilyKind
    level: int = Field(ge=1, le=5)
    count: int = Field(ge=1, le=orders.MAX_COUNT)


class FamilyOrderOut(BaseModel):
    id: uuid.UUID
    skill: str
    kind: str
    level: int
    count: int
    status: OrderStatus
    created: int = 0  # черновиков легло в банк
    rejected: dict[str, int] = Field(default_factory=dict)  # отбраковка по причинам
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    duplicate: bool = False  # повторный клик: вернули заказ, который уже в работе


class FamilyOrdersOut(BaseModel):
    items: list[FamilyOrderOut]
    used_today: int
    limit: int
    max_count: int = orders.MAX_COUNT


def _out(o: FamilyOrder, duplicate: bool = False) -> FamilyOrderOut:
    return FamilyOrderOut(
        id=o.id,
        skill=o.skill,
        kind=o.kind,
        level=o.level,
        count=o.count,
        status=o.status,  # type: ignore[arg-type]
        created=o.created or 0,
        rejected=dict(o.rejected or {}),
        error=o.error,
        created_at=o.created_at,
        updated_at=o.updated_at or o.created_at,
        duplicate=duplicate,
    )


@router.post(
    "/generate",
    status_code=202,
    response_model=FamilyOrderOut,
    responses=problem_responses(401, 403, 422, 429),
)
async def generate_families(
    body: FamilyOrderIn,
    request: Request,
    user: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    """Заказ: навык × `kind` × уровень × до 10 заданий → очередь `ml.llm` (низкий приоритет).

    Результат — черновики в «Допуске заданий» (`draft`, `source = llm`). Такой же заказ в работе —
    возвращается он (`duplicate = true`); сверх дневного лимита — `429 daily_limit`.
    """
    order, dup = await orders.create(
        session,
        skill=body.skill,
        kind=body.kind,
        level=body.level,
        count=body.count,
        user_id=user.id,
        per_day=request.app.state.settings.family_orders_per_day,
        correlation_id=request.headers.get("x-request-id"),
    )
    await session.flush()
    return _out(order, dup)


@router.get("/generate", response_model=FamilyOrdersOut, responses=problem_responses(401, 403))
async def family_orders(
    request: Request,
    _: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    """Последние заказы со статусом и счётчиком, сколько заказов осталось на сегодня."""
    items = await orders.recent(session)
    return FamilyOrdersOut(
        items=[_out(o) for o in items],
        used_today=await orders.used_today(session, datetime.now(UTC)),
        limit=request.app.state.settings.family_orders_per_day,
    )
