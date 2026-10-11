"""API подграфа доказательств: владелец и анонимный вид для работодателя."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fsp_platform.app import ProblemError
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service as candidates
from app.companies import service as companies
from app.deps import get_session
from app.graph import subgraph
from app.graph.trust import TrustConfig
from app.identity.deps import require_roles
from app.identity.models import User
from app.openapi_errors import problem_responses
from app.vacancies import service as vacancies

router = APIRouter(tags=["graph"])

_TRUST = TrustConfig.load()
_owner = require_roles("candidate")
_employer = require_roles("employer")
Skills = Literal["top", "all"]
Depth = Literal["facts", "competitions"]


@router.get(
    "/candidates/me/graph",
    response_model=subgraph.Subgraph,
    response_model_exclude_none=True,
    responses=problem_responses(401, 403),
)
async def my_graph(
    request: Request,
    skills: Skills = "top",
    depth: Depth = "facts",
    user: User = Depends(_owner),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Граф доказательств владельца: факты (в т.ч. тесты) → навыки с доверием."""
    cand = await candidates.get_or_create(
        session, user.id, request.app.state.settings.pseudo_id_secret
    )
    return await subgraph.build(
        session, cand, trust=_TRUST, anonymous=False, skills=skills, depth=depth
    )


@router.get(
    "/candidates/{pseudo_id}/graph",
    response_model=subgraph.Subgraph,
    response_model_exclude_none=True,
    responses=problem_responses(401, 403, 404),
)
async def candidate_graph(
    pseudo_id: str,
    skills: Skills = "top",
    depth: Depth = "facts",
    vacancy_id: uuid.UUID | None = None,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Анонимный подграф для работодателя; скрытый кандидат и чужая вакансия → 404."""
    company, _ = await companies.require_company(session, user.id)
    if vacancy_id is not None:
        await vacancies.get_owned(session, user, vacancy_id)
    cand = await candidates.get_by_pseudo_id(session, pseudo_id)
    if (
        cand is None
        or cand.search_status == "dnd"
        or cand.primary_role is None
        or not candidates.is_publishable(cand)  # 15–17 лет без согласия родителя
        or str(company.id) in (cand.stoplist_company_ids or ())
    ):
        raise ProblemError(404, "candidate_not_found", "Кандидат не найден")
    return await subgraph.build(
        session, cand, trust=_TRUST, anonymous=True, skills=skills, depth=depth,
        vacancy_id=vacancy_id,
    )  # fmt: skip
