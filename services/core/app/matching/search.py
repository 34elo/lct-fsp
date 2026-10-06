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

from fsp_contracts.assessment import CategoryRef
from fsp_contracts.ml import ExplanationItem, SearchFilters
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import service as assessment
from app.candidates import service as candidates
from app.candidates.models import Candidate
from app.graph import service as graph
from app.graph.trust import EvidenceView, TrustConfig, effective_strength
from app.matching.p_accept import PAcceptConfig, hint, mutual, p_accept
from app.matching.rerank import RerankConfig, mmr, multiplier
from app.matching.scoring import MatchConfig, MatchResult, score_candidate
from app.matching.service import build_views, load_vacancy, only_visible, visibility_version
from app.matching.strength import (
    StrengthConfig,
    StrengthInput,
    StrengthResult,
    StrengthView,
    completeness,
    rank,
    strength,
    view,
)
from app.offers import service as offers
from app.recommendations import service as recs
from app.recommendations import tuning as tun
from app.taxonomy import service as taxonomy

CACHE_TTL = 60
MAX_LIMIT = 100
TOP_SKILLS = 8
FSP_HIGHLIGHTS = 3
TRUST_TOP = 5  # доверие кандидата = среднее по пяти сильнейшим навыкам
NICE_WEIGHT = 0.5

Sort = Literal["match", "trust", "fresh", "mutual"]


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
    interest: str | None = None  # low | medium | high — интерес кандидата к вакансии (p_accept)


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
    categories: list[CategoryRef] = []  # подтверждённые тестом профессия × грейд (ADR-018)
    strength: StrengthView | None = None  # сила профиля внутри категории (assessment.md §9)


@dataclass(slots=True)
class Row:
    cand: Candidate
    trust: float
    relevance: float
    skills: list[Any]
    result: MatchResult | None = None
    p_accept: float | None = None
    mult: float = 1.0  # множитель переранжирования (matching.md §5)
    x: dict[str, float] | None = None  # признаки для подстройки в сессии (matching.md §7)
    tuned: float | None = None  # скор после подстройки в сессии
    strength: StrengthResult | None = None  # сила профиля (E23-2)
    rank_on: bool = False  # выбрана категория: порядок по rank = 0.6·match + 0.4·strength
    strength_cfg: StrengthConfig | None = None

    def key(self, sort: Sort) -> float:
        if sort == "fresh":
            return _ts(self.cand.updated_at)
        if sort == "trust":
            return self.trust
        if self.result is not None:
            score = self.tuned if self.tuned is not None else self.result.score
            score = self._ranked(score)
            if sort == "mutual" and self.p_accept is not None:
                return mutual(score, self.p_accept) * self.mult
            return score * self.mult
        return self._ranked(self.tuned if self.tuned is not None else self.relevance) * self.mult

    def _ranked(self, match: float) -> float:
        if self.rank_on and self.strength is not None and self.strength_cfg is not None:
            return rank(match, self.strength.value, self.strength_cfg)
        return match


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
    interest: str | None = None,
    categories: list[CategoryRef] | None = None,
    strength_view: StrengthView | None = None,
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
        match=CardMatch(score=result.score, explanation=result.explanation, interest=interest)
        if result
        else None,
        updated_at=c.updated_at,
        categories=categories or [],
        strength=strength_view,
    )


async def categories_of(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[CategoryRef]]:
    """Категории карточек пачкой (blocks.md §4.3, `get_grades_many`): профессия × грейд."""
    grades = await assessment.get_grades_many(session, ids)
    return {
        cid: [CategoryRef(profession=g.profession, grade=g.grade) for g in gs]
        for cid, gs in grades.items()
    }


def _strength_view(r: Row) -> StrengthView | None:
    if r.strength is None or r.strength_cfg is None:
        return None
    match = None
    if r.rank_on:
        match = r.tuned if r.tuned is not None else (r.result.score if r.result else r.relevance)
    return view(r.strength, r.strength_cfg, match)


