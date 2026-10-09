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

from fsp_contracts.assessment import ProfessionInfo, SkillType
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
    SkillCardDraftRow,
    SkillDistinct,
    SkillMention,
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
        roles.append(
            {
                "slug": role.slug,
                "name": role.name,
                "profession": role.is_profession,
                "active": role.is_active,
                "skills": dict(sorted(ws.items())),
            }
        )
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
                "skill_type": s.skill_type,
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
        row.skill_type = data.skill_types[sk.slug].value
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
            row = roles[r.slug]
            row.name, row.is_profession, row.is_active = r.name, r.profession, r.active
        else:
            session.add(
                Role(slug=r.slug, name=r.name, is_profession=r.profession, is_active=r.active)
            )
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


@dataclass(frozen=True, slots=True)
class DisciplineRule:
    skill_id: uuid.UUID
    slug: str
    kind: str
    weight: float
    track: str | None


async def discipline_rules(session: AsyncSession) -> dict[str, list[DisciplineRule]]:
    """Правила «дисциплина (+трек) → навык» (fsp.md §5). Отклонённые и слитые навыки пропущены."""
    rows = await session.execute(
        select(DisciplineSkillRule, Skill)
        .join(Skill, Skill.id == DisciplineSkillRule.skill_id)
        .where(Skill.status.notin_(("merged", "rejected")))
        .order_by(DisciplineSkillRule.discipline, Skill.slug)
    )
    out: dict[str, list[DisciplineRule]] = {}
    for rule, sk in rows:
        out.setdefault(rule.discipline, []).append(
            DisciplineRule(sk.id, sk.slug, sk.kind, rule.weight, rule.track)
        )
    return out


async def adjacency(
    session: AsyncSession, skill_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[uuid.UUID, float]]]:
    """Смежные навыки (1 шаг, `kind=adjacent`) для каждого из `skill_ids`, только живые."""
    out: dict[uuid.UUID, list[tuple[uuid.UUID, float]]] = {i: [] for i in skill_ids}
    if not skill_ids:
        return out
    stmt = (
        select(SkillRelation.skill_a, SkillRelation.skill_b, SkillRelation.weight)
        .join(Skill, Skill.id == SkillRelation.skill_b)
        .where(
            SkillRelation.kind == "adjacent",
            SkillRelation.skill_a.in_(skill_ids),
            Skill.status.in_(_LIVE),
        )
        .order_by(SkillRelation.skill_a, SkillRelation.skill_b)
    )
    for a, b, w in (await session.execute(stmt)).all():
        out[a].append((b, w))
    return out


