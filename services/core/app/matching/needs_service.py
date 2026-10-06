"""Потребности работодателя и рекомендованные категории (assessment.md §9, E23-4)."""

from __future__ import annotations

import uuid
from typing import Any

from fsp_contracts.ml import SearchFilters
from fsp_platform.app import ProblemError
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import service as assessment
from app.candidates import service as candidates
from app.graph import service as graph
from app.matching import needs as n
from app.matching.models import Need
from app.matching.service import only_visible
from app.taxonomy import service as taxonomy

_POOL_KEYS = ("formats", "employment_types", "cities", "relocation_ok", "active_only", "salary_max")


class NeedCategory(BaseModel):
    profession: str
    title: str
    grade: str
    affinity: float
    candidates: int
    median_salary: int | None = None  # ₽/мес; мало данных — None
    fsp_share: float | None = None  # доля участников с ФСП; пустая категория — None


def _not_found() -> ProblemError:
    return ProblemError(404, "need_not_found", "Потребность не найдена")


def merge_filters(parsed: SearchFilters | None, explicit: SearchFilters | None) -> SearchFilters:
    """Явные поля формы перекрывают разобранные из текста."""
    base: dict[str, Any] = parsed.model_dump(mode="json") if parsed else {}
    if explicit is not None:
        base.update(explicit.model_dump(mode="json", exclude_none=True))
    return SearchFilters.model_validate(base)


async def create(
    session: AsyncSession,
    company_id: uuid.UUID,
    text: str | None,
    filters: SearchFilters,
    cfg: n.NeedsConfig,
) -> Need:
    weights = n.need_weights(filters, cfg)
    if not weights and not filters.roles:
        raise ProblemError(
            422, "need_empty", "В потребности не нашли навыков и профессии: уточните запрос"
        )
    need = Need(
        company_id=company_id, text=text, filters=filters.model_dump(mode="json"),
        weights=weights, grades=n.need_grades(filters),
    )  # fmt: skip
    session.add(need)
    await session.flush()
    return need


async def get_owned(session: AsyncSession, company_id: uuid.UUID, need_id: uuid.UUID) -> Need:
    """Чужая или несуществующая потребность → 404."""
    need = await session.get(Need, need_id)
    if need is None or need.company_id != company_id:
        raise _not_found()
    return need


def filters_of(need: Need) -> SearchFilters:
    return SearchFilters.model_validate(need.filters)


def listing_filters(need: Need | None) -> SearchFilters:
    """Фильтры выдачи в категории: фильтры анкеты — как в потребности; профессию и грейд задаёт
    категория; навыки идут «желательными» (покрытие входит в `match`, но выдачу не обнуляет)."""
    if need is None:
        return SearchFilters()
    f = filters_of(need)
    skills = list(dict.fromkeys([*(m.slug for m in f.skills_must or ()), *(f.skills_nice or ())]))
    return f.model_copy(
        update={
            "roles": None, "grade_min": None, "grade_max": None,
            "skills_must": None, "skills_nice": skills or None,
        }
    )  # fmt: skip


async def categories(
    session: AsyncSession, company_id: uuid.UUID, need: Need, cfg: n.NeedsConfig
) -> list[NeedCategory]:
    """Профессии с affinity ≥ порога × грейды потребности, со счётчиками видимых работодателю."""
    f = filters_of(need)
    profs = {p.slug: p for p in await taxonomy.list_professions(session)}
    picked = n.recommend(
        need.weights, {s: p.skill_weights for s, p in profs.items()}, cfg, f.roles or ()
    )
    if not picked:
        return []
    pool = await only_visible(
        session,
        await candidates.search_pool(
            session, company_id=company_id,
            **{k: v for k, v in listing_filters(need).model_dump().items() if k in _POOL_KEYS},
        ),
    )  # fmt: skip
    by_id = {c.user_id: c for c in pool}
    members: dict[tuple[str, str], list[uuid.UUID]] = {}
    for prof, _ in picked:
        for g in need.grades:
            ids = await assessment.category_members(session, prof, g)
            members[(prof, g)] = [i for i in ids if i in by_id]
    everyone = list({i for ids in members.values() for i in ids})
    disc = await graph.fsp_disciplines_of(session, everyone) if everyone else {}
    owned = await graph.all_skills_of(session, everyone) if everyone else {}

    def has_fsp(cid: uuid.UUID) -> bool:
        return bool(disc.get(cid)) or any("fsp" in s.sources for s in owned.get(cid, ()))

    out: list[NeedCategory] = []
    for prof, aff in picked:
        for g in need.grades:
            ids = members[(prof, g)]
            out.append(
                NeedCategory(
                    profession=prof, title=profs[prof].title, grade=g, affinity=aff,
                    candidates=len(ids),
                    median_salary=n.median_salary(by_id[i].salary_min for i in ids),
                    fsp_share=round(sum(has_fsp(i) for i in ids) / len(ids), 2) if ids else None,
                )
            )  # fmt: skip
    return out
