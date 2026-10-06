"""Ночной рост связей графа навыков (skills.md §5, E16-6): `refresh`.

Из профилей кандидатов (уровень ≥ 2) и требований опубликованных вакансий считаем:
- NPMI пар → рёбра `adjacent` (`source=cooccurrence`);
- `lift(навык, роль)` → веса `role_skills` (`source=data`) для навыков вне ядра;
- подсказки экспертам ФСП (дисциплина, навык) и кандидатов в новые профессии (кластеры);
- продвижение `provisional → active` по поддержке ≥ 5 разных кандидатов.

Формулы чистые (юнит-тесты на числах из документа), сбор данных отдельно. Подсказки не
применяются сами: лежат в `scoring_config` под ключом `taxonomy_hints`. Вакансии читаются через
`vacancies.service`; ПДн нет: только идентификаторы навыков и slug'и.
"""

from __future__ import annotations

import math
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import utcnow
from app.taxonomy.decisions import _table, publish_change
from app.taxonomy.models import (
    Discipline,
    DisciplineSkillRule,
    Role,
    RoleSkill,
    ScoringConfig,
    Skill,
    SkillRelation,
)
from app.vacancies import service as vacancies

HINTS_KEY = "taxonomy_hints"
SOURCE_EDGE = "cooccurrence"
SOURCE_ROLE = "data"

MIN_LEVEL = 2  # уровень навыка кандидата, с которого он входит в корзину
NPMI_MIN = 0.3
EDGE_SUPPORT = 5
EDGE_BASE, EDGE_K, EDGE_MAX = 0.4, 0.5, 0.9
ROLE_SUPPORT = 5
ROLE_K, ROLE_MAX = 0.2, 0.8
HINT_LIFT, HINT_SUPPORT = 2.0, 10
PROMOTE_SUPPORT = 5
CLUSTER_MIN_SIZE = 3
CLUSTER_MAX_COVERED = 0.3  # доля навыков кластера, уже входящая в одну из профессий
CLUSTER_SUPPORT = 5


# --- формулы ---------------------------------------------------------------------------------


def npmi(n_ab: int, n_a: int, n_b: int, n: int) -> float:
    """`log(p(a,b) / (p(a)·p(b))) / −log p(a,b)`; 0 при отсутствии пары, 1 при полном совпадении."""
    if n_ab <= 0 or n <= 0:
        return 0.0
    p_ab = n_ab / n
    if p_ab >= 1.0:
        return 1.0
    return math.log(p_ab * n * n / (n_a * n_b)) / -math.log(p_ab)


def edge_weight(value: float) -> float:
    return min(EDGE_MAX, EDGE_BASE + EDGE_K * value)


def lift(n_sr: int, n_r: int, n_s: int, n: int) -> float:
    """`p(s | r) / p(s)`."""
    if n_r <= 0 or n_s <= 0 or n <= 0:
        return 0.0
    return (n_sr / n_r) / (n_s / n)


def role_weight(value: float) -> float:
    return min(ROLE_MAX, ROLE_K * math.log2(value)) if value > 1 else 0.0


def strong_pairs(
    baskets: list[set[uuid.UUID]],
) -> dict[tuple[uuid.UUID, uuid.UUID], float]:
    """Пары (a < b по str) с поддержкой ≥ 5 и npmi ≥ 0.3 → npmi."""
    n = len(baskets)
    singles: Counter[uuid.UUID] = Counter()
    pairs: Counter[tuple[uuid.UUID, uuid.UUID]] = Counter()
    for b in baskets:
        singles.update(b)
        pairs.update(combinations(sorted(b, key=str), 2))
    out = {}
    for (a, b), n_ab in pairs.items():
        if n_ab < EDGE_SUPPORT:
            continue
        v = npmi(n_ab, singles[a], singles[b], n)
        if v >= NPMI_MIN:
            out[(a, b)] = v
    return out


def clusters(pairs: dict[tuple[uuid.UUID, uuid.UUID], float]) -> list[set[uuid.UUID]]:
    """Связные компоненты графа сильных пар размером ≥ 3."""
    adj: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for a, b in pairs:
        adj[a].add(b)
        adj[b].add(a)
    seen: set[uuid.UUID] = set()
    out = []
    for start in sorted(adj, key=str):
        if start in seen:
            continue
        comp, stack = set(), [start]
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp.add(x)
            stack.extend(adj[x] - comp)
        seen |= comp
        if len(comp) >= CLUSTER_MIN_SIZE:
            out.append(comp)
    return out


# --- сбор данных -----------------------------------------------------------------------------


@dataclass
class Baskets:
    """Единицы наблюдения: кандидат или вакансия → (набор навыков, роль)."""

    skills: list[set[uuid.UUID]] = field(default_factory=list)
    roles: list[str | None] = field(default_factory=list)
    candidate_ids: list[uuid.UUID | None] = field(default_factory=list)  # None — вакансия

    def add(self, skills: set[uuid.UUID], role: str | None, cid: uuid.UUID | None) -> None:
        self.skills.append(skills)
        self.roles.append(role)
        self.candidate_ids.append(cid)