async def skill_names(session: AsyncSession, skill_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not skill_ids:
        return {}
    rows = await session.execute(select(Skill.id, Skill.name).where(Skill.id.in_(skill_ids)))
    return {sid: name for sid, name in rows.all()}


async def resolve_slugs(session: AsyncSession, slugs: list[str]) -> dict[str, uuid.UUID]:
    """slug → id живого навыка (слитый ведёт в целевой); неизвестные и `rejected` пропускаем."""
    if not slugs:
        return {}
    out: dict[str, uuid.UUID] = {}
    for s in await session.scalars(select(Skill).where(Skill.slug.in_(slugs))):
        if s.status == "merged" and s.merged_into:
            out[s.slug] = s.merged_into
        elif s.status != "rejected":
            out[s.slug] = s.id
    return out


async def skill_slugs(session: AsyncSession, skill_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not skill_ids:
        return {}
    rows = await session.execute(select(Skill.id, Skill.slug).where(Skill.id.in_(skill_ids)))
    return {sid: slug for sid, slug in rows.all()}


async def skill_briefs(
    session: AsyncSession, skill_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, str, str, str]]:
    """id → (slug, name, group, status) для витрин навыков."""
    if not skill_ids:
        return {}
    rows = await session.execute(
        select(Skill.id, Skill.slug, Skill.name, Skill.grp, Skill.status).where(
            Skill.id.in_(skill_ids)
        )
    )
    return {sid: (slug, name, grp or "", status) for sid, slug, name, grp, status in rows.all()}


async def testable_ids(session: AsyncSession, skill_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Навыки, по которым есть тест на платформе (`skills.testable`)."""
    if not skill_ids:
        return set()
    rows = await session.scalars(
        select(Skill.id).where(Skill.id.in_(skill_ids), Skill.testable.is_(True))
    )
    return set(rows)


@dataclass(frozen=True)
class AliasIndex:
    forms: dict[str, str]  # нормализованная форма → slug
    names: dict[str, str]  # slug → название


async def alias_index(session: AsyncSession) -> AliasIndex:
    """Нормализованная форма (slug, название, синонимы) → slug живого навыка.

    Слитый навык ведёт в целевой, `rejected` не попадает. Форма, указывающая на разные навыки,
    отбрасывается: разбор запроса не гадает.
    """
    skills = {
        s.id: s for s in await session.scalars(select(Skill).where(Skill.status != "rejected"))
    }

    def target(sk: Skill) -> Skill | None:
        if sk.status == "merged":
            t = skills.get(sk.merged_into) if sk.merged_into else None
            return t if t is not None and t.status != "merged" else None
        return sk

    forms: dict[str, set[str]] = {}
    for sk in skills.values():
        if (t := target(sk)) is not None:
            for f in (sk.slug, sk.name):
                forms.setdefault(norm_alias(f), set()).add(t.slug)
    for a in await session.scalars(select(SkillAlias)):
        if (sk := skills.get(a.skill_id)) is not None and (t := target(sk)) is not None:
            forms.setdefault(a.alias_norm, set()).add(t.slug)
    return AliasIndex(
        forms={f: next(iter(s)) for f, s in forms.items() if len(s) == 1},
        names={sk.slug: sk.name for sk in skills.values() if sk.status != "merged"},
    )


async def list_professions(
    session: AsyncSession, *, include_hidden: bool = False
) -> list[ProfessionInfo]:
    """Профессии теста (`roles.is_profession`), веса и типы навыков (blocks.md §4.3).

    По умолчанию — только активные (ADR-027 п.1: опрос, выдача, новые тесты). `include_hidden` —
    и скрытые: подписи и уже накопленные данные (грейды, попытки) по ним не пропадают.
    """
    q = select(Role).where(Role.is_profession.is_(True))
    if not include_hidden:
        q = q.where(Role.is_active.is_(True))
    roles = list(await session.scalars(q.order_by(Role.slug)))
    skills = {s.id: s for s in await session.scalars(select(Skill).where(Skill.status.in_(_LIVE)))}
    weights: dict[str, dict[str, float]] = {}
    for rs in await session.scalars(select(RoleSkill)):
        if rs.skill_id in skills:
            weights.setdefault(rs.role, {})[skills[rs.skill_id].slug] = rs.weight
    out = []
    for r in roles:
        ws = dict(sorted(weights.get(r.slug, {}).items()))
        types = {
            s.slug: SkillType(s.skill_type)
            for s in skills.values()
            if s.slug in ws and s.skill_type is not None
        }
        out.append(
            ProfessionInfo(
                slug=r.slug, title=r.name, skill_weights=ws, skill_types=types, active=r.is_active
            )
        )
    return out


async def skill_types_of(session: AsyncSession, slugs: list[str]) -> dict[str, SkillType]:
    """slug → тип навыка (живые навыки с заданным типом) — для плана теста по вакансии."""
    if not slugs:
        return {}
    rows = await session.execute(
        select(Skill.slug, Skill.skill_type).where(
            Skill.slug.in_(slugs), Skill.status.in_(_LIVE), Skill.skill_type.is_not(None)
        )
    )
    return {slug: SkillType(t) for slug, t in rows.all()}


async def skill_kinds(session: AsyncSession, skill_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """id → kind (`hard` | `soft` | …): ручная форма отделяет софт-навыки от стека."""
    if not skill_ids:
        return {}
    rows = await session.execute(select(Skill.id, Skill.kind).where(Skill.id.in_(skill_ids)))
    return {sid: kind for sid, kind in rows.all()}


# --- конвейер навыков: журнал решений и черновики карточек (E16-4) ---


def _clean_norm(norm: str) -> str | None:
    """ПДн и инъекции в справочник не пишем: ml маскирует `norm` как «[скрыто]»."""
    return None if not norm or norm == "[скрыто]" else norm


async def record_mention(
    session: AsyncSession,
    item: dict[str, Any],
    *,
    context: str | None = None,
    model_version: str | None = None,
) -> SkillMention | None:
    """Пишет решение ml (`SkillResolveItem` как dict) в журнал. None — писать нельзя (ПДн)."""
    norm = _clean_norm(item.get("norm", ""))
    if norm is None:
        return None
    skill = None
    if slug := item.get("skill_slug"):
        skill = await session.scalar(select(Skill.id).where(Skill.slug == slug))
    rel = item.get("relation")
    row = SkillMention(
        raw=item.get("raw", norm),
        norm=norm,
        context=context,
        decision=item["decision"],
        skill_id=skill,
        relation=f"{rel['type']}:{rel['to_slug']}" if rel else None,
        scores={"confidence": rel["confidence"]} if rel else None,
        model_version=model_version,
    )
    session.add(row)
    await session.flush()
    return row


async def cached_decision(session: AsyncSession, norm: str) -> SkillMention | None:
    """Кеш решений: последнее не отклонённое по ПДн решение для `norm` (повторное упоминание
    не идёт в ml). Пара-ловушка `skill_distinct` проверяется ml до записи, здесь не нужна."""
    return await session.scalar(
        select(SkillMention)
        .where(SkillMention.norm == norm)
        .order_by(SkillMention.id.desc())
        .limit(1)
    )


async def save_card_draft(
    session: AsyncSession, slug: str, draft: dict[str, Any]
) -> SkillCardDraftRow:
    """Сохраняет черновик карточки ml для навыка. Схема — `taxonomy/cards.py` (`SkillCard`).

    Тип карточки обязан совпасть с типом навыка в справочнике, если он задан. Ревью человеком
    обязательно: статус `draft` в каталог `data/skills/cards` сам не попадает.
    """
    from app.taxonomy.cards import SkillCard

    skill = await session.scalar(select(Skill).where(Skill.slug == slug))
    if skill is None:
        raise ValueError(f"навыка {slug!r} нет в справочнике")
    body = {k: v for k, v in draft.items() if k not in ("model", "draft")}
    body["skill"] = slug
    card = SkillCard.model_validate(body)
    if skill.skill_type and card.type.value != skill.skill_type:
        raise ValueError(f"type={card.type.value}, в справочнике {skill.skill_type}")
    row = await session.get(SkillCardDraftRow, skill.id)
    payload = card.model_dump(mode="json")
    if row is None:
        row = SkillCardDraftRow(skill_id=skill.id, card=payload, model=draft.get("model", ""))
        session.add(row)
    else:
        row.card, row.model, row.status = payload, draft.get("model", ""), "draft"
    await session.flush()
    return row


async def pending_merge_count(session: AsyncSession) -> int:
    """Число предложенных слияний навыков — счётчик на главной админки (E39-29)."""
    from app.taxonomy import decisions

    return len(await decisions.pending_merges(session))
