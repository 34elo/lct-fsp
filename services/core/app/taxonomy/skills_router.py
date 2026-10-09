"""HTTP `/admin/skills/*` (E16-7): очередь слияний, откат, «точно разные», стоп-лист, рост графа."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends
from fsp_platform.app import ProblemError
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.identity.deps import require_roles
from app.identity.models import User
from app.openapi_errors import problem_responses
from app.taxonomy import decisions, service, skills_admin
from app.taxonomy.cards import SkillCard
from app.taxonomy.loader import norm_alias
from app.taxonomy.models import SkillBlocklist

router = APIRouter(prefix="/admin/skills", tags=["admin"])
_admin = require_roles("fsp_admin")


class AdminSkillBrief(BaseModel):
    slug: str
    name: str
    status: str
    support_candidates: int
    support_vacancies: int


class MergePreview(BaseModel):
    aliases: list[str]  # станут синонимами цели
    relations: int  # связей слитого, которые перейдут к цели
    support_candidates: int
    support_vacancies: int


class QueueItem(BaseModel):
    skill: str
    skill_name: str
    into: str
    into_name: str
    confidence: float | None = None
    norm: str
    from_: AdminSkillBrief = Field(alias="from")
    target: AdminSkillBrief
    preview: MergePreview

    model_config = {"populate_by_name": True}


class MergeBody(BaseModel):
    from_: str = Field(alias="from", min_length=1)
    into: str = Field(min_length=1)

    model_config = {"populate_by_name": True}


class RejectBody(BaseModel):
    mark_distinct: bool = False  # заодно пометить пару «точно разные»


class MergeOut(BaseModel):
    id: uuid.UUID
    from_skill: str
    into_skill: str
    taxonomy_version: int


class MergeRow(BaseModel):
    id: uuid.UUID
    from_skill: str
    from_name: str
    into_skill: str
    into_name: str
    actor: str
    created_at: dt.datetime
    reverted_at: dt.datetime | None = None
    aliases_added: int
    rows_moved: int


class VersionOut(BaseModel):
    taxonomy_version: int


class DistinctPair(BaseModel):
    a: str
    b: str
    a_name: str
    b_name: str


class DistinctIn(BaseModel):
    a: str = Field(min_length=1)
    b: str = Field(min_length=1)


class DistinctSaved(VersionOut):
    changed: bool


class BlockItem(BaseModel):
    norm: str
    reason: str | None = None
    created_at: dt.datetime


class BlockIn(BaseModel):
    norm: str = Field(min_length=1, max_length=120)
    reason: str | None = Field(default=None, max_length=300)


class ProvisionalOut(AdminSkillBrief):
    type: str | None = None
    created_at: dt.datetime
    draft: SkillCard | None = None


class DisciplineHint(BaseModel):
    discipline: str
    discipline_name: str | None = None
    skill: str
    lift: float
    support: int


class ProfessionCandidate(BaseModel):
    skills: list[str]
    support: int
    covered_by_professions: float


class HintsOut(BaseModel):
    updated_at: str | None = None
    discipline_rules: list[DisciplineHint]
    profession_candidates: list[ProfessionCandidate]


class SkillGraphNode(BaseModel):
    id: str
    type: str = "skill"
    label: str
    skill_type: str | None = None
    status: str


class SkillGraphEdge(BaseModel):
    from_: str = Field(alias="from")
    to: str
    type: str  # adjacent | parent (parent: от дочернего к родителю)
    weight: float | None = None

    model_config = {"populate_by_name": True}


class SkillGraphOut(BaseModel):
    version: int
    nodes: list[SkillGraphNode]
    edges: list[SkillGraphEdge]


async def _ver(session: AsyncSession) -> VersionOut:
    return VersionOut(taxonomy_version=await service.get_version(session))


@router.get(
    "/queue",
    response_model=list[QueueItem],
    response_model_by_alias=True,
    responses=problem_responses(401, 403),
)
async def get_queue(_: User = Depends(_admin), session: AsyncSession = Depends(get_session)):
    """Предложенные слияния («то же», уверенность 0.6–0.9) с превью."""
    return await skills_admin.queue(session)


@router.post(
    "/queue/{slug}/approve",
    response_model=MergeOut,
    responses=problem_responses(401, 403, 404, 409),
)
async def approve_queue(
    slug: str, user: User = Depends(_admin), session: AsyncSession = Depends(get_session)
):
    """Подтверждает слияние: временный навык вливается в целевой."""
    rec, into = await skills_admin.approve_pending(session, slug, skills_admin.actor_of(user.id))
    return MergeOut(
        id=rec.id,
        from_skill=slug,
        into_skill=into,
        taxonomy_version=await service.get_version(session),
    )


@router.post(
    "/queue/{slug}/reject",
    response_model=VersionOut,
    responses=problem_responses(401, 403, 404, 409),
)
async def reject_queue(
    slug: str,
    body: RejectBody | None = None,
    _: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    """Отклоняет слияние: навык остаётся отдельным, пара уходит из очереди."""
    v = await skills_admin.reject_pending(session, slug, bool(body and body.mark_distinct))
    return VersionOut(taxonomy_version=v)


@router.post(
    "/merge",
    status_code=201,
    response_model=MergeOut,
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def merge_skills(
    body: MergeBody, user: User = Depends(_admin), session: AsyncSession = Depends(get_session)
):
    """Ручное слияние `from` → `into` (запрещено для пары «точно разные»)."""
    rec = await decisions.merge(
        session, body.from_, body.into, actor=skills_admin.actor_of(user.id)
    )
    return MergeOut(
        id=rec.id,
        from_skill=body.from_,
        into_skill=body.into,
        taxonomy_version=await service.get_version(session),
    )


@router.get("/merges", response_model=list[MergeRow], responses=problem_responses(401, 403))
async def list_merges(_: User = Depends(_admin), session: AsyncSession = Depends(get_session)):
    """Журнал слияний; откатываются те, у которых нет `reverted_at`."""
    return await skills_admin.merges(session)


@router.post(
    "/merges/{merge_id}/revert",
    response_model=VersionOut,
    responses=problem_responses(401, 403, 404, 409),
)
async def revert_merge(
    merge_id: uuid.UUID, _: User = Depends(_admin), session: AsyncSession = Depends(get_session)
):
    await decisions.revert_merge(session, merge_id)
    return await _ver(session)


@router.get("/distinct", response_model=list[DistinctPair], responses=problem_responses(401, 403))
async def list_distinct(_: User = Depends(_admin), session: AsyncSession = Depends(get_session)):
    return await skills_admin.distinct_pairs(session)


@router.post(
    "/distinct",
    response_model=DistinctSaved,
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def add_distinct(
    body: DistinctIn, _: User = Depends(_admin), session: AsyncSession = Depends(get_session)
):
    changed = await decisions.add_distinct(session, body.a, body.b)
    return DistinctSaved(changed=changed, taxonomy_version=await service.get_version(session))


@router.delete(
    "/distinct", response_model=DistinctSaved, responses=problem_responses(401, 403, 404)
)
async def remove_distinct(
    a: str, b: str, _: User = Depends(_admin), session: AsyncSession = Depends(get_session)
):
    """Пара не найдена → 404."""
    if not await decisions.remove_distinct(session, a, b):
        raise ProblemError(404, "distinct_not_found", "Такой пары нет")
    return DistinctSaved(changed=True, taxonomy_version=await service.get_version(session))


@router.get("/blocklist", response_model=list[BlockItem], responses=problem_responses(401, 403))
async def list_blocklist(_: User = Depends(_admin), session: AsyncSession = Depends(get_session)):
    return await skills_admin.blocklist(session)


@router.post(
    "/blocklist", response_model=BlockItem, responses=problem_responses(401, 403, 409, 422)
)
async def add_blocklist(
    body: BlockIn, _: User = Depends(_admin), session: AsyncSession = Depends(get_session)
):
    if not await decisions.add_blocklist(session, body.norm, body.reason):
        raise ProblemError(409, "blocklist_exists", "Уже в стоп-листе или недопустимое значение")
    key = norm_alias(body.norm)
    row = await session.get(SkillBlocklist, key)
    assert row is not None
    return row


@router.delete("/blocklist", status_code=204, responses=problem_responses(401, 403, 404))
async def remove_blocklist(
    norm: str, _: User = Depends(_admin), session: AsyncSession = Depends(get_session)
):
    if not await decisions.remove_blocklist(session, norm):
        raise ProblemError(404, "blocklist_not_found", "Записи нет")


@router.get(
    "/provisional", response_model=list[ProvisionalOut], responses=problem_responses(401, 403)
)
async def list_provisional(_: User = Depends(_admin), session: AsyncSession = Depends(get_session)):
    """Временные навыки с карточками-черновиками ml."""
    return await skills_admin.provisional(session)


@router.get("/graph", response_model=SkillGraphOut, responses=problem_responses(401, 403))
async def get_graph(_: User = Depends(_admin), session: AsyncSession = Depends(get_session)):
    """Граф навыков справочника для просмотра: узлы и связи «рядом» и «часть»; без данных людей."""
    snap = await service.build_snapshot(session)
    return {
        "version": await service.get_version(session),
        "nodes": [
            {
                "id": x["slug"],
                "label": x["name"],
                "skill_type": x["skill_type"],
                "status": x["status"],
            }
            for x in snap["skills"]
        ],
        "edges": [
            *(
                {"from": r["a"], "to": r["b"], "type": "adjacent", "weight": r["weight"]}
                for r in snap["adjacent"]
            ),
            *(
                {"from": r["child"], "to": r["parent"], "type": "parent", "weight": r["weight"]}
                for r in snap["parent"]
            ),
        ],
    }


@router.get("/hints", response_model=HintsOut, responses=problem_responses(401, 403))
async def get_hints(_: User = Depends(_admin), session: AsyncSession = Depends(get_session)):
    """`taxonomy_hints`: правила дисциплин и кандидаты в новые профессии (ночной рост)."""
    return await skills_admin.hints(session)


@router.post(
    "/{slug}/approve",
    response_model=AdminSkillBrief,
    responses=problem_responses(401, 403, 404, 409),
)
async def approve_skill(
    slug: str, _: User = Depends(_admin), session: AsyncSession = Depends(get_session)
):
    """Временный навык становится активным."""
    return skills_admin._brief(await decisions.approve(session, slug))


@router.post(
    "/{slug}/reject",
    response_model=AdminSkillBrief,
    responses=problem_responses(401, 403, 404, 409),
)
async def reject_skill(
    slug: str, _: User = Depends(_admin), session: AsyncSession = Depends(get_session)
):
    """Временный навык отклоняется и скрывается."""
    return skills_admin._brief(await decisions.reject(session, slug))