async def gather(session: AsyncSession, live: set[uuid.UUID]) -> Baskets:
    out = Baskets()
    cs, cand = _table("candidate_skills"), _table("candidates")
    by_cand: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    rows = await session.execute(
        select(cs.c.candidate_id, cs.c.skill_id).where(cs.c.level >= MIN_LEVEL)
    )
    for cid, sid in rows.all():
        if sid in live:
            by_cand[cid].add(sid)
    for cid, role in (await session.execute(select(cand.c.user_id, cand.c.primary_role))).all():
        if by_cand.get(cid):
            out.add(by_cand[cid], role, cid)
    vacs = await vacancies.list_published(session)
    by_vac = await vacancies.skills_of(session, [v.id for v in vacs])
    for v in vacs:
        ids = {vs.skill_id for vs, _ in by_vac[v.id] if vs.skill_id in live}
        if ids:
            out.add(ids, v.role, None)
    return out


# --- шаги ------------------------------------------------------------------------------------


@dataclass
class Report:
    edges_added: int = 0
    edges_updated: int = 0
    edges_removed: int = 0
    role_skills: int = 0
    promoted: list[str] = field(default_factory=list)
    discipline_hints: list[dict[str, Any]] = field(default_factory=list)
    profession_candidates: list[dict[str, Any]] = field(default_factory=list)
    version: int | None = None


async def _sync_edges(
    session: AsyncSession, pairs: dict[tuple[uuid.UUID, uuid.UUID], float], rep: Report
) -> set[uuid.UUID]:
    """Рёбра `cooccurrence` приводятся к `pairs`; рёбра судьи и админа не трогаем."""
    touched: set[uuid.UUID] = set()
    want = {(x, y): edge_weight(v) for (a, b), v in pairs.items() for x, y in ((a, b), (b, a))}
    existing = {
        (r.skill_a, r.skill_b): r
        for r in await session.scalars(
            select(SkillRelation).where(SkillRelation.kind == "adjacent")
        )
    }
    for key, w in want.items():
        old = existing.get(key)
        if old is None:
            session.add(
                SkillRelation(
                    skill_a=key[0], skill_b=key[1], kind="adjacent", weight=w, source=SOURCE_EDGE
                )
            )
            rep.edges_added += 1
        elif old.source == SOURCE_EDGE and abs(old.weight - w) > 1e-9:
            old.weight = w
            rep.edges_updated += 1
        else:
            continue
        touched.update(key)
    for key, old in existing.items():
        if old.source == SOURCE_EDGE and key not in want:
            await session.delete(old)
            rep.edges_removed += 1
            touched.update(key)
    await session.flush()
    return touched


async def _sync_role_skills(session: AsyncSession, data: Baskets, rep: Report) -> set[uuid.UUID]:
    """`role_skills` с `source=data` только для навыков, которых нет в ядре ни у одной роли."""
    n = len(data.skills)
    n_s: Counter[uuid.UUID] = Counter()
    n_r: Counter[str] = Counter()
    n_sr: Counter[tuple[uuid.UUID, str]] = Counter()
    for sk, role in zip(data.skills, data.roles, strict=True):
        n_s.update(sk)
        if role:
            n_r[role] += 1
            n_sr.update((s, role) for s in sk)
    roles = set(await session.scalars(select(Role.slug)))
    rows = list(await session.scalars(select(RoleSkill)))
    core = {r.skill_id for r in rows if r.source != SOURCE_ROLE}
    have = {(r.role, r.skill_id): r for r in rows if r.source == SOURCE_ROLE}
    want: dict[tuple[str, uuid.UUID], float] = {}
    for (s, r), cnt in n_sr.items():
        if cnt < ROLE_SUPPORT or r not in roles or s in core:
            continue
        w = role_weight(lift(cnt, n_r[r], n_s[s], n))
        if w > 0:
            want[(r, s)] = w
    touched: set[uuid.UUID] = set()
    for (r, s), w in want.items():
        old = have.get((r, s))
        if old is None:
            session.add(RoleSkill(role=r, skill_id=s, weight=w, source=SOURCE_ROLE))
        elif abs(old.weight - w) > 1e-9:
            old.weight = w
        else:
            continue
        rep.role_skills += 1
        touched.add(s)
    for key, old in have.items():
        if key not in want:
            await session.delete(old)
            rep.role_skills += 1
            touched.add(key[1])
    await session.flush()
    return touched


