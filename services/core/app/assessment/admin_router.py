"""HTTP `/admin/families*` — очередь допуска и решения админа (assessment.md §7, §10; E22-9)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import lifecycle
from app.assessment.config import AssessmentConfig, load_config
from app.assessment.models import FamilyRow
from app.deps import get_session
from app.identity.deps import require_roles
from app.identity.models import User
from app.openapi_errors import problem_responses

router = APIRouter(prefix="/admin/families", tags=["admin"])
_admin = require_roles("fsp_admin")

FamilyStatus = Literal["draft", "pilot", "active", "quarantine", "retired"]


def _cfg(request: Request) -> AssessmentConfig:
    return load_config(request.app.state.settings.scoring_config_path or None)


class FamilyStatsOut(BaseModel):
    n: int = 0
    p: float | None = None
    r_pb: float | None = None
    seed_spread: float | None = None
    dif: float | None = None
    leak: float | None = None
    appeals: int = 0


class AdminFamilyOut(BaseModel):
    id: uuid.UUID
    slug: str
    kind: str
    source: str
    skill_type: str
    level: int
    b: float
    n: int
    anchor: bool
    status: FamilyStatus
    key_status: str
    ai_solvable: float
    stats: FamilyStatsOut
    failed_thresholds: list[str] = Field(default_factory=list)  # пусто — можно допускать
    log: list[dict[str, Any]] = Field(default_factory=list)  # история смен статуса
    updated_at: datetime | None = None


def _out(row: FamilyRow, stats: lifecycle.FamilyStats | None, failed: list[str]) -> AdminFamilyOut:
    s = stats.as_json() if stats is not None else lifecycle._stats_of(row).as_json()
    return AdminFamilyOut(
        id=row.id,
        slug=row.slug,
        kind=row.kind,
        source=row.source,
        skill_type=row.skill_type,
        level=row.level,
        b=row.b,
        n=row.n,
        anchor=row.anchor,
        status=row.status,  # type: ignore[arg-type]
        key_status=row.key_status,
        ai_solvable=row.ai_solvable or 0.0,
        stats=FamilyStatsOut(**s),
        failed_thresholds=failed,
        log=list((row.stats or {}).get("log", [])),
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[AdminFamilyOut], responses=problem_responses(401, 403))
async def admission_queue(
    request: Request,
    status: FamilyStatus = "pilot",
    _: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    """Очередь допуска со статистикой и невыполненными порогами."""
    cfg = _cfg(request)
    rows = await lifecycle.queue(session, status, cfg)
    return [_out(row, st, failed) for row, st, failed in rows]


async def _decide(action, family_id, request, user, session) -> AdminFamilyOut:
    cfg = _cfg(request)
    row = await action(session, family_id, user.id, cfg)
    stats = lifecycle._stats_of(row)
    return _out(row, stats, lifecycle.admission_failures(stats, row.b, cfg))


@router.post(
    "/{family_id}/approve",
    response_model=AdminFamilyOut,
    responses=problem_responses(401, 403, 404, 409),
)
async def approve(
    family_id: uuid.UUID,
    request: Request,
    user: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    """`pilot → active` (все пороги) или `quarantine → active`."""
    return await _decide(lifecycle.approve, family_id, request, user, session)


@router.post(
    "/{family_id}/quarantine",
    response_model=AdminFamilyOut,
    responses=problem_responses(401, 403, 404, 409),
)
async def quarantine(
    family_id: uuid.UUID,
    request: Request,
    user: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    return await _decide(lifecycle.quarantine, family_id, request, user, session)


@router.post(
    "/{family_id}/retire",
    response_model=AdminFamilyOut,
    responses=problem_responses(401, 403, 404, 409),
)
async def retire(
    family_id: uuid.UUID,
    request: Request,
    user: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    return await _decide(lifecycle.retire, family_id, request, user, session)
