"""Подсказки навыков и профессий для полей ввода (`/taxonomy/skills/suggest`).

Поиск по нормализованной форме: точное совпадение → префикс → слово/подстрока → триграммы
(опечатки). Внутри класса совпадения ранжирует частота у кандидатов и вакансий (`support_*`),
для запроса с профессией — ещё и вес навыка в ней. «Точно разные» (Java ≠ JavaScript) не
подмешиваются через нечёткое совпадение. Слитые и отклонённые навыки не отдаём, `provisional`
помечен.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from fsp_contracts.assessment import ProfessionSuggestion, SkillSuggestion
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.taxonomy.loader import norm_alias
from app.taxonomy.models import Role, RoleSkill, Skill, SkillAlias, SkillDistinct

FUZZY_MIN = 0.3  # порог сходства триграмм
_EXACT, _PREFIX, _WORD, _FUZZY = 3, 2, 1, 0


def trigrams(text: str) -> set[str]:
    padded = f"  {text} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def similarity(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def match_form(q: str, form: str, q_tri: set[str]) -> tuple[int, float] | None:
    """(класс совпадения, сила 0..1) формы с запросом или None."""
    if form == q:
        return _EXACT, 1.0
    if form.startswith(q):
        return _PREFIX, 0.8 + 0.2 * len(q) / len(form)
    if any(w.startswith(q) for w in form.replace("-", " ").replace(".", " ").split()):
        return _WORD, 0.6 + 0.2 * len(q) / len(form)
    if len(q) >= 2 and q in form:
        return _WORD, 0.5 * len(q) / len(form) + 0.1
    if len(q) >= 3:
        sim = similarity(q_tri, trigrams(form))
        if sim >= FUZZY_MIN:
            return _FUZZY, 0.6 * sim
    return None


def _freq(n: int, top: int) -> float:
    return math.log1p(n) / math.log1p(top) if top > 0 else 0.0


@dataclass
class _Hit:
    skill: Skill
    tier: int
    strength: float
    matched: str | None


async def suggest_skills(
    session: AsyncSession,
    q: str,
    limit: int = 10,
    profession: str | None = None,
    kind: str | None = None,
) -> list[SkillSuggestion]:
    nq = norm_alias(q)
    query = select(Skill).where(Skill.status.in_(("active", "provisional")))
    if kind:  # только навыки заданного вида (например, soft для «Личных качеств»)
        query = query.where(Skill.kind == kind)
    skills = {s.id: s for s in await session.scalars(query)}
    forms: dict[uuid.UUID, list[str]] = {}
    for a in await session.scalars(select(SkillAlias)):
        if a.skill_id in skills:
            forms.setdefault(a.skill_id, []).append(a.alias_norm)
    weights: dict[uuid.UUID, float] = {}
    if profession:
        for rs in await session.scalars(select(RoleSkill).where(RoleSkill.role == profession)):
            weights[rs.skill_id] = rs.weight
    top = max((s.support_candidates + s.support_vacancies for s in skills.values()), default=0)

    def rank(h: _Hit) -> float:
        s = h.skill
        f = _freq(s.support_candidates + s.support_vacancies, top)
        return round(min(1.0, 0.7 * h.strength + 0.2 * f + 0.1 * weights.get(s.id, 0.0)), 4)

    hits: list[_Hit] = []
    if not nq:  # пустой запрос: самые частые (в профессии — её навыки)
        hits = [
            _Hit(s, _WORD, 0.5, None) for s in skills.values() if not weights or s.id in weights
        ]
    else:
        q_tri = trigrams(nq)
        for sid, s in skills.items():
            best: _Hit | None = None
            own = (norm_alias(s.name), norm_alias(s.slug))
            for form in (*own, *forms.get(sid, [])):
                m = match_form(nq, form, q_tri)
                if m and (best is None or m > (best.tier, best.strength)):
                    best = _Hit(s, m[0], m[1], None if form in own else form)
            if best:
                hits.append(best)
    hits.sort(key=lambda h: (-h.tier, -rank(h), h.skill.slug))
    if any(h.tier == _FUZZY for h in hits):
        # нечёткое совпадение не подтягивает «точно разных» к уже найденному навыку
        pairs = {(d.skill_a, d.skill_b) for d in await session.scalars(select(SkillDistinct))}
        kept: list[_Hit] = []
        for h in hits:
            if h.tier == _FUZZY and any(
                (h.skill.id, k.skill.id) in pairs or (k.skill.id, h.skill.id) in pairs for k in kept
            ):
                continue
            kept.append(h)
        hits = kept
    return [
        SkillSuggestion(
            slug=h.skill.slug,
            name=h.skill.name,
            group=h.skill.grp,
            provisional=h.skill.status == "provisional",
            matched=h.matched,
            score=rank(h),
        )
        for h in hits[:limit]
    ]


async def suggest_professions(
    session: AsyncSession, q: str, limit: int = 10
) -> list[ProfessionSuggestion]:
    """Все видимые профессии системы, в том числе добавленные админом (`roles.is_active`)."""
    nq = norm_alias(q)
    q_tri = trigrams(nq)
    out: list[tuple[int, float, Role]] = []
    for r in await session.scalars(select(Role).where(Role.is_active.is_(True))):
        if not nq:
            out.append((_WORD, 0.5, r))
            continue
        best = None
        for form in (norm_alias(r.name), norm_alias(r.slug.replace("_", " "))):
            m = match_form(nq, form, q_tri)
            if m and (best is None or m > best):
                best = m
        if best:
            out.append((best[0], best[1], r))
    out.sort(key=lambda x: (-x[0], -x[1], x[2].slug))
    return [
        ProfessionSuggestion(slug=r.slug, title=r.name, score=round(st, 4))
        for _, st, r in out[:limit]
    ]