async def _discipline_hints(
    session: AsyncSession, data: Baskets, slugs: dict[uuid.UUID, str]
) -> list[dict[str, Any]]:
    """Дисциплина × навык: lift ≥ 2 и поддержка ≥ 10 среди участников, правила ещё нет."""
    fr = _table("fsp_results")
    members: dict[str, set[uuid.UUID]] = defaultdict(set)
    for cid, disc in (await session.execute(select(fr.c.candidate_id, fr.c.discipline))).all():
        if disc:
            members[disc].add(cid)
    cand_basket = {c: s for c, s in zip(data.candidate_ids, data.skills, strict=True) if c}
    total = len(cand_basket)
    n_s: Counter[uuid.UUID] = Counter()
    for s in cand_basket.values():
        n_s.update(s)
    names = dict((await session.execute(select(Discipline.slug, Discipline.name))).all())
    ruled = {(r.discipline, r.skill_id) for r in await session.scalars(select(DisciplineSkillRule))}
    out = []
    for disc in sorted(members):
        part = [cand_basket[c] for c in members[disc] if c in cand_basket]
        if not part:
            continue
        cnt: Counter[uuid.UUID] = Counter()
        for s in part:
            cnt.update(s)
        for sid, k in cnt.items():
            if k < HINT_SUPPORT or (disc, sid) in ruled:
                continue
            lf = lift(k, len(part), n_s[sid], total)
            if lf >= HINT_LIFT:
                out.append(
                    {
                        "discipline": disc,
                        "discipline_name": names.get(disc),
                        "skill": slugs[sid],
                        "lift": round(lf, 3),
                        "support": k,
                    }
                )
    out.sort(key=lambda h: (-h["lift"], h["discipline"], h["skill"]))
    return out


async def _profession_candidates(
    session: AsyncSession,
    data: Baskets,
    pairs: dict[tuple[uuid.UUID, uuid.UUID], float],
    slugs: dict[uuid.UUID, str],
) -> list[dict[str, Any]]:
    """Кластеры сильно связанных навыков, которые не покрыты ни одной профессией."""
    prof = set(await session.scalars(select(Role.slug).where(Role.is_profession)))
    role_sk: dict[str, set[uuid.UUID]] = defaultdict(set)
    for rs in await session.scalars(select(RoleSkill)):
        if rs.role in prof:
            role_sk[rs.role].add(rs.skill_id)
    out = []
    for comp in clusters(pairs):
        covered = max((len(comp & s) / len(comp) for s in role_sk.values()), default=0.0)
        if covered > CLUSTER_MAX_COVERED:
            continue
        need = max(2, math.ceil(len(comp) / 2))
        inside = [b & comp for b in data.skills if len(b & comp) >= need]
        if len(inside) < CLUSTER_SUPPORT:
            continue
        freq: Counter[uuid.UUID] = Counter()
        for b in inside:
            freq.update(b)
        top = sorted(comp, key=lambda s: (-freq[s], slugs[s]))
        out.append(
            {
                "skills": [slugs[s] for s in top],
                "support": len(inside),
                "covered_by_professions": round(covered, 3),
            }
        )
    out.sort(key=lambda c: (-c["support"], c["skills"]))
    return out


async def _promote(session: AsyncSession, rep: Report) -> set[uuid.UUID]:
    """Поддержка считается и по кандидатам, и по вакансиям; `provisional → active` по кандидатам."""
    cs = _table("candidate_skills")
    n_cand = dict(
        (
            await session.execute(select(cs.c.skill_id, sa.func.count()).group_by(cs.c.skill_id))
        ).all()
    )
    vs = _table("vacancy_skills")
    n_vac = dict(
        (
            await session.execute(select(vs.c.skill_id, sa.func.count()).group_by(vs.c.skill_id))
        ).all()
    )
    touched: set[uuid.UUID] = set()
    for sk in await session.scalars(
        select(Skill).where(Skill.status.in_(("active", "provisional")))
    ):
        sk.support_candidates = n_cand.get(sk.id, 0)
        sk.support_vacancies = n_vac.get(sk.id, 0)
        if sk.status == "provisional" and sk.support_candidates >= PROMOTE_SUPPORT:
            sk.status = "active"
            rep.promoted.append(sk.slug)
            touched.add(sk.id)
    await session.flush()
    return touched


async def _save_hints(session: AsyncSession, rep: Report) -> None:
    value = {
        "updated_at": utcnow().isoformat(),
        "discipline_rules": rep.discipline_hints,
        "profession_candidates": rep.profession_candidates,
    }
    cfg = await session.get(ScoringConfig, HINTS_KEY)
    if cfg is None:
        session.add(ScoringConfig(key=HINTS_KEY, value=value, version=1))
    else:
        cfg.value, cfg.version = value, cfg.version + 1
    await session.flush()


async def refresh(session: AsyncSession) -> Report:
    """Одна ночная итерация; идемпотентна. Изменение графа → `taxonomy.updated`."""
    rep = Report()
    # продвижение первым: новые активные навыки сразу участвуют в рёбрах и ролях
    rep_touched = await _promote(session, rep)
    skills = list(
        await session.scalars(select(Skill).where(Skill.status.in_(("active", "provisional"))))
    )
    slugs = {s.id: s.slug for s in skills}
    data = await gather(session, set(slugs))
    pairs = strong_pairs(data.skills)
    touched = (
        rep_touched
        | await _sync_edges(session, pairs, rep)
        | await _sync_role_skills(session, data, rep)
    )
    rep.discipline_hints = await _discipline_hints(session, data, slugs)
    rep.profession_candidates = await _profession_candidates(session, data, pairs, slugs)
    await _save_hints(session, rep)
    if touched:
        rep.version = await publish_change(session, sorted(touched, key=str))
    return rep
