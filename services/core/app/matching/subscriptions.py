"""Подписки компаний на категорию.

По `candidate.category.changed` кандидат сверяется с подписками на его категории. Подошедший
пишется в `category_subscription_hits` (PK «подписка + кандидат» — повтор не дублирует), затем
подписка уведомляет участников компании дайджестом не чаще `subscription_digest_minutes`.
Адресату уходит число и анонимные `pseudo_id`, без ПДн кандидата.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fsp_contracts.assessment import CategoryRef, TestGrade
from fsp_contracts.notify import TgTemplate
from fsp_contracts.ui import UiMessage
from fsp_platform.app import ProblemError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import service as assessment
from app.candidates import service as candidates
from app.companies import service as companies
from app.graph import service as graph
from app.matching import needs as n
from app.matching.models import CategorySubscription as Sub
from app.matching.models import CategorySubscriptionHit as Hit
from app.matching.service import visible_ids
from app.notifications import service as notifications
from app.taxonomy import service as taxonomy

_PREVIEW_LIMIT = 5  # pseudo_id в payload уведомления


class SkillMin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=80)
    min_level: int = Field(default=2, ge=1, le=4)  # доверие ○○○○ … ●●●●


class SubscriptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profession: str = Field(min_length=1, max_length=80)
    grades: list[TestGrade] = Field(default_factory=list, max_length=3)  # пусто — любой
    skills: list[SkillMin] = Field(default_factory=list, max_length=10)
    salary_max: int | None = Field(default=None, ge=0)  # бюджет ₽/мес: ожидания не выше
    formats: list[str] = Field(default_factory=list, max_length=5)
    only_confirmed: bool = False


class SubscriptionOut(BaseModel):
    id: uuid.UUID
    profession: str
    grades: list[str]
    skills: list[SkillMin]
    salary_max: int | None
    formats: list[str]
    only_confirmed: bool
    created_at: datetime


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


def to_out(sub: Sub) -> SubscriptionOut:
    return SubscriptionOut(
        id=sub.id, profession=sub.profession, grades=list(sub.grades),
        skills=[SkillMin.model_validate(s) for s in sub.skills], salary_max=sub.salary_max,
        formats=list(sub.formats), only_confirmed=sub.only_confirmed,
        created_at=_aware(sub.created_at),
    )  # fmt: skip


async def create(
    session: AsyncSession, company_id: uuid.UUID, body: SubscriptionCreate, cfg: n.NeedsConfig
) -> Sub:
    if body.profession not in {p.slug for p in await taxonomy.list_professions(session)}:
        raise ProblemError(422, "invalid_category", "Неизвестная профессия")
    known = await taxonomy.resolve_slugs(session, [s.slug for s in body.skills])
    if missing := [s.slug for s in body.skills if s.slug not in known]:
        raise ProblemError(422, "invalid_skill", f"Неизвестные навыки: {', '.join(missing)}")
    total = await session.scalar(
        select(func.count()).select_from(Sub).where(Sub.company_id == company_id)
    )
    if (total or 0) >= cfg.max_subscriptions:
        raise ProblemError(429, "subscription_limit", "Слишком много подписок")
    sub = Sub(
        company_id=company_id, profession=body.profession,
        grades=sorted({g.value for g in body.grades}),
        skills=[s.model_dump() for s in body.skills], salary_max=body.salary_max,
        formats=sorted(set(body.formats)), only_confirmed=body.only_confirmed,
    )  # fmt: skip
    session.add(sub)
    await session.flush()
    return sub


async def list_for(session: AsyncSession, company_id: uuid.UUID) -> list[Sub]:
    rows = await session.scalars(
        select(Sub).where(Sub.company_id == company_id).order_by(Sub.created_at, Sub.id)
    )
    return list(rows)


async def delete(session: AsyncSession, company_id: uuid.UUID, sub_id: uuid.UUID) -> None:
    """Чужая или несуществующая подписка → 404."""
    sub = await session.get(Sub, sub_id)
    if sub is None or sub.company_id != company_id:
        raise ProblemError(404, "subscription_not_found", "Подписка не найдена")
    await session.delete(sub)
    await session.flush()


def _fits(sub: Sub, cand: Any, grade: Any, levels: dict[str, int]) -> bool:
    if sub.grades and grade.grade.value not in sub.grades:
        return False
    if sub.only_confirmed and (grade.needs_confirmation or grade.low_confidence):
        return False
    if str(sub.company_id) in (cand.stoplist_company_ids or ()) or cand.search_status == "dnd":
        return False
    if sub.salary_max is not None and (
        cand.salary_min is not None and cand.salary_min > sub.salary_max
    ):
        return False
    if sub.formats and not set(sub.formats) & set(cand.formats or ()):
        return False
    return all(levels.get(s["slug"], 0) >= s.get("min_level", 1) for s in sub.skills)


async def register_hits(
    session: AsyncSession, candidate_id: uuid.UUID, categories: list[CategoryRef]
) -> set[uuid.UUID]:
    """Новые попадания кандидата в подписки (по полному набору категорий). Возвращает id подписок
    с новыми попаданиями. Идемпотентно: уже записанный кандидат подписку не будит."""
    professions = {c.profession for c in categories}
    if not professions:
        return set()
    subs = list(await session.scalars(select(Sub).where(Sub.profession.in_(professions))))
    if not subs or candidate_id not in await visible_ids(session, [candidate_id]):
        return set()
    cand = await candidates.get(session, candidate_id)
    if cand is None or cand.deleted_at is not None:
        return set()
    by_prof = (await assessment.get_grades_many(session, [candidate_id])).get(candidate_id, [])
    grades = {g.profession: g for g in by_prof}
    owned = (await graph.all_skills_of(session, [candidate_id]))[candidate_id]
    slugs = await taxonomy.skill_slugs(session, [s.skill_id for s in owned])
    levels = {slugs[s.skill_id]: s.level for s in owned if s.skill_id in slugs}
    have = set(
        await session.scalars(
            select(Hit.subscription_id).where(
                Hit.candidate_id == candidate_id, Hit.subscription_id.in_([s.id for s in subs])
            )
        )
    )
    now = datetime.now(UTC)
    touched: set[uuid.UUID] = set()
    for sub in subs:
        grade = grades.get(sub.profession)
        if sub.id in have or grade is None:
            continue
        if _fits(sub, cand, grade, levels):
            session.add(Hit(subscription_id=sub.id, candidate_id=candidate_id, created_at=now))
            touched.add(sub.id)
    await session.flush()
    return touched


async def flush_due(
    session: AsyncSession,
    cfg: n.NeedsConfig,
    *,
    only: set[uuid.UUID] | None = None,
    now: datetime | None = None,
) -> list[UiMessage]:
    """Дайджест: подписки с неотправленными попаданиями, у которых прошёл интервал. SSE-сообщения
    возвращаем вызывающему (он публикует их после коммита)."""
    now = now or datetime.now(UTC)
    stmt = select(Sub).where(
        Sub.id.in_(select(Hit.subscription_id).where(Hit.notified_at.is_(None)))
    )
    if only is not None:
        stmt = stmt.where(Sub.id.in_(only))
    interval = timedelta(minutes=cfg.subscription_digest_minutes)
    profs = {p.slug: p.title for p in await taxonomy.list_professions(session, include_hidden=True)}
    out: list[UiMessage] = []
    for sub in list(await session.scalars(stmt.order_by(Sub.id))):
        last = _aware(sub.last_digest_at)
        if last is not None and now - last < interval:
            continue
        hits = list(
            await session.scalars(
                select(Hit)
                .where(Hit.subscription_id == sub.id, Hit.notified_at.is_(None))
                .order_by(Hit.created_at, Hit.candidate_id)
            )
        )
        pseudo: list[str] = []
        for h in hits[:_PREVIEW_LIMIT]:
            cand = await candidates.get(session, h.candidate_id)
            if cand is not None:
                pseudo.append(cand.pseudo_id)
        title = profs.get(sub.profession, sub.profession)
        payload = {
            "subscription_id": str(sub.id), "profession": sub.profession,
            "count": len(hits), "pseudo_ids": pseudo,
        }  # fmt: skip
        for user_id in await companies.member_user_ids(session, sub.company_id):
            await notifications.notify(
                session, user_id, type="category_subscription",
                title=f"Новые кандидаты по подписке «{title}»: {len(hits)}",
                payload=payload, out=out, tg=TgTemplate.category_subscription,
                tg_data={"title": title, "count": len(hits)},
            )  # fmt: skip
        for h in hits:
            h.notified_at = now
        sub.last_digest_at = now
    await session.flush()
    return out


async def recent_hits(
    session: AsyncSession, company_id: uuid.UUID, limit: int
) -> list[tuple[Sub, Hit]]:
    """Свежие попадания кандидатов в подписки компании (для ленты активности)."""
    rows = await session.execute(
        select(Sub, Hit)
        .join(Hit, Hit.subscription_id == Sub.id)
        .where(Sub.company_id == company_id)
        .order_by(Hit.created_at.desc(), Hit.candidate_id)
        .limit(limit)
    )
    return [(s, h) for s, h in rows]
