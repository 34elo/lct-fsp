"""Регулярные задания компании (assessment.md §3, §10; E25-1).

Работодатель берёт задание конструктора (E30-1) или семейство из банка, выбирает категорию
(`profession × grade`) и публикует: рассылка идёт кандидатам с действующим грейдом ровно этой
категории и согласием `profile_publication` (blocks.md §4.5). «Рассылка» — событие
`regular_task.published` в outbox (уведомление шлёт блок 2, E9-6) и появление задания в
`GET /assessment/tasks` кандидата. Повторная публикация в пределах `period_days` ничего не делает;
по истечении — новый раунд (`round`), у кандидатов новый вариант и новый ответ.

Оценка: кодовые и спецификационные типы — автоматически (`family.score`), `open` — рубрика-чеклист
(отметки работодателя; черновик LLM — позже). Ответ в θ не идёт (assessment.md §4). Ключ и рубрика
кандидату не уходят. Функции не делают `commit`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fsp_contracts.assessment import RegularTaskPublished, TestGrade
from fsp_contracts.enums import ConsentType
from fsp_contracts.registry import new_event
from fsp_platform.app import ProblemError
from fsp_platform.outbox import add_to_outbox
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import service as grades_service
from app.assessment import track
from app.assessment.attempts import build_item, family_of, item_seed
from app.assessment.families.base import Kind
from app.assessment.families.spec import score_open
from app.assessment.models import FamilyRow, RegularTask, TaskSubmission
from app.candidates import service as candidates
from app.candidates.models import Candidate
from app.consents import service as consents
from app.identity.models import utcnow
from app.taxonomy import service as taxonomy

PRODUCER = "core"
BANK_STATUSES = ("pilot", "active")
MAX_ANSWER_CHARS = 20_000


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def not_found() -> ProblemError:
    return ProblemError(404, "not_found", "Задание не найдено")


# --- работодатель -----------------------------------------------------------------------------


async def create_task(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    author_id: uuid.UUID,
    family_id: uuid.UUID,
    profession: str,
    grade: TestGrade,
    title: str | None,
    period_days: int,
) -> RegularTask:
    """Черновик из семейства компании или из банка. Чужое семейство компании → 404."""
    row = await session.get(FamilyRow, family_id)
    if row is None or (row.company_id is not None and row.company_id != company_id):
        raise not_found()
    if row.company_id is None and row.status not in BANK_STATUSES:
        raise not_found()
    if row.kind == Kind.open.value and row.company_id is None:
        raise ProblemError(409, "open_not_in_bank", "Открытые задания берутся только из своих")
    if family_of(row) is None:
        raise ProblemError(409, "family_unavailable", "Семейство заданий недоступно")
    if profession not in {p.slug for p in await taxonomy.list_professions(session)}:
        raise ProblemError(
            422,
            "unknown_profession",
            "Профессия не найдена",
            errors=[{"field": "profession", "message": profession}],
        )
    form = (row.spec or {}).get("form") or {}
    rubric = list(form.get("rubric") or []) if row.kind == Kind.open.value else None
    if row.kind == Kind.open.value and not rubric:
        raise ProblemError(409, "rubric_required", "У открытого задания нет рубрики")
    task = RegularTask(
        company_id=company_id,
        author_id=author_id,
        family_id=family_id,
        profession=profession,
        grade=grade.value,
        title=(title or form.get("title") or row.slug).strip(),
        rubric=rubric,
        period_days=period_days,
        status="draft",
        round=0,
    )
    session.add(task)
    await session.flush()
    return task


async def get_company_task(
    session: AsyncSession, task_id: uuid.UUID, company_id: uuid.UUID
) -> RegularTask:
    task = await session.get(RegularTask, task_id)
    if task is None or task.company_id != company_id:
        raise not_found()
    return task


async def list_company_tasks(session: AsyncSession, company_id: uuid.UUID) -> list[RegularTask]:
    q = select(RegularTask).where(RegularTask.company_id == company_id)
    return list(await session.scalars(q.order_by(RegularTask.created_at.desc())))


async def recipients_of(session: AsyncSession, task: RegularTask) -> list[uuid.UUID]:
    """Кандидаты категории задания с согласием `profile_publication`."""
    members = await grades_service.category_members(session, task.profession, task.grade)
    return [cid for cid in sorted(members, key=str) if await _visible(session, cid)]


async def _visible(session: AsyncSession, candidate_id: uuid.UUID) -> bool:
    """Согласие `profile_publication`, профиль не удалён, 15–17 лет — с согласием родителя."""
    if not await consents.has_consent(session, candidate_id, ConsentType.profile_publication):
        return False
    cand = await session.get(Candidate, candidate_id)
    return cand is not None and cand.deleted_at is None and candidates.is_publishable(cand)


async def publish(
    session: AsyncSession, task: RegularTask, *, now: datetime | None = None
) -> tuple[RegularTask, bool]:
    """Рассылка. Возвращает `(задание, разослано_ли_сейчас)`; повтор в пределах периода — нет."""
    now = now or datetime.now(UTC)
    if task.status == "closed":
        raise ProblemError(409, "task_closed", "Задание закрыто")
    if task.status == "open" and task.published_at is not None:
        if now < aware(task.published_at) + timedelta(days=task.period_days):
            return task, False
    recipients = await recipients_of(session, task)
    task.status = "open"
    task.round += 1
    task.published_at = now
    await session.flush()
    event = RegularTaskPublished(
        task_id=task.id,
        company_id=task.company_id,
        profession=task.profession,
        grade=TestGrade(task.grade),
        round=task.round,
        period_days=task.period_days,
        recipients=recipients,
        published_at=now,
    )
    await add_to_outbox(session, new_event("regular_task.published", PRODUCER, event), task.id)
    await track.emit(
        session,
        "regular_task_sent",
        None,
        {"profession": task.profession, "grade": task.grade},
        role="employer",
        now=now,
    )
    return task, True


async def close(session: AsyncSession, task: RegularTask) -> RegularTask:
    task.status = "closed"
    await session.flush()
    return task


async def counts(
    session: AsyncSession, task_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    """`{task_id: (ответов, оценённых)}` по всем раундам."""
    if not task_ids:
        return {}
    rows = await session.execute(
        select(
            TaskSubmission.task_id,
            func.count(TaskSubmission.id),
            func.count(TaskSubmission.score),
        )
        .where(TaskSubmission.task_id.in_(task_ids))
        .group_by(TaskSubmission.task_id)
    )
    return {tid: (int(n), int(scored)) for tid, n, scored in rows}


async def submissions_of(
    session: AsyncSession, task: RegularTask
) -> list[tuple[TaskSubmission, Candidate]]:
    rows = await session.execute(
        select(TaskSubmission, Candidate)
        .join(Candidate, Candidate.user_id == TaskSubmission.candidate_id)
        .where(TaskSubmission.task_id == task.id)
        .order_by(TaskSubmission.created_at.desc(), TaskSubmission.id)
    )
    return [(s, c) for s, c in rows]


async def score_submission(
    session: AsyncSession,
    task: RegularTask,
    submission_id: uuid.UUID,
    marks: list[bool],
    *,
    now: datetime | None = None,
) -> TaskSubmission:
    """Рубрика-чеклист: оценка `open` работодателем, балл — доля отмеченных пунктов."""
    sub = await session.get(TaskSubmission, submission_id)
    if sub is None or sub.task_id != task.id:
        raise not_found()
    if not task.rubric:
        raise ProblemError(409, "not_open_task", "Рубрика есть только у открытых заданий")
    if len(marks) != len(task.rubric):
        raise ProblemError(
            422,
            "invalid_marks",
            "Число отметок не совпадает с рубрикой",
            errors=[{"field": "marks", "message": f"нужно {len(task.rubric)}"}],
        )
    sub.rubric_marks = list(marks)
    sub.score = score_open(task.rubric, marks)
    sub.scored_by = "employer"
    sub.scored_at = now or datetime.now(UTC)
    await session.flush()
    return sub


# --- кандидат ---------------------------------------------------------------------------------


async def my_tasks(session: AsyncSession, candidate_id: uuid.UUID) -> list[RegularTask]:
    """Открытые задания категорий кандидата; без согласия `profile_publication` — пусто."""
    if not await _visible(session, candidate_id):
        return []
    cats = {
        (g.profession, g.grade.value)
        for g in await grades_service.get_grades(session, candidate_id)
    }
    if not cats:
        return []
    rows = await session.scalars(
        select(RegularTask)
        .where(RegularTask.status == "open")
        .order_by(RegularTask.published_at.desc())
    )
    return [t for t in rows if (t.profession, t.grade) in cats]


async def my_task(
    session: AsyncSession, candidate_id: uuid.UUID, task_id: uuid.UUID
) -> RegularTask:
    for t in await my_tasks(session, candidate_id):
        if t.id == task_id:
            return t
    raise not_found()


async def my_submission(
    session: AsyncSession, task: RegularTask, candidate_id: uuid.UUID
) -> TaskSubmission | None:
    return await session.scalar(
        select(TaskSubmission).where(
            TaskSubmission.task_id == task.id,
            TaskSubmission.candidate_id == candidate_id,
            TaskSubmission.round == task.round,
        )
    )


async def kind_of(session: AsyncSession, task: RegularTask) -> str:
    row = await session.get(FamilyRow, task.family_id)
    return row.kind if row is not None else ""


def _seed(candidate_id: uuid.UUID, task: RegularTask) -> int:
    return item_seed(candidate_id, task.id, uuid.UUID(int=task.round))


async def item_public(
    session: AsyncSession, task: RegularTask, candidate_id: uuid.UUID
) -> dict[str, Any]:
    """Вариант текущего раунда без ключа и рубрики."""
    row = await session.get(FamilyRow, task.family_id)
    fam = family_of(row) if row is not None else None
    if fam is None:
        raise ProblemError(503, "family_unavailable", "Семейство заданий недоступно")
    return build_item(fam, _seed(candidate_id, task), None).public()


async def submit(
    session: AsyncSession, task: RegularTask, candidate_id: uuid.UUID, answer: Any
) -> TaskSubmission:
    """Ответ на текущий раунд. Повтор возвращает уже принятый ответ, ничего не меняя."""
    existing = await my_submission(session, task, candidate_id)
    if existing is not None:
        return existing
    row = await session.get(FamilyRow, task.family_id)
    fam = family_of(row) if row is not None else None
    if row is None or fam is None:
        raise ProblemError(503, "family_unavailable", "Семейство заданий недоступно")
    if len(str(answer)) > MAX_ANSWER_CHARS:
        raise ProblemError(422, "answer_too_long", "Ответ слишком длинный")
    seed = _seed(candidate_id, task)
    score: float | None = None
    scored_by: str | None = None
    now = datetime.now(UTC)
    if row.kind != Kind.open.value:
        item = build_item(fam, seed, None)
        score = max(0.0, min(1.0, float(fam.score(item, answer))))
        scored_by = "auto"
    sub = TaskSubmission(
        task_id=task.id,
        candidate_id=candidate_id,
        round=task.round,
        seed=seed,
        answer=answer,
        score=score,
        scored_by=scored_by,
        scored_at=now if score is not None else None,
        created_at=utcnow(),
    )
    try:
        async with session.begin_nested():
            session.add(sub)
            await session.flush()
    except IntegrityError:  # параллельный повтор: ответ уже принят
        existing = await my_submission(session, task, candidate_id)
        if existing is None:
            raise
        return existing
    await track.emit(
        session,
        "regular_task_answered",
        candidate_id,
        {
            "task_kind": track.slug(row.kind),
            "profession": task.profession,
            "grade": task.grade,
            "latency_h": max(0, int((now - aware(task.published_at)).total_seconds() // 3600))
            if task.published_at
            else None,
        },
        now=now,
    )
    return sub
