"""HTTP `/admin/demo/*` — вау-экраны питча: только чтение, без ПДн, роль `fsp_admin`.

- `two-worlds`: одно семейство и один сид в двух доменах мира (`World`): ручки сложности
  те же, меняются только компания, словарь и данные. Ключ в ответ не попадает.
- `llm-exam`: «LLM сдаёт наш тест». Цифры только из измерений: `ai_solvable` из банка
  и отчёт `make eval-assessment` (симуляция на синтетике). Нет отчёта — `report = null`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from random import Random
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fsp_platform.app import ProblemError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import families
from app.assessment.families import world_tasks
from app.assessment.models import FamilyRow
from app.assessment.world import DOMAIN_TITLES, DOMAINS, World
from app.deps import get_session
from app.identity.deps import require_roles
from app.identity.models import User
from app.openapi_errors import problem_responses

router = APIRouter(prefix="/admin/demo", tags=["admin"])
_admin = require_roles("fsp_admin")

DEFAULT_REPORT = Path(__file__).resolve().parents[4] / "reports" / "eval-assessment" / "report.json"
AI_SOLVES = 0.5  # порог «решается ИИ» — как `ai_solvable_share` в tools/eval_assessment
TOP = 5


class WorldItemOut(BaseModel):
    domain: str
    domain_title: str
    company: str
    scale: int
    kind: str
    stem: str
    options: list[str] | None = None
    time_limit_s: int
    services: list[str]


class TwoWorldsOut(BaseModel):
    family: str
    skill: str
    level: int
    seed: int
    choices: list[str]
    worlds: list[WorldItemOut]
    same_shape: bool  # одинаковы вид задания, лимит времени, число вариантов и масштаб


class LlmGradeRow(BaseModel):
    declared: str
    flagged_share: float  # доля попыток с пометкой «требует подтверждения»
    granted: dict[str, int]


class LlmReportOut(BaseModel):
    seed: int
    families: int
    ai_solvable_share: float | None = None
    rows: list[LlmGradeRow]
    simulation: bool = True


class LlmFamilyOut(BaseModel):
    slug: str
    status: str
    ai_solvable: float


class LlmBankOut(BaseModel):
    families: int
    measured: int
    solved_by_llm: int
    top: list[LlmFamilyOut]


class LlmExamOut(BaseModel):
    report: LlmReportOut | None = None
    bank: LlmBankOut


def world_family_slugs() -> list[str]:
    return [f.slug for f in world_tasks.FAMILIES]


@router.get(
    "/two-worlds", response_model=TwoWorldsOut, responses=problem_responses(401, 403, 404, 422)
)
async def two_worlds(
    family: Annotated[str, Query(max_length=80)] = "arch_blast_radius",
    seed: Annotated[int, Query(ge=0, le=2**31 - 1)] = 7,
    domains: Annotated[list[str] | None, Query()] = None,
    _: User = Depends(_admin),
) -> TwoWorldsOut:
    choices = world_family_slugs()
    fam = families.get(family) if family in choices else None
    if fam is None:
        raise ProblemError(404, "family_not_found", "Семейство не найдено")
    domains = domains or ["ecommerce", "fintech"]
    if len(domains) != 2 or domains[0] == domains[1] or any(d not in DOMAINS for d in domains):
        raise ProblemError(422, "invalid_domains", "Нужны два разных домена из справочника")
    items: list[WorldItemOut] = []
    shapes = set()
    for d in domains:
        w = World.from_seed(seed, d)
        it = fam.generate(Random(seed), w)
        shapes.add((it.kind.value, it.time_limit_s, len(it.options or []), w.scale))
        items.append(
            WorldItemOut(
                domain=d,
                domain_title=DOMAIN_TITLES[d],
                company=w.company,
                scale=w.scale,
                kind=it.kind.value,
                stem=it.stem,
                options=it.options,
                time_limit_s=it.time_limit_s,
                services=list(w.services),
            )
        )
    return TwoWorldsOut(
        family=fam.slug,
        skill=fam.skill,
        level=fam.level,
        seed=seed,
        choices=choices,
        worlds=items,
        same_shape=len(shapes) == 1,
    )


def _read_report() -> LlmReportOut | None:
    path = Path(os.getenv("EVAL_ASSESSMENT_REPORT") or DEFAULT_REPORT)
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        rows = [
            LlmGradeRow(
                declared=g,
                flagged_share=float(v.get("flagged_share", 0.0)),
                granted={k: int(n) for k, n in v.get("granted", {}).items()},
            )
            for g, v in raw["llm"].items()
        ]
        share = raw.get("metrics", {}).get("ai_solvable_share")
        return LlmReportOut(
            seed=int(raw["seed"]),
            families=int(raw["bank"]["families"]),
            ai_solvable_share=None if share is None else float(share),
            rows=rows,
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


@router.get("/llm-exam", response_model=LlmExamOut, responses=problem_responses(401, 403))
async def llm_exam(
    _: User = Depends(_admin), session: AsyncSession = Depends(get_session)
) -> LlmExamOut:
    rows = (
        (await session.execute(select(FamilyRow).where(FamilyRow.status.in_(("pilot", "active")))))
        .scalars()
        .all()
    )
    measured = [r for r in rows if (r.ai_solvable or 0.0) > 0]
    top = sorted(measured, key=lambda r: (-(r.ai_solvable or 0.0), r.slug))[:TOP]
    return LlmExamOut(
        report=_read_report(),
        bank=LlmBankOut(
            families=len(rows),
            measured=len(measured),
            solved_by_llm=sum((r.ai_solvable or 0.0) >= AI_SOLVES for r in rows),
            top=[
                LlmFamilyOut(slug=r.slug, status=r.status, ai_solvable=r.ai_solvable or 0.0)
                for r in top
            ],
        ),
    )
