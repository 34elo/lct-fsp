"""Поиск по каталогу анонимных карточек (api.md §2.5, matching.md §11, messaging.md §6).

Работодатель получает только `CandidateCard`: псевдоним, роль, грейд, навыки с уровнем доверия,
ФСП-достижения, вилка и форматы. Имени, контактов, user_id, компаний и репозиториев в DTO нет.
Фильтры анкеты — SQL, фильтры навыков — по `candidate_skills`; порядок и курсор — в памяти
(каталог — сотни анкет). Страница кешируется на 60 с по версии каталога.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

from fsp_contracts.ml import ExplanationItem, SearchFilters
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service as candidates
from app.candidates.models import Candidate
from app.graph import service as graph
from app.graph.trust import EvidenceView, TrustConfig, effective_strength
from app.matching.scoring import MatchConfig, MatchResult, score_candidate
from app.matching.service import build_views, load_vacancy
from app.taxonomy import service as taxonomy

CACHE_TTL = 60
MAX_LIMIT = 100
TOP_SKILLS = 8
FSP_HIGHLIGHTS = 3
TRUST_TOP = 5  # доверие кандидата = среднее по пяти сильнейшим навыкам
NICE_WEIGHT = 0.5

Sort = Literal["match", "trust", "fresh"]


class SkillBrief(BaseModel):
    slug: str
    name: str
    level: int
    sources: list[str]


class FspHighlight(BaseModel):
    title: str
    level: str
    place: int | None = None
    of: int | None = None
    year: int


class CardMatch(BaseModel):
    score: float
    explanation: list[ExplanationItem]


class CandidateCard(BaseModel):
    """Единственное представление кандидата для работодателя до принятия оффера."""

    pseudo_id: str
    pseudonym: str
    avatar_seed: str
    primary_role: str | None
    grade: str | None
    grade_preliminary: bool
    primary_stack: list[str]
    top_skills: list[SkillBrief]
    fsp_highlights: list[FspHighlight]
    salary_min: int | None
    formats: list[str]
    city: str | None
    relocation: bool
    search_status: str
    match: CardMatch | None = None
    updated_at: datetime


@dataclass(slots=True)
class Row:
    cand: Candidate
    trust: float
    relevance: float
    skills: list[Any]
    result: MatchResult | None = None

    def key(self, sort: Sort) -> float:
        if sort == "fresh":
            return _ts(self.cand.updated_at)
        if sort == "trust":
            return self.trust
        if self.result is not None:
            return self.result.score
        return self.relevance


def _ts(d: datetime) -> float:
    return (d if d.tzinfo else d.replace(tzinfo=UTC)).timestamp()


def grades_between(lo: str | None, hi: str | None) -> list[str] | None:
    if lo is None and hi is None:
        return None
    order = candidates.GRADE_ORDER
    i = order.index(lo) if lo else 0
    j = order.index(hi) if hi else len(order) - 1
    return list(order[i : j + 1])


def trust_of(skills: list[Any]) -> float:
    top = sorted((s.confidence for s in skills if not s.claimed_only), reverse=True)[:TRUST_TOP]
    return round(sum(top) / TRUST_TOP, 6)


def relevance_of(
    held: dict[uuid.UUID, Any], must: dict[uuid.UUID, float], nice: list[uuid.UUID]
) -> float:
    """Без вакансии «match» — покрытие запрошенных навыков по доверию (nice весит вдвое меньше)."""
    total = len(must) + NICE_WEIGHT * len(nice)
    if total == 0:
        return 0.0
    got = sum(min(1.0, held[s].confidence) for s in must if s in held)
    got += NICE_WEIGHT * sum(min(1.0, held[s].confidence) for s in nice if s in held)
    return round(got / total, 6)


def encode_cursor(sort: Sort, key: float, pseudo_id: str) -> str:
    raw = json.dumps([sort, round(key, 6), pseudo_id], separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str, sort: Sort) -> tuple[float, str] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        s, key, pid = json.loads(raw)
        if s != sort or not isinstance(pid, str):
            return None
        return float(key), pid
    except (ValueError, TypeError):
        return None


def cache_key(catalog_v: str, payload: dict[str, Any], cursor: str | None) -> str:
    sha = hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return f"c:search:{catalog_v}:{sha}:{cursor or '-'}"


async def _fsp_highlights(
    session: AsyncSession, ids: list[uuid.UUID], trust: TrustConfig, today: date
) -> dict[uuid.UUID, list[FspHighlight]]:
    best: dict[uuid.UUID, dict[uuid.UUID, tuple[float, FspHighlight]]] = {}
    for ev in await graph.evidence_of(session, ids, source="fsp"):
        d = ev.details or {}
        label = d.get("label")
        if ev.fact_type != "fsp_result" or not isinstance(label, str):
            continue
        s = effective_strength(
            EvidenceView(ev.id, ev.source, ev.strength, ev.observed_at, ev.verified), today, trust
        )
        if s <= 0:
            continue
        item = FspHighlight(
            title=label, level=str(d.get("level") or ""), place=d.get("place"),
            of=d.get("participants"), year=ev.observed_at.year,
        )  # fmt: skip
        per = best.setdefault(ev.candidate_id, {})  # один факт даёт несколько навыков
        if ev.fact_id not in per or s > per[ev.fact_id][0]:
            per[ev.fact_id] = (s, item)
    return {
        cid: [h for _, h in sorted(per.values(), key=lambda t: -t[0])[:FSP_HIGHLIGHTS]]
        for cid, per in best.items()
    }


def _card(
    c: Candidate,
    skills: list[Any],
    names: dict[uuid.UUID, tuple[str, str]],
    highlights: list[FspHighlight],
    result: MatchResult | None,
) -> CandidateCard:
    ordered = sorted(skills, key=lambda s: (s.claimed_only, -s.confidence, str(s.skill_id)))
    top = [
        SkillBrief(slug=names[s.skill_id][0], name=names[s.skill_id][1], level=s.level,
                   sources=list(s.sources or ()))
        for s in ordered[:TOP_SKILLS]
        if s.skill_id in names
    ]  # fmt: skip
    return CandidateCard(
        pseudo_id=c.pseudo_id,
        pseudonym=c.pseudonym,
        avatar_seed=hashlib.sha1(c.pseudo_id.encode()).hexdigest()[:12],
        primary_role=c.primary_role,
        grade=c.grade,
        grade_preliminary=c.grade_confidence is None or c.grade_confidence < 0.5,
        primary_stack=list(c.primary_stack or ()),
        top_skills=top,
        fsp_highlights=highlights,
        salary_min=c.salary_min,
        formats=list(c.formats or ()),
        city=c.city,
        relocation=c.relocation,
        search_status=candidates.effective_status(c),
        match=CardMatch(score=result.score, explanation=result.explanation) if result else None,
        updated_at=c.updated_at,
    )


async def search_candidates(
    session: AsyncSession,
    redis: Redis | None,
    *,
    company_id: uuid.UUID,
    filters: SearchFilters,
    sort: Sort,
    cursor: str | None,
    limit: int,
    vacancy_id: uuid.UUID | None,
    vacancy_version: int | None,
    cfg: MatchConfig,
    trust: TrustConfig,
    today: date | None = None,
) -> dict[str, Any]:
    """Страница выдачи `{items, next_cursor, total}`; `items` — JSON-словари `CandidateCard`."""
    limit = max(1, min(limit, MAX_LIMIT))
    after = decode_cursor(cursor, sort) if cursor else None
    key = cache_key(
        await candidates.catalog_version(session),
        {"company": str(company_id), "f": filters.model_dump(mode="json"), "sort": sort,
         "vacancy": [str(vacancy_id), vacancy_version], "limit": limit},
        cursor,
    )  # fmt: skip
    if redis is not None:
        try:
            if (hit := await redis.get(key)) is not None:
                return json.loads(hit)
        except Exception:  # noqa: BLE001 — кеш не должен ронять поиск
            pass

    day = today or datetime.now(UTC).date()
    f = filters
    pool = await candidates.search_pool(
        session, company_id=company_id, roles=[str(r) for r in f.roles] if f.roles else None,
        grades=grades_between(f.grade_min, f.grade_max), salary_max=f.salary_max,
        formats=[str(x) for x in f.formats] if f.formats else None,
        employment_types=[str(x) for x in f.employment_types] if f.employment_types else None,
        cities=f.cities, relocation_ok=f.relocation_ok, active_only=bool(f.active_only),
    )  # fmt: skip
    ids = [c.user_id for c in pool]
    owned = await graph.all_skills_of(session, ids)

    musts = f.skills_must or []
    slugs = [m.slug for m in musts] + list(f.skills_nice or [])
    by_slug = await taxonomy.resolve_slugs(session, slugs)
    min_trust = int(f.min_trust) if f.min_trust is not None else 0
    must_floor = {
        by_slug.get(m.slug): max(int(m.min_level or 0), min_trust) for m in musts
    }  # None — неизвестный навык: не найдёт никого
    nice_ids = [by_slug[s] for s in f.skills_nice or () if s in by_slug]
    disc = await graph.fsp_disciplines_of(session, ids) if f.fsp_only or f.fsp_disciplines else {}

    rows: list[Row] = []
    for c in pool:
        held = {s.skill_id: s for s in owned[c.user_id]}
        if any(
            sid is None or sid not in held or held[sid].level < floor
            for sid, floor in must_floor.items()
        ):
            continue
        if f.fsp_disciplines and not set(f.fsp_disciplines) & disc.get(c.user_id, set()):
            continue
        if f.fsp_only and not (
            disc.get(c.user_id) or any("fsp" in s.sources for s in held.values())
        ):
            continue
        rows.append(
            Row(c, trust_of(owned[c.user_id]),
                relevance_of(held, {k: 1.0 for k in must_floor if k}, nice_ids),
                owned[c.user_id])
        )  # fmt: skip

    if vacancy_id is not None and rows:
        loaded = await load_vacancy(session, vacancy_id)
        if loaded is not None:
            v, adj = loaded
            views = await build_views(session, [r.cand for r in rows], v, adj, trust, day)
            for r, view in zip(rows, views, strict=True):
                r.result = score_candidate(v, view, adj, cfg)

    def sortkey(r: Row) -> float:
        k = r.key(sort)
        if sort == "match" and vacancy_id is not None and r.result is None:
            k -= 10  # не прошёл жёсткие фильтры вакансии — после подходящих
        return round(k, 6)

    def order(r: Row) -> tuple[float, str]:
        return (-sortkey(r), r.cand.pseudo_id)

    rows.sort(key=order)
    total = len(rows)
    if after is not None:
        akey, apid = after
        rows = [r for r in rows if order(r) > (-akey, apid)]
    page = rows[:limit]
    next_cursor = (
        encode_cursor(sort, sortkey(page[-1]), page[-1].cand.pseudo_id)
        if len(rows) > limit
        else None
    )

    page_ids = [r.cand.user_id for r in page]
    sids = list({s.skill_id for r in page for s in r.skills})
    slug_of = await taxonomy.skill_slugs(session, sids)
    name_of = await taxonomy.skill_names(session, sids)
    names = {sid: (slug_of[sid], name_of.get(sid, slug_of[sid])) for sid in slug_of}
    highlights = await _fsp_highlights(session, page_ids, trust, day)
    items = [
        _card(r.cand, r.skills, names, highlights.get(r.cand.user_id, []), r.result).model_dump(
            mode="json"
        )
        for r in page
    ]
    out = {"items": items, "next_cursor": next_cursor, "total": total}
    if redis is not None:
        try:
            await redis.set(key, json.dumps(out, ensure_ascii=False), ex=CACHE_TTL)
        except Exception:  # noqa: BLE001
            pass
    return out
