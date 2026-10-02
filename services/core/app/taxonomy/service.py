"""Загрузка ядра графа в БД, версия справочника, снимки (публичный и для ml).

Версия растёт только когда содержимое изменилось (хеш снимка); тогда в той же транзакции
в outbox пишется `taxonomy.updated {version, changed_skill_ids}` (messaging.md).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from fsp_contracts.envelope import new_envelope
from fsp_contracts.events import TaxonomyUpdated
from fsp_platform.outbox import add_to_outbox
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.taxonomy.loader import TaxonomyData, norm_alias
from app.taxonomy.models import (
    Discipline,
    DisciplineSkillRule,
    Role,
    RoleSkill,
    ScoringConfig,
    Skill,
    SkillAlias,
    SkillBlocklist,
    SkillDistinct,
    SkillRelation,
)

KEY = "taxonomy"
NS = uuid.UUID("5f0b8f0e-6f55-4b52-9a63-0c6a5a3b7a11")
DISCIPLINE_NAMES = {
    "algorithmic": "Алгоритмическое программирование",
    "product": "Продуктовое программирование",
    "security": "Информационная безопасность",
    "uav": "Беспилотные авиационные системы",
    "robotics": "Робототехника",
}
_LIVE = ("active", "provisional")


def skill_id(slug: str) -> uuid.UUID:
    """Стабильный id вершины ядра: одинаков в любой среде."""
    return uuid.uuid5(NS, f"skill:{slug}")


@dataclass
class SyncResult:
    version: int
    bumped: bool
    changed_skill_ids: list[uuid.UUID] = field(default_factory=list)
    skipped_rule_skills: list[str] = field(default_factory=list)
    skipped_aliases: list[str] = field(default_factory=list)


async def get_version(session: AsyncSession) -> int:
    row = await session.get(ScoringConfig, KEY)
    return row.version if row else 0


async def build_snapshot(session: AsyncSession) -> dict[str, Any]:
    """Весь граф без `version`: детерминированный порядок, пригоден для хеширования."""
    skills = list(
        await session.scalars(select(Skill).where(Skill.status.in_(_LIVE)).order_by(Skill.slug))
    )
    by_id = {s.id: s.slug for s in skills}
    aliases: dict[uuid.UUID, list[str]] = {}
    for a in await session.scalars(select(SkillAlias).order_by(SkillAlias.alias_norm)):
        aliases.setdefault(a.skill_id, []).append(a.alias_norm)
    adjacent, parent = [], []
    for r in await session.scalars(select(SkillRelation)):
        if r.skill_a not in by_id or r.skill_b not in by_id:
            continue
        a, b = by_id[r.skill_a], by_id[r.skill_b]
        if r.kind == "parent":
            parent.append({"child": a, "parent": b, "weight": r.weight})
        elif a < b:  # adjacent хранится в обе стороны, отдаём пару один раз
            adjacent.append({"a": a, "b": b, "weight": r.weight})
    distinct = sorted(
        sorted((by_id[d.skill_a], by_id[d.skill_b]))
        for d in await session.scalars(select(SkillDistinct))
        if d.skill_a in by_id and d.skill_b in by_id
    )
    roles = []
    for role in await session.scalars(select(Role).order_by(Role.slug)):
        ws = {
            by_id[rs.skill_id]: rs.weight
            for rs in await session.scalars(select(RoleSkill).where(RoleSkill.role == role.slug))
            if rs.skill_id in by_id
        }
        roles.append({"slug": role.slug, "name": role.name, "skills": dict(sorted(ws.items()))})
    disciplines = []
    for d in await session.scalars(select(Discipline).order_by(Discipline.slug)):
        rules = sorted(
            (
                {"skill": by_id[r.skill_id], "weight": r.weight, "track": r.track}
                for r in await session.scalars(
                    select(DisciplineSkillRule).where(DisciplineSkillRule.discipline == d.slug)
                )
                if r.skill_id in by_id
            ),
            key=lambda x: (x["track"] or "", x["skill"]),
        )
        disciplines.append({"slug": d.slug, "name": d.name, "rules": rules})
    return {
        "skills": [
            {
                "id": str(s.id),
                "slug": s.slug,
                "name": s.name,
                "kind": s.kind,
                "group": s.grp,
                "status": s.status,
                "testable": s.testable,
                "description": s.description,
                "aliases": aliases.get(s.id, []),
            }
            for s in skills
        ],
        "adjacent": sorted(adjacent, key=lambda x: (x["a"], x["b"])),
        "parent": sorted(parent, key=lambda x: (x["child"], x["parent"])),
        "distinct": distinct,
        "roles": roles,
        "disciplines": disciplines,
    }


def snapshot_hash(snap: dict[str, Any]) -> str:
    raw = json.dumps(snap, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _fingerprints(snap: dict[str, Any]) -> dict[str, str]:
    """Отпечаток каждой вершины: её поля + всё, что к ней привязано."""
    parts: dict[str, list[Any]] = {s["slug"]: [s] for s in snap["skills"]}

    def put(slug: str, item: Any) -> None:
        if slug in parts:
            parts[slug].append(item)

    for r in snap["adjacent"]:
        put(r["a"], ["adj", r]), put(r["b"], ["adj", r])
    for r in snap["parent"]:
        put(r["child"], ["par", r]), put(r["parent"], ["par", r])
    for a, b in snap["distinct"]:
        put(a, ["dis", a, b]), put(b, ["dis", a, b])
    for role in snap["roles"]:
        for slug, w in role["skills"].items():
            put(slug, ["role", role["slug"], w])
    for d in snap["disciplines"]:
        for r in d["rules"]:
            put(r["skill"], ["disc", d["slug"], r])
    return {slug: snapshot_hash({"p": p}) for slug, p in parts.items()}


async def sync(session: AsyncSession, data: TaxonomyData) -> SyncResult:
    """Идемпотентно приводит БД к YAML. Правки, сделанные не сидом (pipeline/admin), не трогает."""
    before = await build_snapshot(session)
    skipped_aliases: list[str] = []

    existing = {s.slug: s for s in await session.scalars(select(Skill))}
    for sk in data.skills:
        row = existing.get(sk.slug)
        if row is None:
            row = Skill(
                id=skill_id(sk.slug), slug=sk.slug, source="seed", status="active", name=sk.name
            )
            session.add(row)
            existing[sk.slug] = row
        elif row.source != "seed":
            continue  # правка администратора/конвейера важнее сида
        row.name, row.kind, row.grp = sk.name, sk.kind, sk.group
        row.testable, row.description = sk.testable, sk.description
    await session.flush()
    ids = {slug: row.id for slug, row in existing.items()}

    # синонимы: slug и имя тоже ищутся как синонимы
    desired: dict[str, str] = {}
    for sk in data.skills:
        for a in [sk.slug, sk.name, *sk.aliases]:
            desired.setdefault(norm_alias(a), sk.slug)
    have = {a.alias_norm: a for a in await session.scalars(select(SkillAlias))}
    for norm, a in have.items():
        if a.source == "seed" and norm not in desired:
            await session.delete(a)
    for norm, slug in desired.items():
        cur = have.get(norm)
        if cur is None:
            session.add(SkillAlias(alias_norm=norm, skill_id=ids[slug], source="seed"))
        elif cur.skill_id != ids[slug]:
            if cur.source == "seed":
                cur.skill_id = ids[slug]
            else:
                skipped_aliases.append(norm)

    # связи: смежность в обе стороны, иерархия направленная
    want: dict[tuple[uuid.UUID, uuid.UUID, str], float] = {}
    for r in data.adjacent:
        want[(ids[r.a], ids[r.b], "adjacent")] = r.weight
        want[(ids[r.b], ids[r.a], "adjacent")] = r.weight
    for p in data.parent:
        want[(ids[p.child], ids[p.parent], "parent")] = p.weight
    rels = {(r.skill_a, r.skill_b, r.kind): r for r in await session.scalars(select(SkillRelation))}
    for key, r in rels.items():
        if r.source == "seed" and key not in want:
            await session.delete(r)
    for key, w in want.items():
        cur = rels.get(key)
        if cur is None:
            session.add(
                SkillRelation(skill_a=key[0], skill_b=key[1], kind=key[2], weight=w, source="seed")
            )
        elif cur.source == "seed":
            cur.weight = w

    pairs = {tuple(sorted((ids[a], ids[b]), key=str)) for a, b in data.distinct}
    have_pairs = {(d.skill_a, d.skill_b): d for d in await session.scalars(select(SkillDistinct))}
    for key, d in have_pairs.items():
        if key not in pairs:
            await session.delete(d)
    for a, b in pairs - have_pairs.keys():
        session.add(SkillDistinct(skill_a=a, skill_b=b))

    known_block = set(await session.scalars(select(SkillBlocklist.norm)))
    for b in data.blocklist:
        if (n := norm_alias(b.norm)) not in known_block:
            session.add(SkillBlocklist(norm=n, reason=b.reason))
            known_block.add(n)

    # роли
    roles = {r.slug: r for r in await session.scalars(select(Role))}
    for r in data.roles:
        if r.slug in roles:
            roles[r.slug].name = r.name
        else:
            session.add(Role(slug=r.slug, name=r.name))
    await session.flush()
    have_rs = {(x.role, x.skill_id): x for x in await session.scalars(select(RoleSkill))}
    want_rs = {(r.slug, ids[s]): w for r in data.roles for s, w in r.skills.items()}
    for key, x in have_rs.items():
        if x.source == "seed" and key not in want_rs:
            await session.delete(x)
    for key, w in want_rs.items():
        if key in have_rs:
            if have_rs[key].source == "seed":
                have_rs[key].weight = w
        else:
            session.add(RoleSkill(role=key[0], skill_id=key[1], weight=w, source="seed"))

    # правила дисциплин ФСП (навыки, которых нет в ядре, пропускаем и сообщаем)
    skipped_rules: list[str] = []
    if data.discipline_rules:
        discs = {d.slug: d for d in await session.scalars(select(Discipline))}
        for slug in data.discipline_rules:
            if slug not in discs:
                session.add(Discipline(slug=slug, name=DISCIPLINE_NAMES.get(slug, slug)))
        await session.flush()
        want_dr: dict[tuple[str, uuid.UUID, str], float] = {}
        for disc, rules in data.discipline_rules.items():
            for skill, w, track in rules:
                if skill not in ids:
                    skipped_rules.append(f"{disc}:{skill}")
                    continue
                want_dr[(disc, ids[skill], track or "")] = w
        have_dr = {
            (x.discipline, x.skill_id, x.track or ""): x
            for x in await session.scalars(select(DisciplineSkillRule))
        }
        for key, x in have_dr.items():
            if key not in want_dr:
                await session.delete(x)
        for key, w in want_dr.items():
            if key in have_dr:
                have_dr[key].weight = w
            else:
                session.add(
                    DisciplineSkillRule(
                        discipline=key[0], skill_id=key[1], weight=w, track=key[2] or None
                    )
                )
    await session.flush()

    after = await build_snapshot(session)
    digest = snapshot_hash(after)
    cfg = await session.get(ScoringConfig, KEY)
    if cfg is not None and cfg.value.get("hash") == digest:
        return SyncResult(cfg.version, False, [], skipped_rules, skipped_aliases)

    fb, fa = _fingerprints(before), _fingerprints(after)
    changed = sorted(s for s in fb.keys() | fa.keys() if fb.get(s) != fa.get(s))
    changed_ids = [skill_id_of(after, before, s) for s in changed]
    version = (cfg.version if cfg else 0) + 1
    if cfg is None:
        session.add(ScoringConfig(key=KEY, value={"hash": digest}, version=version))
    else:
        cfg.value, cfg.version = {"hash": digest}, version
    event = TaxonomyUpdated(version=version, changed_skill_ids=changed_ids)
    await add_to_outbox(session, new_envelope("taxonomy.updated", "core", event))
    return SyncResult(version, True, changed_ids, skipped_rules, skipped_aliases)


def skill_id_of(after: dict[str, Any], before: dict[str, Any], slug: str) -> uuid.UUID:
    for snap in (after, before):
        for s in snap["skills"]:
            if s["slug"] == slug:
                return uuid.UUID(s["id"])
    raise KeyError(slug)  # недостижимо: slug взят из одного из снимков


@dataclass(frozen=True, slots=True)
class SkillGraph:
    """Граф навыков в памяти core (graph.md §3): версия справочника, slug и иерархия «вверх»."""

    version: int
    slugs: dict[uuid.UUID, str]
    parents: dict[uuid.UUID, tuple[tuple[uuid.UUID, float], ...]]  # child → ((parent, coef), …)
    roles: dict[str, dict[uuid.UUID, float]] = field(default_factory=dict)  # role → {skill: вес}
    stack_ids: frozenset[uuid.UUID] = frozenset()  # языки и их фреймворки (ml.md §4)

    def parents_of(self, skill_id: uuid.UUID) -> tuple[tuple[uuid.UUID, float], ...]:
        return self.parents.get(skill_id, ())


async def load_skill_graph(session: AsyncSession) -> SkillGraph:
    version = await get_version(session)
    live = list(await session.scalars(select(Skill).where(Skill.status.in_(_LIVE))))
    slugs = {s.id: s.slug for s in live}
    parents: dict[uuid.UUID, list[tuple[uuid.UUID, float]]] = {}
    for r in await session.scalars(select(SkillRelation).where(SkillRelation.kind == "parent")):
        if r.skill_a in slugs and r.skill_b in slugs:
            parents.setdefault(r.skill_a, []).append((r.skill_b, r.weight))
    roles: dict[str, dict[uuid.UUID, float]] = {}
    for rs in await session.scalars(select(RoleSkill)):
        if rs.skill_id in slugs:
            roles.setdefault(rs.role, {})[rs.skill_id] = rs.weight
    langs = {s.id for s in live if s.grp == "language"}
    stack_ids = frozenset(
        langs | {c for c, ps in parents.items() if any(p in langs for p, _ in ps)}
    )
    return SkillGraph(
        version,
        slugs,
        {k: tuple(sorted(v, key=lambda x: str(x[0]))) for k, v in parents.items()},
        roles,
        stack_ids,
    )


class SkillGraphCache:
    """Держит граф в памяти процесса; сбрасывается по `taxonomy.updated` и сверкой версии."""

    def __init__(self) -> None:
        self._graph: SkillGraph | None = None
        self._lock = asyncio.Lock()

    def invalidate(self) -> None:
        self._graph = None

    async def get(self, session: AsyncSession) -> SkillGraph:
        async with self._lock:
            g = self._graph
            if g is None or g.version != await get_version(session):
                g = self._graph = await load_skill_graph(session)
            return g
