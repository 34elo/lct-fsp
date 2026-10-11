"""Применение решений графа навыков.

- `apply_decisions` — решения конвейера ml (`SkillResolveItem`): новые вершины `provisional`,
  синонимы, связи, стоп-лист; журнал `skill_mentions` пишется тут же;
- `merge` / `revert_merge` — слияние задним числом и откат по журналу `skill_merges`;
- «точно разные» (`skill_distinct`) и стоп-лист (`skill_blocklist`): CRUD для админки;
- `approve` / `reject` — решения админа по вершине.

Любое изменение графа в той же транзакции поднимает версию справочника и пишет
`taxonomy.updated` в outbox: обработчик пересчитывает затронутых кандидатов.
Таблицы других модулей (доказательства, `vacancy_skills`) переносятся по их имени в метаданных,
без импорта чужих моделей; правила схлопывания дублей описаны в `_REPOINT`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from fsp_contracts.envelope import new_envelope
from fsp_contracts.events import TaxonomyUpdated
from fsp_contracts.ml import SkillResolveItem
from fsp_platform.app import ProblemError
from fsp_platform.db import Base
from fsp_platform.outbox import add_to_outbox
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import utcnow
from app.taxonomy.loader import norm_alias
from app.taxonomy.models import (
    ScoringConfig,
    Skill,
    SkillAlias,
    SkillBlocklist,
    SkillDistinct,
    SkillMention,
    SkillMerge,
    SkillRelation,
)
from app.taxonomy.service import KEY, build_snapshot, record_mention, snapshot_hash

PARENT_WEIGHT = 0.6  # ребро «часть» по умолчанию
RELATED_FACTOR = 0.8  # вес «смежен» = оценка судьи × 0.8
_LIVE = ("active", "provisional")
_SKILL_TYPE = {"hard": "hard", "soft": "soft", "domain": "business"}


# --- версия справочника и событие -----------------------------------------------------------


async def publish_change(session: AsyncSession, skill_ids: list[uuid.UUID]) -> int | None:
    """Поднимает версию справочника и пишет `taxonomy.updated`, если снимок изменился."""
    digest = snapshot_hash(await build_snapshot(session))
    cfg = await session.get(ScoringConfig, KEY)
    if cfg is not None and cfg.value.get("hash") == digest:
        return None
    version = (cfg.version if cfg else 0) + 1
    if cfg is None:
        session.add(ScoringConfig(key=KEY, value={"hash": digest}, version=version))
    else:
        cfg.value, cfg.version = {"hash": digest}, version
    ids = list(dict.fromkeys(skill_ids))
    event = TaxonomyUpdated(version=version, changed_skill_ids=ids)
    await add_to_outbox(session, new_envelope("taxonomy.updated", "core", event))
    await session.flush()
    return version


# --- «точно разные» и стоп-лист ----------------------------------------------------------------


def _pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (a, b) if str(a) < str(b) else (b, a)


async def _by_slug(session: AsyncSession, slug: str) -> Skill:
    sk = await session.scalar(select(Skill).where(Skill.slug == slug))
    if sk is None:
        raise ProblemError(404, "skill_not_found", "Навык не найден", slug)
    return sk


async def is_distinct(session: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> bool:
    x, y = _pair(a, b)
    return (await session.get(SkillDistinct, (x, y))) is not None


async def add_distinct(session: AsyncSession, slug_a: str, slug_b: str) -> bool:
    """Помечает пару «точно разные». False — пара уже была. Слитую пару пометить нельзя."""
    a, b = await _by_slug(session, slug_a), await _by_slug(session, slug_b)
    if a.id == b.id:
        raise ProblemError(422, "distinct_same_skill", "Навык нельзя отличить от самого себя")
    if a.merged_into == b.id or b.merged_into == a.id:
        raise ProblemError(409, "distinct_already_merged", "Навыки уже слиты: сначала откатите")
    if await is_distinct(session, a.id, b.id):
        return False
    x, y = _pair(a.id, b.id)
    session.add(SkillDistinct(skill_a=x, skill_b=y))
    await session.flush()
    await publish_change(session, [a.id, b.id])
    return True


async def remove_distinct(session: AsyncSession, slug_a: str, slug_b: str) -> bool:
    a, b = await _by_slug(session, slug_a), await _by_slug(session, slug_b)
    x, y = _pair(a.id, b.id)
    row = await session.get(SkillDistinct, (x, y))
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    await publish_change(session, [a.id, b.id])
    return True


async def list_distinct(session: AsyncSession) -> list[tuple[str, str]]:
    slugs = {s.id: s.slug for s in await session.scalars(select(Skill))}
    rows = await session.scalars(select(SkillDistinct))
    return sorted((slugs[r.skill_a], slugs[r.skill_b]) for r in rows)


async def is_blocked(session: AsyncSession, norm: str) -> bool:
    return (await session.get(SkillBlocklist, norm_alias(norm))) is not None


async def add_blocklist(session: AsyncSession, norm: str, reason: str | None = None) -> bool:
    key = norm_alias(norm)
    if not key or key == "[скрыто]" or await session.get(SkillBlocklist, key):
        return False
    session.add(SkillBlocklist(norm=key, reason=reason))
    await session.flush()
    return True


async def remove_blocklist(session: AsyncSession, norm: str) -> bool:
    row = await session.get(SkillBlocklist, norm_alias(norm))
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True


# --- решения конвейера ---


@dataclass
class Applied:
    norm: str
    decision: str
    skill_id: uuid.UUID | None = None
    created: bool = False
    alias_added: bool = False
    relation: str | None = None  # parent | adjacent | same_pending
    blocked: bool = False
    note: str | None = None


@dataclass
class _Batch:
    changed: list[uuid.UUID] = field(default_factory=list)


async def _add_alias(
    session: AsyncSession, norm: str, skill: Skill, source: str, confidence: float | None = None
) -> bool:
    key = norm_alias(norm)
    if not key or key in (norm_alias(skill.slug), norm_alias(skill.name)):
        return False
    row = await session.get(SkillAlias, key)
    if row is not None:
        return False  # синоним другого (или этого же) навыка не перезаписываем
    session.add(SkillAlias(alias_norm=key, skill_id=skill.id, source=source, confidence=confidence))
    await session.flush()
    return True


async def _add_relation(
    session: AsyncSession,
    a: uuid.UUID,
    b: uuid.UUID,
    kind: str,
    weight: float,
    confidence: float,
) -> bool:
    """Ребро графа от конвейера; чужие рёбра не перезаписываются, `adjacent` — в обе стороны."""
    pairs = [(a, b), (b, a)] if kind == "adjacent" else [(a, b)]
    added = False
    for x, y in pairs:
        if await session.get(SkillRelation, (x, y, kind)) is None:
            session.add(
                SkillRelation(
                    skill_a=x,
                    skill_b=y,
                    kind=kind,
                    weight=weight,
                    source="pipeline",
                    confidence=confidence,
                )
            )
            added = True
    await session.flush()
    return added


async def _new_vertex(session: AsyncSession, item: SkillResolveItem) -> tuple[Skill, bool]:
    slug = item.skill_slug or ""
    sk = await session.scalar(select(Skill).where(Skill.slug == slug))
    if sk is not None:
        return sk, False
    kind = item.kind if item.kind in _SKILL_TYPE else "hard"
    sk = Skill(
        id=uuid.uuid4(),
        slug=slug,
        name=item.raw.strip() or slug,
        kind=kind,
        status="provisional",
        source="pipeline",
        skill_type=_SKILL_TYPE[kind],
    )
    session.add(sk)
    await session.flush()
    return sk, True


async def _apply_one(
    session: AsyncSession,
    item: SkillResolveItem,
    *,
    context: str | None,
    model_version: str | None,
    batch: _Batch,
) -> Applied:
    norm = item.norm
    res = Applied(norm=norm, decision=item.decision)
    hidden = norm == "[скрыто]"

    if item.decision == "rejected":
        if not hidden and item.reason == "moderation":
            await add_blocklist(session, norm, item.reason)
        await record_mention(
            session, item.model_dump(), context=context, model_version=model_version
        )
        return res

    if item.skill_slug is None:
        res.note = "нет skill_slug"
        return res

    if item.decision in ("alias", "fuzzy"):
        sk = await session.scalar(select(Skill).where(Skill.slug == item.skill_slug))
        if sk is None or sk.status not in _LIVE:
            res.note = "целевой навык не найден"
            return res
        res.skill_id = sk.id
        res.alias_added = await _add_alias(session, norm, sk, "pipeline", None)
        if res.alias_added:
            batch.changed.append(sk.id)
        await record_mention(
            session, item.model_dump(), context=context, model_version=model_version
        )
        return res

    # new | same_pending: новая вершина provisional. Стоп-лист проверяется до создания.
    if await is_blocked(session, norm):
        res.blocked, res.decision, res.note = True, "rejected", "в стоп-листе"
        return res
    sk, res.created = await _new_vertex(session, item)
    res.skill_id = sk.id
    if await _add_alias(session, norm, sk, "pipeline", None):
        res.alias_added = True
    rel = item.relation
    if rel is not None:
        target = await session.scalar(select(Skill).where(Skill.slug == rel.to_slug))
        if target is not None and target.id != sk.id and target.status in _LIVE:
            if rel.type == "same":
                res.relation = "same_pending"  # слияние решает админ (очередь `pending_merges`)
            elif rel.type == "narrower":  # упоминание уже навыка: новая вершина — часть целевой
                if await _add_relation(
                    session, sk.id, target.id, "parent", PARENT_WEIGHT, rel.confidence
                ):
                    res.relation = "parent"
            elif rel.type == "broader":
                if await _add_relation(
                    session, target.id, sk.id, "parent", PARENT_WEIGHT, rel.confidence
                ):
                    res.relation = "parent"
            elif rel.type == "related":
                w = round(min(1.0, rel.confidence * RELATED_FACTOR), 2)
                if await _add_relation(session, sk.id, target.id, "adjacent", w, rel.confidence):
                    res.relation = "adjacent"
            if res.relation:
                batch.changed.append(target.id)
    if res.created or res.alias_added or res.relation not in (None, "same_pending"):
        batch.changed.append(sk.id)
    await record_mention(session, item.model_dump(), context=context, model_version=model_version)
    return res


async def apply_decisions(
    session: AsyncSession,
    items: list[dict[str, Any] | SkillResolveItem],
    *,
    context: str | None = None,
    model_version: str | None = None,
) -> list[Applied]:
    """Применяет пачку решений ml. Идемпотентно: повтор того же решения ничего не создаёт."""
    batch = _Batch()
    out: list[Applied] = []
    for raw in items:
        item = raw if isinstance(raw, SkillResolveItem) else SkillResolveItem.model_validate(raw)
        out.append(
            await _apply_one(
                session, item, context=context, model_version=model_version, batch=batch
            )
        )
    if batch.changed:
        await publish_change(session, batch.changed)
    return out


async def pending_merges(session: AsyncSession) -> list[dict[str, Any]]:
    """Очередь админа: предложенные слияния («то же», уверенность 0.6–0.9) для живых вершин."""
    rows = await session.scalars(
        select(SkillMention)
        .where(SkillMention.decision == "same_pending")
        .order_by(SkillMention.id.desc())
    )
    seen: set[uuid.UUID] = set()
    out: list[dict[str, Any]] = []
    for m in rows:
        if m.skill_id is None or m.skill_id in seen or not m.relation:
            continue
        seen.add(m.skill_id)
        sk = await session.get(Skill, m.skill_id)
        if sk is None or sk.status != "provisional":
            continue
        target = await session.scalar(
            select(Skill).where(Skill.slug == m.relation.split(":", 1)[1])
        )
        if target is None or target.status not in _LIVE:
            continue
        out.append(
            {
                "skill": sk.slug,
                "into": target.slug,
                "confidence": (m.scores or {}).get("confidence"),
                "norm": m.norm,
            }
        )
    return out


# --- решения админа по вершине -------------------------------------------------------------------


async def approve(session: AsyncSession, slug: str) -> Skill:
    sk = await _by_slug(session, slug)
    if sk.status == "active":
        return sk
    if sk.status != "provisional":
        raise ProblemError(409, "skill_bad_status", "Подтвердить можно только временный навык")
    sk.status = "active"
    await session.flush()
    await publish_change(session, [sk.id])
    return sk


async def reject(session: AsyncSession, slug: str) -> Skill:
    sk = await _by_slug(session, slug)
    if sk.status == "rejected":
        return sk
    if sk.status != "provisional":
        raise ProblemError(409, "skill_bad_status", "Отклонить можно только временный навык")
    sk.status = "rejected"
    await session.flush()
    await publish_change(session, [sk.id])
    return sk


# --- слияние и откат -----------------------------------------------------------------------------

Row = dict[str, Any]
Resolve = Callable[[Row, Row], Row | None]


def _max_weight(old: Row, new: Row) -> Row | None:
    return {"weight": new["weight"]} if new["weight"] > old["weight"] else None


def _stronger_evidence(old: Row, new: Row) -> Row | None:
    if new["strength"] <= old["strength"]:
        return None
    return {k: new[k] for k in ("strength", "observed_at", "details", "verified", "is_active")}


def _vacancy(old: Row, new: Row) -> Row | None:
    merged = {
        "required": bool(old["required"] or new["required"]),
        "min_level": max(old["min_level"], new["min_level"]),
        "weight": max(old["weight"], new["weight"]),
    }
    diff = {k: v for k, v in merged.items() if old[k] != v}
    return diff or None


@dataclass(frozen=True)
class _Repoint:
    table: str
    skill_cols: tuple[str, ...]
    unique: tuple[str, ...]  # колонки ключа уникальности без skill-колонок
    resolve: Resolve | None = None  # при дубле: что обновить у существующей строки


# Что переносится при слиянии. Дубль по ключу схлопывается: остаётся сильнейшее.
_REPOINT: tuple[_Repoint, ...] = (
    _Repoint("skill_relations", ("skill_a", "skill_b"), ("kind",), _max_weight),
    _Repoint("role_skills", ("skill_id",), ("role",), _max_weight),
    _Repoint("discipline_skill_rules", ("skill_id",), ("discipline", "track"), _max_weight),
    _Repoint("skill_distinct", ("skill_a", "skill_b"), (), None),
    _Repoint("vacancy_skills", ("skill_id",), ("vacancy_id",), _vacancy),
    _Repoint(
        "evidence",
        ("skill_id",),
        ("candidate_id", "source", "fact_type", "fact_id"),
        _stronger_evidence,
    ),
)
_INPLACE = (("skill_aliases", "alias_norm"), ("skill_mentions", "id"))  # (таблица, ключ)


def _table(name: str) -> sa.Table:
    return Base.metadata.tables[name]


def _enc(v: Any) -> Any:
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, dt.datetime | dt.date):
        return v.isoformat()
    return v


def _dump(table: sa.Table, row: Any) -> Row:
    return {c.name: _enc(row[c.name]) for c in table.columns}


def _dec(col: sa.Column, v: Any) -> Any:
    if v is None:
        return None
    try:
        py = col.type.python_type
    except NotImplementedError:
        return v
    if py is uuid.UUID:
        return uuid.UUID(v)
    if py is dt.datetime:
        return dt.datetime.fromisoformat(v)
    if py is dt.date:
        return dt.date.fromisoformat(v)
    return v


def _load(table: sa.Table, row: Row) -> Row:
    return {k: _dec(table.c[k], v) for k, v in row.items()}


def _pk(table: sa.Table, row: Row) -> Row:
    return {c.name: row[c.name] for c in table.primary_key.columns}


def _where(table: sa.Table, key: Row) -> sa.ColumnElement[bool]:
    return sa.and_(*(table.c[k] == v for k, v in key.items()))


async def _repoint(session: AsyncSession, spec: _Repoint, frm: uuid.UUID, into: uuid.UUID) -> Row:
    """Переносит строки `frm` → `into` в таблице; возвращает записи для отката."""
    t = _table(spec.table)
    cond = sa.or_(*(t.c[c] == frm for c in spec.skill_cols))
    rows = [dict(r) for r in (await session.execute(sa.select(t).where(cond))).mappings()]
    removed: list[Row] = []
    added: list[Row] = []
    changed: list[Row] = []
    for old in rows:
        new = {k: (into if k in spec.skill_cols and v == frm else v) for k, v in old.items()}
        removed.append(_dump(t, old))
        await session.execute(sa.delete(t).where(_where(t, _pk(t, old))))
        if spec.table == "skill_distinct":
            a, b = _pair(new["skill_a"], new["skill_b"])
            new["skill_a"], new["skill_b"] = a, b
        if len(spec.skill_cols) == 2 and new[spec.skill_cols[0]] == new[spec.skill_cols[1]]:
            continue  # петля после слияния
        key_cols = (*spec.skill_cols, *spec.unique)
        dup = (
            (await session.execute(sa.select(t).where(_where(t, {c: new[c] for c in key_cols}))))
            .mappings()
            .first()
        )
        if dup is not None:
            dup = dict(dup)
            upd = spec.resolve(dup, new) if spec.resolve else None
            if upd:
                changed.append(
                    {
                        "pk": {k: _enc(v) for k, v in _pk(t, dup).items()},
                        "old": {k: _enc(dup[k]) for k in upd},
                    }
                )
                await session.execute(sa.update(t).where(_where(t, _pk(t, dup))).values(**upd))
            continue
        await session.execute(sa.insert(t).values(**new))
        added.append({k: _enc(v) for k, v in _pk(t, new).items()})
    return {"removed": removed, "added": added, "changed": changed}


_MOVED_TABLES = {
    "skill_aliases",
    "skill_mentions",
    "skill_relations",
    "role_skills",
    "skill_distinct",
    "discipline_skill_rules",
    "vacancy_skills",
    "evidence",
    "candidate_skills",
}


def _expire_cached(session: AsyncSession) -> None:
    """Строки перенесены SQL-запросами: загруженные в сессию копии устарели."""
    for obj in list(session.identity_map.values()):
        if type(obj).__table__.name in _MOVED_TABLES:  # type: ignore[attr-defined]
            session.expire(obj)


async def _forbidden_by_distinct(session: AsyncSession, frm: Skill, into: Skill) -> bool:
    """«Точно разные» блокируют слияние и транзитивно: через уже слитые в обе стороны вершины."""

    async def group(sk: Skill) -> set[uuid.UUID]:
        kids = await session.scalars(select(Skill.id).where(Skill.merged_into == sk.id))
        return {sk.id, *kids}

    gf, gi = await group(frm), await group(into)
    for a in gf:
        for b in gi:
            if await is_distinct(session, a, b):
                return True
    return False


async def merge(
    session: AsyncSession, from_slug: str, into_slug: str, *, actor: str = "pipeline"
) -> SkillMerge:
    """`from` → `into`. Запрещено для пары «точно разные» (и через слитые)."""
    frm, into = await _by_slug(session, from_slug), await _by_slug(session, into_slug)
    if frm.id == into.id:
        raise ProblemError(422, "merge_same_skill", "Нельзя слить навык с самим собой")
    if frm.status not in _LIVE or into.status not in _LIVE:
        raise ProblemError(409, "skill_bad_status", "Слить можно только живые навыки")
    if frm.status == "active" and into.status == "provisional":
        raise ProblemError(
            409, "merge_into_provisional", "Активный навык нельзя слить во временный"
        )
    if await _forbidden_by_distinct(session, frm, into):
        raise ProblemError(
            409,
            "merge_forbidden_distinct",
            "Пара помечена «точно разные»",
            f"{from_slug} ≠ {into_slug}",
        )

    moved: dict[str, Any] = {
        "from_status": frm.status,
        "from_support": [frm.support_candidates, frm.support_vacancies],
        "tables": {},
        "inplace": {},
    }
    for spec in _REPOINT:
        moved["tables"][spec.table] = await _repoint(session, spec, frm.id, into.id)
    for name, key in _INPLACE:
        t = _table(name)
        ids = [
            _enc(r[0])
            for r in (
                await session.execute(sa.select(t.c[key]).where(t.c.skill_id == frm.id))
            ).all()
        ]
        if ids:
            await session.execute(
                sa.update(t)
                .where(t.c[key].in_([_dec(t.c[key], i) for i in ids]))
                .values(skill_id=into.id)
            )
        moved["inplace"][name] = ids
    # производные записи пересоберёт пересчёт профиля
    await session.execute(
        sa.delete(_table("candidate_skills")).where(_table("candidate_skills").c.skill_id == frm.id)
    )
    # название и slug слитого остаются синонимами цели
    extra = []
    for form in (frm.slug, frm.name):
        key = norm_alias(form)
        if key and key not in (norm_alias(into.slug), norm_alias(into.name)):
            if await session.get(SkillAlias, key) is None:
                session.add(
                    SkillAlias(alias_norm=key, skill_id=into.id, source="merge", confidence=1.0)
                )
                extra.append(key)
    moved["aliases_added"] = extra
    into.support_candidates += frm.support_candidates
    into.support_vacancies += frm.support_vacancies
    frm.status, frm.merged_into = "merged", into.id
    _expire_cached(session)
    rec = SkillMerge(from_skill=frm.id, into_skill=into.id, actor=actor, moved=moved)
    session.add(rec)
    await session.flush()
    await publish_change(session, [frm.id, into.id])
    return rec


async def revert_merge(session: AsyncSession, merge_id: uuid.UUID) -> SkillMerge:
    """Разделение: возвращает вершину, синонимы, связи и доказательства по журналу слияния."""
    rec = await session.get(SkillMerge, merge_id)
    if rec is None:
        raise ProblemError(404, "merge_not_found", "Слияние не найдено")
    if rec.reverted_at is not None:
        raise ProblemError(409, "merge_reverted", "Слияние уже откатано")
    frm, into = await session.get(Skill, rec.from_skill), await session.get(Skill, rec.into_skill)
    assert frm is not None and into is not None
    if frm.merged_into != into.id or into.status not in _LIVE:
        raise ProblemError(409, "merge_not_revertible", "Сначала откатите более позднее слияние")
    moved = rec.moved
    for name, info in reversed(list(moved["tables"].items())):
        t = _table(name)
        for k in info["added"]:
            await session.execute(sa.delete(t).where(_where(t, _load(t, k))))
        for ch in info["changed"]:
            await session.execute(
                sa.update(t).where(_where(t, _load(t, ch["pk"]))).values(**_load(t, ch["old"]))
            )
        for row in info["removed"]:
            await session.execute(sa.insert(t).values(**_load(t, row)))
    for name, key in _INPLACE:
        ids = moved["inplace"].get(name) or []
        if ids:
            t = _table(name)
            await session.execute(
                sa.update(t)
                .where(t.c[key].in_([_dec(t.c[key], i) for i in ids]))
                .values(skill_id=frm.id)
            )
    for key in moved.get("aliases_added", []):
        await session.execute(
            sa.delete(SkillAlias.__table__).where(
                SkillAlias.alias_norm == key, SkillAlias.skill_id == into.id
            )
        )
    cs, vs = moved["from_support"]
    into.support_candidates = max(0, into.support_candidates - cs)
    into.support_vacancies = max(0, into.support_vacancies - vs)
    frm.status, frm.merged_into = moved["from_status"], None
    _expire_cached(session)
    rec.reverted_at = utcnow()
    await session.flush()
    await publish_change(session, [frm.id, into.id])
    return rec