async def _attach_strength(
    session: AsyncSession,
    rows: list[Row],
    category: CategoryRef | None,
    nice_ids: list[uuid.UUID],
    must_floor: dict[Any, int],
    day: date,
    cfg: StrengthConfig,
) -> None:
    """Сила профиля (assessment.md §9) по грейду выбранной категории, иначе по профессии
    `primary_role`, иначе по лучшему грейду. Без действующего грейда силы нет.

    F — наибольшее доверие по навыкам с источником `fsp` (нет ФСП — 0, без штрафа);
    S — среднее доверие по навыкам запроса, без запроса — `trust_of`; R — свежесть теста
    по `confirmed_at`; C — полнота анкеты."""
    grades = await assessment.get_grades_many(session, [r.cand.user_id for r in rows])
    need = [k for k in must_floor if k] + nice_ids
    for r in rows:
        gs = grades.get(r.cand.user_id) or []
        if category is not None:
            g = next((x for x in gs if x.profession == category.profession), None)
        else:
            g = next((x for x in gs if x.profession == r.cand.primary_role), None) or (
                max(gs, key=lambda x: x.theta) if gs else None
            )
        if g is None:
            continue
        held = {s.skill_id: s for s in r.skills}
        fsp = max((s.confidence for s in r.skills if "fsp" in s.sources), default=0.0)
        s_val = (
            sum(min(1.0, held[k].confidence) if k in held else 0.0 for k in need) / len(need)
            if need
            else r.trust
        )
        days = (datetime.combine(day, datetime.min.time(), UTC) - g.confirmed_at).days
        r.strength = strength(
            StrengthInput(
                band_position=g.band_position, fsp=fsp, skills=s_val, days_since_test=days,
                completeness=completeness(r.cand, len(r.skills)), integrity=g.integrity,
            ),
            cfg,
        )  # fmt: skip
        r.strength_cfg = cfg
        r.rank_on = category is not None


def features_of(r: Row) -> dict[str, float]:
    """Признаки подстройки (matching.md §7): компоненты скора и бинарные капитан/GitHub/«ищу».

    Без вакансии `skills` — покрытие запрошенных навыков, `fsp` — есть ли навык из ФСП.
    """
    if r.result is not None:
        b = r.result.breakdown
        x = {k: float(b.get(k, 0.0)) for k in ("skills", "semantic", "grade", "salary", "fsp")}
    else:
        fsp = any("fsp" in (s.sources or ()) for s in r.skills)
        x = {"skills": r.relevance, "semantic": 0.0, "grade": 0.0, "salary": 0.0,
             "fsp": 1.0 if fsp else 0.0}  # fmt: skip
    team = r.cand.team_signals or {}
    x["captain"] = float(
        any(
            f.get("kind") == "captain"
            for sig in team.values() if isinstance(sig, dict)
            for f in sig.get("facts") or ()
        )
    )  # fmt: skip
    x["github"] = float(any("github" in (s.sources or ()) for s in r.skills))
    x["active"] = float(candidates.effective_status(r.cand) == "active")
    return {k: round(v, 6) for k, v in x.items()}


def apply_tuning(
    rows: list[Row],
    signals: list[tun.Signal],
    snapshot: dict[str, dict[str, float]],
    query: Any,
    cfg: tun.TuningConfig,
) -> tun.Tuning:
    """Подстройка сессии: веса по снимкам признаков из показов, Роккио по векторам выдачи.

    Меняется только порядок уже прошедших фильтры: у вакансии `score' = min(1, Σw'·x ·
    score/base)` (K_soft и «ищу» сохраняются), без вакансии — `Σw'·x`.
    """
    embs = {str(r.cand.user_id): r.cand.embedding for r in rows}
    t = tun.build(signals, snapshot, cfg, embeddings=embs, query=query)
    if not t.active:
        return t
    for r in rows:
        if r.x is None:
            continue
        tb = tun.tuned_base(r.x, t, r.cand.embedding, cfg)
        if r.result is not None:
            base = float(r.result.breakdown.get("base") or 0.0)
            r.tuned = round(min(1.0, tb * (r.result.score / base if base > 0 else 1.0)), 6)
        else:
            r.tuned = round(tb, 6)
    return t


