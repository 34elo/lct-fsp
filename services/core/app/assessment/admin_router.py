"""HTTP `/admin/families*` — очередь допуска и решения админа (assessment.md §7, §10; E22-9)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fsp_contracts.assessment import ProfessionInfo
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import admission, constructor, lifecycle
from app.assessment.attempts import family_of
from app.assessment.config import AssessmentConfig, load_config
from app.assessment.families.spec import FamilySpec
from app.assessment.models import FamilyRow
from app.assessment.world import domain_for_profession
from app.deps import get_session
from app.identity.deps import require_roles
from app.identity.models import User
from app.openapi_errors import problem_responses
from app.taxonomy import service as taxonomy

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


class FamilyProfessionOut(BaseModel):
    slug: str
    title: str


class FamilyExampleOut(BaseModel):
    """Сгенерированный вариант задания и ответ решателя (ключ) — для карточки допуска."""

    kind: str
    stem: str
    options: list[str] | None = None
    answer: str


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
    company_id: uuid.UUID | None = None  # задание компании (конструктор)
    spec: dict[str, Any] | None = None  # конструктор: form, author, key_draft, autocheck
    skill: str | None = None  # slug навыка (E39-31)
    grade: Literal["junior", "middle", "senior"] = "middle"  # ячейка «грейд» по уровню
    professions: list[FamilyProfessionOut] = Field(default_factory=list)  # для кого задание
    example: FamilyExampleOut | None = None  # пример варианта с ответом решателя


def _out(
    row: FamilyRow,
    stats: lifecycle.FamilyStats | None,
    failed: list[str],
    profs: list[ProfessionInfo] | None = None,
) -> AdminFamilyOut:
    s = stats.as_json() if stats is not None else lifecycle._stats_of(row).as_json()
    fam = family_of(row)
    skill = getattr(fam, "skill", None)
    found = admission.professions_of(skill, profs or [])
    example = admission.example_of(
        fam, row.slug, domain_for_profession(found[0].slug) if found else None
    )
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
        company_id=row.company_id,
        spec=row.spec,
        skill=skill,
        grade=admission.grade_of_level(row.level),  # type: ignore[arg-type]
        professions=[FamilyProfessionOut(slug=p.slug, title=p.title) for p in found],
        example=FamilyExampleOut(**example) if example else None,
    )


async def _profs(session: AsyncSession) -> list[ProfessionInfo]:
    return await taxonomy.list_professions(session, include_hidden=True)


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
    profs = await _profs(session)
    return [_out(row, st, failed, profs) for row, st, failed in rows]


async def _decide(action, family_id, request, user, session) -> AdminFamilyOut:
    cfg = _cfg(request)
    row = await action(session, family_id, user.id, cfg)
    stats = lifecycle._stats_of(row)
    return _out(
        row,
        stats,
        lifecycle.admission_failures(stats, row.b, cfg, need_dif=row.source == "fsp"),
        await _profs(session),
    )


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


class KeyApproveIn(BaseModel):
    """Какой ключ утвердить: автора, черновик LLM или свою правку спецификации (E30-1)."""

    source: Literal["author", "llm", "custom"]
    spec: FamilySpec | None = None  # для `custom`


@router.post(
    "/{family_id}/key",
    response_model=AdminFamilyOut,
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def approve_key(
    family_id: uuid.UUID,
    body: KeyApproveIn,
    request: Request,
    user: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    """Утвердить ключ задания конструктора (`key_status → approved`) после автопроверки."""
    cfg = _cfg(request)
    row = await constructor.approve_key(session, family_id, user.id, body.source, body.spec)
    stats = lifecycle._stats_of(row)
    return _out(
        row,
        stats,
        lifecycle.admission_failures(stats, row.b, cfg, need_dif=row.source == "fsp"),
        await _profs(session),
    )


@router.post(
    "/{family_id}/pilot",
    response_model=AdminFamilyOut,
    responses=problem_responses(401, 403, 404, 409),
)
async def to_pilot(
    family_id: uuid.UUID,
    request: Request,
    user: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    """Задание компании → общий банк: `draft → pilot` (E30-1)."""
    return await _decide(constructor.to_bank, family_id, request, user, session)
