"""HTTP `/assessment/*` (assessment.md §10). Попытка, `next`, `answers`, состояние, опрос."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fsp_contracts.assessment import ProfessionSlug, TestGrade
from fsp_contracts.enums import WorkFormat
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import attempts, grading, survey
from app.assessment.config import AssessmentConfig, load_config
from app.assessment.models import Attempt, Grade, Survey
from app.candidates import service as candidates
from app.deps import get_session
from app.identity import service as identity
from app.identity.deps import require_roles
from app.identity.models import User
from app.openapi_errors import problem_responses
from app.taxonomy import service as taxonomy

router = APIRouter(tags=["assessment"])
_candidate = require_roles("candidate")


def _cfg(request: Request) -> AssessmentConfig:
    return load_config(request.app.state.settings.scoring_config_path or None)


class AttemptIn(BaseModel):
    profession: ProfessionSlug
    declared_grade: TestGrade


class AttemptResultOut(BaseModel):
    """Итог завершённой попытки (assessment.md §10): грейд, θ по типам, честность, разбор."""

    grade: TestGrade | None = None  # грейд, подтверждённый этой попыткой
    theta: float | None = None
    se: float | None = None
    theta_by_type: dict[str, float] = Field(default_factory=dict)
    integrity: float = 1.0
    needs_confirmation: bool = False
    by_skill: list[dict[str, Any]] = Field(default_factory=list)  # {skill, items, share}


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
    low_confidence: bool = False  # решение по EAP на максимуме заданий или при нехватке банка
    upgrade_offer: TestGrade | None = None  # бонусный этап пройден: предложение повышения
    upgrade_accepted: bool = False
    result: AttemptResultOut | None = None  # только у завершённой попытки


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
    responses=problem_responses(401, 403, 409, 422, 503),
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


@router.post(
    "/assessment/attempts/{attempt_id}/upgrade",
    response_model=AttemptOut,
    responses=problem_responses(401, 403, 404, 409),
)
async def upgrade(
    attempt_id: uuid.UUID,
    request: Request,
    user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
):
    """Принять повышение после бонусного этапа (повтор идемпотентен)."""
    att = await attempts._own_attempt(session, user.id, attempt_id)
    await grading.accept_upgrade(session, att, _cfg(request))
    return await attempts.attempt_summary(session, user.id, attempt_id)


# --- опрос и история (E22-7) ------------------------------------------------------------------


class SurveyIn(BaseModel):
    industry: str | None = Field(default=None, max_length=64)
    profession: ProfessionSlug
    stack: list[str] = Field(default_factory=list, max_length=survey.MAX_STACK)
    formats: list[WorkFormat] = Field(default_factory=list)
    salary_from: int | None = Field(default=None, ge=0, le=100_000_000)
    salary_to: int | None = Field(default=None, ge=0, le=100_000_000)
    declared_grade: TestGrade | None = None


class SurveyOut(BaseModel):
    id: uuid.UUID | None = None
    industry: str | None = None
    profession: str | None = None
    stack: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=list)
    salary_from: int | None = None
    salary_to: int | None = None
    declared_grade: str | None = None
    created_at: datetime | None = None
    prefilled: bool = False  # черновик из резюме, ещё не сохранён


def _survey_out(row: Survey) -> SurveyOut:
    return SurveyOut(id=row.id, created_at=row.created_at, **survey.snapshot(row))


class CooldownOut(BaseModel):
    profession: str
    grade: TestGrade
    next_change_at: datetime


class RetryOut(BaseModel):
    profession: str
    grade: TestGrade  # на этот грейд повтор закрыт после неудачи
    next_attempt_at: datetime


class HistoryOut(BaseModel):
    surveys: list[SurveyOut]
    attempts: list[AttemptOut]
    cooldowns: list[CooldownOut]  # ближайшая смена грейда по профессиям
    retries: list[RetryOut] = Field(default_factory=list)  # повтор того же грейда после неудачи


@router.put(
    "/assessment/survey",
    response_model=SurveyOut,
    responses=problem_responses(401, 403, 422),
)
async def put_survey(
    body: SurveyIn,
    request: Request,
    user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
):
    await candidates.get_or_create(session, user.id, request.app.state.settings.pseudo_id_secret)
    row, _ = await survey.save_survey(session, user.id, body.model_dump(mode="json"))
    return _survey_out(row)


@router.get(
    "/assessment/survey",
    response_model=SurveyOut,
    responses=problem_responses(401, 403),
)
async def get_survey(
    user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
):
    row = await survey.last_survey(session, user.id)
    if row is not None:
        return _survey_out(row)
    professions = {p.slug for p in await taxonomy.list_professions(session)}
    draft = survey.prefill(await candidates.get(session, user.id), professions)
    return SurveyOut(prefilled=True, **draft) if draft else SurveyOut()


@router.get(
    "/assessment/history",
    response_model=HistoryOut,
    responses=problem_responses(401, 403),
)
async def history(
    request: Request,
    user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
):
    surveys = await session.scalars(
        select(Survey)
        .where(Survey.candidate_id == user.id)
        .order_by(Survey.created_at.desc(), Survey.id.desc())
    )
    atts_list = list(
        await session.scalars(
            select(Attempt)
            .where(Attempt.candidate_id == user.id)
            .order_by(Attempt.started_at.desc(), Attempt.id.desc())
        )
    )
    grades = await session.scalars(
        select(Grade).where(Grade.candidate_id == user.id).order_by(Grade.profession)
    )
    retries = [
        RetryOut(profession=p, grade=c.grade, next_attempt_at=c.until)
        for p in sorted({a.profession for a in atts_list})
        for c in await grading.cooldowns(session, user.id, p, _cfg(request))
        if c.kind == "retry" and c.grade is not None
    ]
    return HistoryOut(
        retries=retries,
        surveys=[_survey_out(r) for r in surveys],
        attempts=[await attempts.attempt_summary(session, user.id, a.id) for a in atts_list],
        cooldowns=[
            CooldownOut(profession=g.profession, grade=g.grade, next_change_at=g.next_change_at)
            for g in grades
        ],
    )
