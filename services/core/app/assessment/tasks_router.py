"""HTTP регулярных заданий: `/employer/tasks` (работодатель) и `/assessment/tasks` (кандидат).

Чужое задание → 404. «Пригласить» — ссылка на форму приглашения:
`/employer/offers/new?candidate=<pseudo_id>&source=regular_task`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request
from fsp_contracts.assessment import TestGrade
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import tasks
from app.assessment.models import RegularTask, TaskSubmission
from app.candidates import service as candidates
from app.candidates.models import Candidate
from app.companies import service as companies
from app.deps import get_session
from app.identity.deps import require_roles
from app.identity.models import User
from app.openapi_errors import problem_responses

employer_router = APIRouter(prefix="/employer/tasks", tags=["assessment"])
candidate_router = APIRouter(prefix="/assessment/tasks", tags=["assessment"])
_employer = require_roles("employer")
_candidate = require_roles("candidate")

INVITE_URL = "/employer/offers/new?candidate={pseudo_id}&source=regular_task"


class TaskIn(BaseModel):
    family_id: uuid.UUID
    profession: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    grade: TestGrade
    title: str | None = Field(default=None, min_length=1, max_length=200)
    period_days: int = Field(default=14, ge=7, le=14)  # раз в 1–2 недели


class TaskOut(BaseModel):
    id: uuid.UUID
    family_id: uuid.UUID
    title: str
    profession: str
    grade: str
    kind: str
    period_days: int
    status: str  # draft | open | closed
    round: int
    published_at: datetime | None = None
    next_round_at: datetime | None = None
    rubric: list[str] | None = None
    submissions: int = 0
    scored: int = 0
    delivered: bool | None = None  # только в ответе на publish: разослано ли сейчас


class SubmissionOut(BaseModel):
    id: uuid.UUID
    pseudo_id: str
    round: int
    answer: Any = None
    score: float | None = None
    rubric_marks: list[bool] | None = None
    scored_by: str | None = None
    created_at: datetime
    invite_url: str


class MarksIn(BaseModel):
    marks: list[bool] = Field(min_length=1, max_length=50)


class CandidateTaskOut(BaseModel):
    id: uuid.UUID
    title: str
    profession: str
    grade: str
    kind: str
    round: int
    published_at: datetime | None = None
    answer_until: datetime | None = None
    submitted: bool = False
    score: float | None = None


class CandidateTaskDetail(CandidateTaskOut):
    item: dict[str, Any]  # условие без ключа и рубрики
    submission_score: float | None = None
    scored_by: str | None = None


class AnswerIn(BaseModel):
    answer: Any


def _task_out(
    task: RegularTask, kind: str, counts: tuple[int, int] = (0, 0), delivered: bool | None = None
) -> TaskOut:
    nxt = (
        tasks.aware(task.published_at) + timedelta(days=task.period_days)
        if task.published_at
        else None
    )
    return TaskOut(
        id=task.id,
        family_id=task.family_id,
        title=task.title,
        profession=task.profession,
        grade=task.grade,
        kind=kind,
        period_days=task.period_days,
        status=task.status,
        round=task.round,
        published_at=task.published_at,
        next_round_at=nxt if task.status == "open" else None,
        rubric=task.rubric,
        submissions=counts[0],
        scored=counts[1],
        delivered=delivered,
    )


async def _company_id(session: AsyncSession, user: User) -> uuid.UUID:
    company, _ = await companies.require_company(session, user.id)
    return company.id


async def _out(session: AsyncSession, task: RegularTask, delivered: bool | None = None) -> TaskOut:
    c = await tasks.counts(session, [task.id])
    return _task_out(task, await tasks.kind_of(session, task), c.get(task.id, (0, 0)), delivered)


# --- работодатель -----------------------------------------------------------------------------


@employer_router.post(
    "",
    status_code=201,
    response_model=TaskOut,
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def create_task(
    body: TaskIn,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    """Черновик регулярного задания из своего задания конструктора или семейства банка."""
    company_id = await _company_id(session, user)
    task = await tasks.create_task(
        session,
        company_id=company_id,
        author_id=user.id,
        family_id=body.family_id,
        profession=body.profession,
        grade=body.grade,
        title=body.title,
        period_days=body.period_days,
    )
    return await _out(session, task)


@employer_router.get("", response_model=list[TaskOut], responses=problem_responses(401, 403))
async def list_tasks(user: User = Depends(_employer), session: AsyncSession = Depends(get_session)):
    found = await companies.my_company(session, user.id)
    if found is None:  # новая компания: заданий ещё нет
        return []
    rows = await tasks.list_company_tasks(session, found[0].id)
    c = await tasks.counts(session, [t.id for t in rows])
    return [_task_out(t, await tasks.kind_of(session, t), c.get(t.id, (0, 0))) for t in rows]


@employer_router.get(
    "/{task_id}", response_model=TaskOut, responses=problem_responses(401, 403, 404)
)
async def get_task(
    task_id: uuid.UUID,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    task = await tasks.get_company_task(session, task_id, await _company_id(session, user))
    return await _out(session, task)


@employer_router.post(
    "/{task_id}/publish", response_model=TaskOut, responses=problem_responses(401, 403, 404, 409)
)
async def publish_task(
    task_id: uuid.UUID,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    """Рассылка кандидатам категории. Повтор в пределах периода не рассылает заново."""
    task = await tasks.get_company_task(session, task_id, await _company_id(session, user))
    task, delivered = await tasks.publish(session, task)
    return await _out(session, task, delivered)


@employer_router.post(
    "/{task_id}/close", response_model=TaskOut, responses=problem_responses(401, 403, 404)
)
async def close_task(
    task_id: uuid.UUID,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    task = await tasks.get_company_task(session, task_id, await _company_id(session, user))
    return await _out(session, await tasks.close(session, task))


def _sub_out(sub: TaskSubmission, pseudo_id: str) -> SubmissionOut:
    return SubmissionOut(
        id=sub.id,
        pseudo_id=pseudo_id,
        round=sub.round,
        answer=sub.answer,
        score=sub.score,
        rubric_marks=sub.rubric_marks,
        scored_by=sub.scored_by,
        created_at=sub.created_at,
        invite_url=INVITE_URL.format(pseudo_id=pseudo_id),
    )


@employer_router.get(
    "/{task_id}/submissions",
    response_model=list[SubmissionOut],
    responses=problem_responses(401, 403, 404),
)
async def list_submissions(
    task_id: uuid.UUID,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    """Ответы анонимны: только `pseudo_id` и ссылка «Пригласить»."""
    task = await tasks.get_company_task(session, task_id, await _company_id(session, user))
    return [_sub_out(s, c.pseudo_id) for s, c in await tasks.submissions_of(session, task)]


@employer_router.put(
    "/{task_id}/submissions/{submission_id}/score",
    response_model=SubmissionOut,
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def score_submission(
    task_id: uuid.UUID,
    submission_id: uuid.UUID,
    body: MarksIn,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
):
    """Рубрика-чеклист открытого задания: итог — за работодателем."""
    task = await tasks.get_company_task(session, task_id, await _company_id(session, user))
    sub = await tasks.score_submission(session, task, submission_id, body.marks)
    cand = await session.get(Candidate, sub.candidate_id)
    return _sub_out(sub, cand.pseudo_id if cand else "")


# --- кандидат ---------------------------------------------------------------------------------


def _cand_out(task: RegularTask, kind: str, sub: TaskSubmission | None) -> CandidateTaskOut:
    until = (
        tasks.aware(task.published_at) + timedelta(days=task.period_days)
        if task.published_at
        else None
    )
    return CandidateTaskOut(
        id=task.id,
        title=task.title,
        profession=task.profession,
        grade=task.grade,
        kind=kind,
        round=task.round,
        published_at=task.published_at,
        answer_until=until,
        submitted=sub is not None,
        score=sub.score if sub else None,
    )


@candidate_router.get(
    "", response_model=list[CandidateTaskOut], responses=problem_responses(401, 403)
)
async def my_tasks(user: User = Depends(_candidate), session: AsyncSession = Depends(get_session)):
    """Открытые регулярные задания моих категорий (нужно согласие `profile_publication`)."""
    out = []
    for t in await tasks.my_tasks(session, user.id):
        out.append(
            _cand_out(
                t, await tasks.kind_of(session, t), await tasks.my_submission(session, t, user.id)
            )
        )
    return out


@candidate_router.get(
    "/{task_id}", response_model=CandidateTaskDetail, responses=problem_responses(401, 403, 404)
)
async def my_task(
    task_id: uuid.UUID,
    user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
):
    task = await tasks.my_task(session, user.id, task_id)
    sub = await tasks.my_submission(session, task, user.id)
    base = _cand_out(task, await tasks.kind_of(session, task), sub)
    return CandidateTaskDetail(
        **base.model_dump(),
        item=await tasks.item_public(session, task, user.id),
        submission_score=sub.score if sub else None,
        scored_by=sub.scored_by if sub else None,
    )


@candidate_router.post(
    "/{task_id}/answer",
    response_model=CandidateTaskOut,
    responses=problem_responses(401, 403, 404, 422, 503),
)
async def answer_task(
    task_id: uuid.UUID,
    body: AnswerIn,
    request: Request,
    user: User = Depends(_candidate),
    session: AsyncSession = Depends(get_session),
):
    """Ответ на текущий раунд. Повтор возвращает принятый ответ и не меняет балл."""
    task = await tasks.my_task(session, user.id, task_id)
    await candidates.get_or_create(session, user.id, request.app.state.settings.pseudo_id_secret)
    sub = await tasks.submit(session, task, user.id, body.answer)
    return _cand_out(task, await tasks.kind_of(session, task), sub)
