"""HTTP `/assessment/*` (assessment.md §10). E22-1: попытка, `next`, `answers`, состояние."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fsp_contracts.assessment import ProfessionSlug, TestGrade
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import attempts
from app.assessment.config import AssessmentConfig, load_config
from app.candidates import service as candidates
from app.deps import get_session
from app.identity import service as identity
from app.identity.deps import require_roles
from app.identity.models import User
from app.openapi_errors import problem_responses

router = APIRouter(tags=["assessment"])
_candidate = require_roles("candidate")


def _cfg(request: Request) -> AssessmentConfig:
    return load_config(request.app.state.settings.scoring_config_path or None)


class AttemptIn(BaseModel):
    profession: ProfessionSlug
    declared_grade: TestGrade


class AttemptOut(BaseModel):
    id: uuid.UUID
    profession: str
    declared_grade: TestGrade
    stage: Literal["main", "bonus"]
    status: Literal["active", "passed", "failed", "abandoned"]
    answered: int
    target: int
    started_at: datetime
    finished_at: datetime | None


class NextOut(BaseModel):
    """Задание без ключа или `{done: true}`."""

    done: bool = False
    response_id: uuid.UUID | None = None
    seq: int | None = None
    kind: str | None = None
    stem: str | None = None
    options: list[str] | None = None
    time_limit_s: int | None = None


class AnswerIn(BaseModel):
    response_id: uuid.UUID
    answer: Any = None
    rt_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    telemetry: dict[str, Any] | None = None


class AnswerOut(BaseModel):
    response_id: uuid.UUID
    accepted: bool
    done: bool


@router.post(
    "/assessment/attempts",
    status_code=201,
    response_model=AttemptOut,
    responses=problem_responses(401, 403, 409, 422),
)
async def create_attempt(
    body: AttemptIn,
    request: Request,
    user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
):
    identity.require_verified_email(user)
    await candidates.get_or_create(session, user.id, request.app.state.settings.pseudo_id_secret)
    att = await attempts.create_attempt(
        session, user.id, body.profession, body.declared_grade, _cfg(request)
    )
    return await attempts.attempt_summary(session, user.id, att.id)


@router.get(
    "/assessment/attempts/{attempt_id}",
    response_model=AttemptOut,
    responses=problem_responses(401, 403, 404),
)
async def get_attempt(
    attempt_id: uuid.UUID,
    user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
):
    return await attempts.attempt_summary(session, user.id, attempt_id)


@router.get(
    "/assessment/attempts/{attempt_id}/next",
    response_model=NextOut,
    response_model_exclude_none=True,
    responses=problem_responses(401, 403, 404),
)
async def next_item(
    attempt_id: uuid.UUID,
    request: Request,
    user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
):
    return await attempts.next_item(session, user.id, attempt_id, _cfg(request))


@router.post(
    "/assessment/attempts/{attempt_id}/answers",
    response_model=AnswerOut,
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def answer(
    attempt_id: uuid.UUID,
    body: AnswerIn,
    request: Request,
    user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
):
    return await attempts.submit_answer(
        session,
        user.id,
        attempt_id,
        body.response_id,
        body.answer,
        body.rt_ms,
        body.telemetry,
        _cfg(request),
    )