def p_accept_for(
    v: Any, cand: Candidate, responsibility_score: float | None, cfg: PAcceptConfig
) -> float:
    """p_accept кандидата под вакансию (`v` — VacancyView) при вилке вакансии."""
    return p_accept(
        salary_to=v.salary_to, salary_min=cand.salary_min, vacancy_formats=v.formats,
        candidate_formats=cand.formats or (), vacancy_skills=[q.slug for q in v.skills],
        primary_stack=cand.primary_stack or (), responsibility_score=responsibility_score,
        active=candidates.effective_status(cand) == "active", cfg=cfg,
    )  # fmt: skip


async def _rerank(
    session: AsyncSession,
    rows: list[Row],
    company_id: uuid.UUID,
    cfg: RerankConfig,
    sort: Sort,
    order: Any,
) -> None:
    """Множители (нагрузка офферами, показы без действий, готовность) и MMR по топ-K, на месте."""
    ids = [r.cand.user_id for r in rows]
    unanswered = await offers.open_counts(session, ids)
    shown = await recs.shown_without_action(session, company_id, ids)
    now = datetime.now(UTC)
    for r in rows:
        age = (
            now
            - (
                r.cand.updated_at
                if r.cand.updated_at.tzinfo
                else r.cand.updated_at.replace(tzinfo=UTC)
            )
        ).total_seconds() / 86400
        r.mult = multiplier(
            unanswered=unanswered.get(r.cand.user_id, 0), shown=shown.get(r.cand.user_id, 0),
            active=candidates.effective_status(r.cand) == "active", updated_days=age, cfg=cfg,
        )  # fmt: skip
    rows.sort(key=order)
    rows[:] = mmr(rows, lambda r: -order(r)[0], lambda r: r.cand.embedding, cfg)


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
    responsibility_score: float | None = None,
    pa_cfg: PAcceptConfig | None = None,
    rr_cfg: RerankConfig | None = None,
    session_signals: tuple[list[tun.Signal], dict[str, dict[str, float]]] | None = None,
    tuning_cfg: tun.TuningConfig | None = None,
    category: CategoryRef | None = None,
    strength_cfg: StrengthConfig | None = None,
) -> dict[str, Any]:
    """Страница выдачи `{items, next_cursor, total, features, tuning}`.

    `category` — фильтр «профессия × грейд» по действующим грейдам (`category_members`).

    `items` — JSON-словари `CandidateCard`; `features` — признаки показанных (по `pseudo_id`)
    для снимка в `impressions`; `tuning` — состояние подстройки сессии (`session_signals`).
    """
    limit = max(1, min(limit, MAX_LIMIT))
    if sort == "mutual" and vacancy_id is None:
        sort = "match"  # H считается под вакансию; без неё — обычное соответствие
    pa_cfg = pa_cfg or PAcceptConfig.load()
    rr_cfg = rr_cfg or RerankConfig.load()
    st_cfg = strength_cfg or StrengthConfig.load()
    after = decode_cursor(cursor, sort) if cursor else None
    key = cache_key(
        await candidates.catalog_version(session) + await visibility_version(session),
        {"company": str(company_id), "f": filters.model_dump(mode="json"), "sort": sort,
         "cat": category.model_dump(mode="json") if category else None,
         "vacancy": [str(vacancy_id), vacancy_version], "limit": limit,
         "rs": responsibility_score},
        cursor,
    )  # fmt: skip
    tcfg = tuning_cfg or tun.TuningConfig.load()
    tuned_session = (
        session_signals is not None
        and tun.count_signals(session_signals[0], tcfg) >= tcfg.min_signals
    )
    if redis is not None and not tuned_session:  # подстроенная выдача не кешируется
        try:
            if (hit := await redis.get(key)) is not None:
                return json.loads(hit)
        except Exception:  # noqa: BLE001 — кеш не должен ронять поиск
            pass

    day = today or datetime.now(UTC).date()
    f = filters
    pool = await only_visible(session, await candidates.search_pool(
        session, company_id=company_id, roles=[str(r) for r in f.roles] if f.roles else None,
        grades=grades_between(f.grade_min, f.grade_max), salary_max=f.salary_max,
        formats=[str(x) for x in f.formats] if f.formats else None,
        employment_types=[str(x) for x in f.employment_types] if f.employment_types else None,
        cities=f.cities, relocation_ok=f.relocation_ok, active_only=bool(f.active_only),
    ))  # fmt: skip
    if category is not None:
        members = set(
            await assessment.category_members(session, category.profession, category.grade)
        )
        pool = [c for c in pool if c.user_id in members]
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

    query_vec = None
    if vacancy_id is not None and rows:
        loaded = await load_vacancy(session, vacancy_id)
        if loaded is not None:
            v, adj = loaded
            query_vec = v.embedding
            views = await build_views(session, [r.cand for r in rows], v, adj, trust, day)
            for r, view in zip(rows, views, strict=True):
                r.result = score_candidate(v, view, adj, cfg)
                if r.result is not None:
                    r.p_accept = p_accept_for(v, r.cand, responsibility_score, pa_cfg)
    if category is not None:  # rank участвует в порядке — сила нужна всем
        await _attach_strength(session, rows, category, nice_ids, must_floor, day, st_cfg)
    for r in rows:
        if vacancy_id is None or r.result is not None:  # не прошедших фильтры не подстраиваем
            r.x = features_of(r)
    t = (
        apply_tuning(rows, session_signals[0], session_signals[1], query_vec, tcfg)
        if session_signals is not None
        else None
    )

    def sortkey(r: Row) -> float:
        k = r.key(sort)
        if sort in ("match", "mutual") and vacancy_id is not None and r.result is None:
            k -= 10  # не прошёл жёсткие фильтры вакансии — после подходящих
        return round(k, 6)

    def order(r: Row) -> tuple[float, str]:
        return (-sortkey(r), r.cand.pseudo_id)

    rows.sort(key=order)
    if sort in ("match", "mutual") and rows:
        await _rerank(session, rows, company_id, rr_cfg, sort, order)
    total = len(rows)
    if after is not None:
        akey, apid = after
        pos = next((i for i, r in enumerate(rows) if r.cand.pseudo_id == apid), None)
        if pos is not None:  # курсор — по месту последнего показанного в итоговом порядке
            rows = rows[pos + 1 :]
        else:
            rows = [r for r in rows if order(r) > (-akey, apid)]
    page = rows[:limit]
    next_cursor = (
        encode_cursor(sort, sortkey(page[-1]), page[-1].cand.pseudo_id)
        if len(rows) > limit
        else None
    )

    if category is None:  # без категории сила только в карточках страницы
        await _attach_strength(session, page, None, nice_ids, must_floor, day, st_cfg)
    page_ids = [r.cand.user_id for r in page]
    sids = list({s.skill_id for r in page for s in r.skills})
    slug_of = await taxonomy.skill_slugs(session, sids)
    name_of = await taxonomy.skill_names(session, sids)
    names = {sid: (slug_of[sid], name_of.get(sid, slug_of[sid])) for sid in slug_of}
    highlights = await _fsp_highlights(session, page_ids, trust, day)
    cats = await categories_of(session, page_ids)
    items = [
        _card(
            r.cand,
            r.skills,
            names,
            highlights.get(r.cand.user_id, []),
            r.result,
            None if r.p_accept is None else hint(r.p_accept, pa_cfg),
            cats.get(r.cand.user_id, []),
            _strength_view(r),
        ).model_dump(mode="json")
        for r in page
    ]
    out: dict[str, Any] = {
        "items": items,
        "next_cursor": next_cursor,
        "total": total,
        "features": {r.cand.pseudo_id: r.x for r in page if r.x is not None},
    }
    if t is not None:
        out["tuning"] = {
            "active": t.active, "signals": t.signals,
            "chips": tun.chips(t.weights, tcfg) if t.active else [], "hints": t.hints,
        }  # fmt: skip
    if redis is not None and not tuned_session:
        try:
            await redis.set(key, json.dumps(out, ensure_ascii=False), ex=CACHE_TTL)
        except Exception:  # noqa: BLE001
            pass
    return out
