"""Админка графа навыков: очередь слияний, откат, «точно разные», стоп-лист, рост.

Обёртка над `decisions.py` и `growth.py`: логики слияния тут нет, только выборки и решения админа.
Любая правка графа поднимает версию справочника в `decisions` (`publish_change`).
"""

from __future__ import annotations

import uuid
from typing import Any

from fsp_platform.app import ProblemError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.taxonomy import decisions, service
from app.taxonomy.cards import SkillCard
from app.taxonomy.growth import HINTS_KEY
from app.taxonomy.models import (
    ScoringConfig,
    Skill,
    SkillAlias,
    SkillBlocklist,
    SkillCardDraftRow,
    SkillMention,
    SkillMerge,
    SkillRelation,
)


def _brief(sk: Skill) -> dict[str, Any]:
    return {
        "slug": sk.slug,
        "name": sk.name,
        "status": sk.status,
        "support_candidates": sk.support_candidates,
        "support_vacancies": sk.support_vacancies,
    }


async def _by_slug(session: AsyncSession, slug: str) -> Skill:
    sk = await session.scalar(select(Skill).where(Skill.slug == slug))
    if sk is None:
        raise ProblemError(404, "skill_not_found", "Навык не найден")
    return sk


async def queue(session: AsyncSession) -> list[dict[str, Any]]:
    """Очередь слияний с превью: что перейдёт к целевому навыку."""
    out = []
    for item in await decisions.pending_merges(session):
        frm, into = await _by_slug(session, item["skill"]), await _by_slug(session, item["into"])
        aliases = sorted(
            await session.scalars(
                select(SkillAlias.alias_norm).where(SkillAlias.skill_id == frm.id)
            )
        )
        rels = len(
            list(
                await session.scalars(
                    select(SkillRelation.skill_a).where(
                        (SkillRelation.skill_a == frm.id) | (SkillRelation.skill_b == frm.id)
                    )
                )
            )
        )
        out.append(
            {
                **item,
                "skill_name": frm.name,
                "into_name": into.name,
                "from": _brief(frm),
                "target": _brief(into),
                "preview": {
                    "aliases": sorted({*aliases, frm.slug, frm.name.lower()}),
                    "relations": rels,
                    "support_candidates": frm.support_candidates,
                    "support_vacancies": frm.support_vacancies,
                },
            }
        )
    return out


async def _pending_target(session: AsyncSession, slug: str) -> str:
    for item in await decisions.pending_merges(session):
        if item["skill"] == slug:
            return item["into"]
    raise ProblemError(404, "merge_not_pending", "Слияния в очереди нет")


async def approve_pending(session: AsyncSession, slug: str, actor: str) -> tuple[SkillMerge, str]:
    into = await _pending_target(session, slug)
    rec = await decisions.merge(session, slug, into, actor=actor)
    await _close_mentions(session, slug, "same_merged")
    return rec, into


async def reject_pending(session: AsyncSession, slug: str, mark_distinct: bool) -> int:
    into = await _pending_target(session, slug)
    await _close_mentions(session, slug, "same_rejected")
    if mark_distinct:
        await decisions.add_distinct(session, slug, into)
    return await service.get_version(session)


async def _close_mentions(session: AsyncSession, slug: str, decision: str) -> None:
    sk = await _by_slug(session, slug)
    for m in await session.scalars(
        select(SkillMention).where(
            SkillMention.skill_id == sk.id, SkillMention.decision == "same_pending"
        )
    ):
        m.decision = decision
    await session.flush()


async def merges(session: AsyncSession) -> list[dict[str, Any]]:
    slugs = {s.id: s for s in await session.scalars(select(Skill))}
    out = []
    for r in await session.scalars(select(SkillMerge).order_by(SkillMerge.created_at.desc())):
        moved = r.moved or {}
        out.append(
            {
                "id": r.id,
                "from_skill": slugs[r.from_skill].slug,
                "from_name": slugs[r.from_skill].name,
                "into_skill": slugs[r.into_skill].slug,
                "into_name": slugs[r.into_skill].name,
                "actor": r.actor,
                "created_at": r.created_at,
                "reverted_at": r.reverted_at,
                "aliases_added": len(moved.get("aliases_added", [])),
                "rows_moved": sum(
                    len(i.get("added", [])) + len(i.get("changed", [])) + len(i.get("removed", []))
                    for i in moved.get("tables", {}).values()
                ),
            }
        )
    return out


async def distinct_pairs(session: AsyncSession) -> list[dict[str, str]]:
    names = {s.slug: s.name for s in await session.scalars(select(Skill))}
    return [
        {"a": a, "b": b, "a_name": names[a], "b_name": names[b]}
        for a, b in await decisions.list_distinct(session)
    ]


async def blocklist(session: AsyncSession) -> list[SkillBlocklist]:
    return list(await session.scalars(select(SkillBlocklist).order_by(SkillBlocklist.norm)))


async def provisional(session: AsyncSession) -> list[dict[str, Any]]:
    """Временные навыки с карточкой-черновиком (если ml успел её сделать)."""
    drafts = {d.skill_id: d for d in await session.scalars(select(SkillCardDraftRow))}
    out = []
    for sk in await session.scalars(
        select(Skill).where(Skill.status == "provisional").order_by(Skill.created_at.desc())
    ):
        d = drafts.get(sk.id)
        out.append(
            {
                **_brief(sk),
                "type": sk.skill_type,
                "created_at": sk.created_at,
                "draft": SkillCard.model_validate(d.card) if d else None,
            }
        )
    return out


async def hints(session: AsyncSession) -> dict[str, Any]:
    """Подсказки экспертам: правила дисциплин и кандидаты в новые профессии (growth.refresh)."""
    cfg = await session.get(ScoringConfig, HINTS_KEY)
    v = cfg.value if cfg else {}
    return {
        "updated_at": v.get("updated_at"),
        "discipline_rules": v.get("discipline_rules", []),
        "profession_candidates": v.get("profession_candidates", []),
    }


def actor_of(user_id: uuid.UUID) -> str:
    return f"admin:{user_id}"
