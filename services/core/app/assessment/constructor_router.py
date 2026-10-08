"""HTTP `/families` — конструктор заданий (assessment.md §4, §10; E30-1).

Создают работодатель (задание компании) и админ. Эксперт — роль `fsp_admin` до появления
отдельной роли. Чужое задание → 404.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import constructor, key_draft
from app.assessment.attempts import family_of
from app.assessment.config import load_config
from app.assessment.families.spec import FamilySpec
from app.assessment.models import FamilyRow
from app.companies import service as companies
from app.deps import get_session
from app.identity.deps import require_roles
from app.identity.models import User
from app.openapi_errors import problem_responses

router = APIRouter(prefix="/families", tags=["assessment"])
_author = require_roles("employer", "fsp_admin")


class FamilyOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    kind: str
    source: str
    skill: str
    skill_type: str
    level: int
    status: str
    key_status: str  # draft — ключ из черновика LLM, ждёт админа
    company_id: uuid.UUID | None = None
    form: dict[str, Any]  # действующая спецификация (с ключом)
    author_form: dict[str, Any]  # как прислал автор
    key_draft: dict[str, Any] | None = None  # черновик LLM для сравнения
    autocheck: dict[str, Any] = Field(default_factory=dict)
    examples: list[dict[str, Any]] = Field(default_factory=list)  # варианты с ключом
    created_at: datetime | None = None


def family_out(row: FamilyRow, *, with_examples: bool = True) -> FamilyOut:
    spec = row.spec or {}
    form = spec.get("form") or {}
    exs: list[dict[str, Any]] = []
    if with_examples:
        fam = family_of(row)
        exs = constructor.examples(fam) if fam is not None else []  # type: ignore[arg-type]
    return FamilyOut(
        id=row.id,
        slug=row.slug,
        title=form.get("title", row.slug),
        kind=row.kind,
        source=row.source,
        skill=form.get("skill", ""),
        skill_type=row.skill_type,
        level=row.level,
        status=row.status,
        key_status=row.key_status,
        company_id=row.company_id,
        form=form,
        author_form=spec.get("author") or {},
        key_draft=spec.get("key_draft"),
        autocheck=spec.get("autocheck") or {},
        examples=exs,
        created_at=row.created_at,
    )


async def _company_id(session: AsyncSession, user: User) -> uuid.UUID | None:
    if user.role != "employer":
        return None
    company, _ = await companies.require_company(session, user.id)  # нет компании → 404
    return company.id


@router.post(
    "", status_code=201, response_model=FamilyOut, responses=problem_responses(401, 403, 404, 422)
)
async def create_family(
    body: FamilySpec,
    request: Request,
    user: User = Depends(_author),
    session: AsyncSession = Depends(get_session),
):
    """Форма → семейство-спецификация → автопроверка → `draft` (компания) или `pilot` (админ)."""
    settings = request.app.state.settings
    cfg = load_config(settings.scoring_config_path or None)
    company_id = await _company_id(session, user)

    async def drafter(spec: FamilySpec):
        return await key_draft.request_draft(settings, spec)

    row = await constructor.create_family(
        session, body, cfg, author_id=user.id, company_id=company_id, drafter=drafter
    )
    return family_out(row)


@router.get("", response_model=list[FamilyOut], responses=problem_responses(401, 403))
async def list_families(
    user: User = Depends(_author), session: AsyncSession = Depends(get_session)
):
    """Задания конструктора: свои и своей компании; админ — все."""
    found = await companies.my_company(session, user.id) if user.role == "employer" else None
    rows = await constructor.list_visible(
        session,
        user_id=user.id,
        company_id=found[0].id if found else None,
        admin=user.role == "fsp_admin",
    )
    return [family_out(r, with_examples=False) for r in rows]


@router.get("/{family_id}", response_model=FamilyOut, responses=problem_responses(401, 403, 404))
async def get_family(
    family_id: uuid.UUID,
    user: User = Depends(_author),
    session: AsyncSession = Depends(get_session),
):
    found = await companies.my_company(session, user.id) if user.role == "employer" else None
    row = await constructor.get_visible(
        session,
        family_id,
        user_id=user.id,
        company_id=found[0].id if found else None,
        admin=user.role == "fsp_admin",
    )
    return family_out(row)
