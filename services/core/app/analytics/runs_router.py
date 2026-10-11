"""Живые прогоны.

Админ: `POST|GET /admin/live-runs`, `GET /admin/live-runs/{id}`.
Испытатель (по секретному токену из ссылки): `GET /run/{token}`, `POST /run/{token}/start`,
`POST /run/{token}/sus`. Токен виден только админу и испытателю; чужой токен = 404.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fsp_platform.app import ProblemError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import runs
from app.analytics.models import LiveRun
from app.analytics.router import _token, _who
from app.deps import get_session
from app.identity.deps import require_roles
from app.openapi_errors import problem_responses

admin = APIRouter(prefix="/admin/live-runs", tags=["live-runs"])
public = APIRouter(prefix="/run", tags=["live-runs"])

RATE_LIMIT = 60  # запросов в минуту на IP
_admin = require_roles("fsp_admin")

Scenario = Literal["candidate", "employer"]
Status = Literal["invited", "started", "finished"]


class RunCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: Scenario
    tasks: list[str] | None = Field(default=None, max_length=10)  # id заданий; по умолчанию все
    notes: Annotated[str, Field(max_length=500)] | None = None


class SusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: Annotated[
        list[Annotated[int, Field(ge=1, le=5)]],
        Field(min_length=runs.SUS_ITEMS, max_length=runs.SUS_ITEMS),
    ]
    category_agree: bool | None = None
    notes: Annotated[str, Field(max_length=500)] | None = None


class TaskOut(BaseModel):
    id: str
    title: str
    target: int
    count: int
    done: bool
    done_at: datetime | None = None
    duration_s: int | None = None


class RunOut(BaseModel):
    """Прогон для админа: задания, время, SUS, затык."""

    id: UUID
    scenario: Scenario
    token: str
    path: str  # ссылка-приглашение относительно сайта: `/run/<token>`
    status: Status
    invited_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    tasks: list[TaskOut]
    tasks_done: int
    tasks_total: int
    steps: int
    total_time_s: int | None
    stuck_task: str | None
    sus_score: float | None
    category_agree: bool | None
    notes: str | None


class RunSummary(BaseModel):
    runs: int
    finished: int
    task_success_pct: float | None
    median_time_s: int | None
    median_sus: float | None
    category_agree_pct: float | None


class RunListOut(BaseModel):
    items: list[RunOut]
    summary: RunSummary


class RunTaskPublic(BaseModel):
    id: str
    title: str
    target: int
    count: int
    done: bool


class RunPublicOut(BaseModel):
    """Состояние для испытателя: без токена других, заметок и чужих данных."""

    id: UUID  # метка `run_id` для событий интерфейса
    scenario: Scenario
    status: Status
    tasks: list[RunTaskPublic]
    all_done: bool


def _status(run: LiveRun) -> Status:
    if run.finished_at is not None:
        return "finished"
    return "started" if run.started_at is not None else "invited"


def _run_out(run: LiveRun, steps: int, last_event: datetime | None) -> RunOut:
    stats = runs.task_stats(run, last_event)
    started, finished = runs._aware(run.started_at), runs._aware(run.finished_at)
    if started is not None:
        done_times = [s["done_at"] for s in stats if s["done_at"]]
        end = finished or (max(done_times) if done_times else runs._aware(last_event))
        total = max(0, round((end - started).total_seconds())) if end else None
    else:
        total = None
    return RunOut(
        id=run.id,
        scenario=run.scenario,  # type: ignore[arg-type]
        token=run.token,
        path=f"/run/{run.token}",
        status=_status(run),
        invited_at=run.invited_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        tasks=[TaskOut(**s) for s in stats],
        tasks_done=sum(1 for s in stats if s["done"]),
        tasks_total=len(stats),
        steps=steps,
        total_time_s=total,
        stuck_task=runs.stuck_task(stats),
        sus_score=run.sus_score,
        category_agree=run.category_agree,
        notes=run.notes,
    )


async def _outs(session: AsyncSession, found: list[LiveRun]) -> list[RunOut]:
    extra = await runs.steps_and_last(session, [r.id for r in found])
    return [_run_out(r, *extra.get(r.id, (0, None))) for r in found]


def _public(run: LiveRun) -> RunPublicOut:
    tasks = [
        RunTaskPublic(
            id=t["id"],
            title=t["title"],
            target=t["target"],
            count=t["count"],
            done=bool(t["done_at"]),
        )
        for t in run.tasks
    ]
    return RunPublicOut(
        id=run.id,
        scenario=run.scenario,  # type: ignore[arg-type]
        status=_status(run),
        tasks=tasks,
        all_done=all(t.done for t in tasks),
    )


@admin.post("", response_model=RunOut, status_code=201, responses=problem_responses(401, 403, 422))
async def create_run(
    body: RunCreateIn,
    session: AsyncSession = Depends(get_session),
    _user=Depends(_admin),
) -> RunOut:
    """Создать прогон и ссылку-приглашение (`path`)."""
    run = await runs.create(session, body.scenario, body.tasks, body.notes)
    return (await _outs(session, [run]))[0]


@admin.get("", response_model=RunListOut, responses=problem_responses(401, 403))
async def list_runs(
    scenario: Scenario | None = None,
    session: AsyncSession = Depends(get_session),
    _user=Depends(_admin),
) -> RunListOut:
    """Прогоны (новые сверху) и сводка: успешность заданий, медианное время, SUS."""
    stmt = select(LiveRun).order_by(LiveRun.invited_at.desc()).limit(200)
    if scenario:
        stmt = stmt.where(LiveRun.scenario == scenario)
    items = await _outs(session, list((await session.execute(stmt)).scalars().all()))
    summary = runs.summarize([i.model_dump() for i in items])
    return RunListOut(items=items, summary=RunSummary(**summary))


@admin.get("/{run_id}", response_model=RunOut, responses=problem_responses(401, 403, 404))
async def get_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user=Depends(_admin),
) -> RunOut:
    run = await session.get(LiveRun, run_id)
    if run is None:
        raise ProblemError(404, "not_found", "Прогон не найден")
    return (await _outs(session, [run]))[0]


async def _limit(request: Request) -> None:
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else "-"
    )
    await request.app.state.limiter.check(f"run:{ip}", RATE_LIMIT, 60)


@public.get(
    "/{token}",
    response_model=RunPublicOut,
    dependencies=[Depends(_limit)],
    responses=problem_responses(404, 429),
)
async def get_run_public(token: str, session: AsyncSession = Depends(get_session)) -> RunPublicOut:
    """Состояние прогона по ссылке: задания и их выполнение."""
    return _public(await runs.by_token(session, token))


@public.post(
    "/{token}/start",
    response_model=RunPublicOut,
    dependencies=[Depends(_limit)],
    responses=problem_responses(404, 409, 429),
)
async def start_run(
    token: str, request: Request, session: AsyncSession = Depends(get_session)
) -> RunPublicOut:
    """Старт: запускает таймер и (если испытатель вошёл) привязывает его псевдоним к прогону."""
    run = await runs.by_token(session, token)
    actor, _role = await _who(request, _token(request, None), session)
    return _public(await runs.start(session, run, actor))


@public.post(
    "/{token}/sus",
    response_model=RunPublicOut,
    dependencies=[Depends(_limit)],
    responses=problem_responses(404, 409, 422, 429),
)
async def submit_sus(
    token: str, body: SusIn, session: AsyncSession = Depends(get_session)
) -> RunPublicOut:
    """Анкета SUS (10 ответов 1–5) и согласие с категорией; завершает прогон."""
    run = await runs.by_token(session, token)
    await runs.submit_sus(session, run, body.answers, body.category_agree, body.notes)
    return _public(run)
