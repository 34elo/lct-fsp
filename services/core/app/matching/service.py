"""Подбор кандидатов под вакансию (matching.md §2–4, ml.md §6): отбор SQL → скоринг → объяснения.

Модуль не лезет в чужие модели: данные берёт через `service.py` модулей vacancies, taxonomy,
graph и candidates. Формулы — в `scoring.py`. Запись в `matches` и выдача — E7-2/E7-3.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service as candidates
from app.graph import service as graph
from app.graph.trust import EvidenceView, TrustConfig, effective_strength
from app.matching.scoring import (
    CandidateView,
    FspProof,
    HeldSkill,
    MatchConfig,
    MatchResult,
    Requirement,
    VacancyView,
    score_candidate,
)
from app.taxonomy import service as taxonomy
from app.vacancies import service as vacancies

if TYPE_CHECKING:
    from app.candidates.service import Candidate


async def load_vacancy(
    session: AsyncSession, vacancy_id: uuid.UUID, embedding: list[float] | None = None
) -> tuple[VacancyView, dict[uuid.UUID, list[tuple[uuid.UUID, float]]]] | None:
    v = await vacancies.get(session, vacancy_id)
    if v is None:
        return None
    rows = (await vacancies.skills_of(session, [v.id]))[v.id]
    ids = [vs.skill_id for vs, _ in rows]
    adj = await taxonomy.adjacency(session, ids)
    names = await taxonomy.skill_names(session, ids)
    reqs = tuple(
        Requirement(vs.skill_id, slug, names.get(vs.skill_id, slug), vs.required,
                    vs.min_level, vs.weight)
        for vs, slug in rows
    )  # fmt: skip
    view = VacancyView(
        id=v.id,
        version=v.version,
        company_id=v.company_id,
        grade_min=v.grade_min,
        grade_max=v.grade_max,
        formats=tuple(v.formats or ()),
        salary_from=v.salary_from,
        salary_to=v.salary_to,
        skills=reqs,
        important_qualities=tuple(v.important_qualities or ()),
        embedding=embedding,
    )
    return view, adj


async def select_candidates(
    session: AsyncSession,
    v: VacancyView,
    adj: dict[uuid.UUID, list[tuple[uuid.UUID, float]]],
    cfg: MatchConfig,
) -> tuple[list[Candidate], set[uuid.UUID]]:
    """Отбор (matching.md §3): A — по графу с жёсткими фильтрами, B — по смыслу (если есть вектор).

    Возвращает анкеты и множество id, найденных только по смыслу.
    """
    required = [r for r in v.skills if r.required]
    reqs = [
        graph.CoverReq(r.skill_id, via, w, cfg.target(r.min_level))
        for r in required
        for via, w in [(r.skill_id, 1.0), *adj.get(r.skill_id, ())]
    ]
    ids = await graph.covering_candidates(
        session,
        reqs,
        required_count=len(required),
        max_failed=cfg.max_failed_required,
        limit=cfg.candidate_limit,
    )
    attrs = {
        "salary_cap": v.salary_to * cfg.salary_grace,
        "formats": list(v.formats),
        "company_id": v.company_id,
    }
    found = await candidates.eligible(session, ids, **attrs)
    semantic: list[Candidate] = []
    if v.embedding:
        semantic = await candidates.nearest_by_embedding(
            session, list(v.embedding), limit=cfg.semantic_limit, **attrs
        )
    by_graph = {c.user_id for c in found}
    only = [c for c in semantic if c.user_id not in by_graph]
    return found + only, {c.user_id for c in only}


def _grade_evidence(breakdown: Iterable[dict] | None) -> tuple[str, ...]:
    out: list[str] = []
    for b in breakdown or ():
        out.extend(str(e) for e in b.get("evidence_ids") or ())
    return tuple(dict.fromkeys(out))


def _team(signals: dict | None) -> tuple[dict[str, float], dict[str, list[uuid.UUID]]]:
    values: dict[str, float] = {}
    facts: dict[str, list[uuid.UUID]] = {}
    for k, s in (signals or {}).items():
        if not isinstance(s, dict) or "value" not in s:
            continue  # например, management_confirmed
        values[k] = float(s["value"])
        facts[k] = [uuid.UUID(f["fact_id"]) for f in s.get("facts", []) if f.get("fact_id")]
    return values, facts


async def build_views(
    session: AsyncSession,
    cands: list[Candidate],
    v: VacancyView,
    adj: dict[uuid.UUID, list[tuple[uuid.UUID, float]]],
    trust: TrustConfig,
    today: date,
) -> list[CandidateView]:
    """Проекции кандидатов для скоринга: навыки, ФСП-доказательства, командные сигналы."""
    ids = [c.user_id for c in cands]
    vac_ids = [r.skill_id for r in v.skills]
    skill_ids = list(dict.fromkeys(vac_ids + [a for r in vac_ids for a, _ in adj.get(r, ())]))
    names = await taxonomy.skill_names(session, skill_ids)

    held: dict[uuid.UUID, dict[uuid.UUID, HeldSkill]] = {i: {} for i in ids}
    for cs in await graph.skills_of_candidates(session, ids, skill_ids):
        held[cs.candidate_id][cs.skill_id] = HeldSkill(
            name=names.get(cs.skill_id, str(cs.skill_id)),
            confidence=cs.confidence,
            level=cs.level,
            sources=tuple(cs.sources or ()),
            evidence_ids=tuple(str(e) for e in cs.top_evidence or ()),
            claimed_only=cs.claimed_only,
        )

    fsp: dict[uuid.UUID, dict[uuid.UUID, FspProof]] = {i: {} for i in ids}
    for ev in await graph.evidence_of(session, ids, skill_ids=vac_ids, source="fsp"):
        s = effective_strength(
            EvidenceView(ev.id, ev.source, ev.strength, ev.observed_at, ev.verified), today, trust
        )
        cur = fsp[ev.candidate_id].get(ev.skill_id)
        if s > 0 and (cur is None or s > cur.strength):
            label = (ev.details or {}).get("label")
            fsp[ev.candidate_id][ev.skill_id] = FspProof(
                str(ev.id), s, label if isinstance(label, str) else None
            )

    teams = {c.user_id: _team(c.team_signals) for c in cands}
    fact_ids = list({f for _, facts in teams.values() for fs in facts.values() for f in fs})
    by_fact: dict[tuple[uuid.UUID, uuid.UUID], list[str]] = {}
    if fact_ids:
        for ev in await graph.evidence_of(session, ids, fact_ids=fact_ids):
            by_fact.setdefault((ev.candidate_id, ev.fact_id), []).append(str(ev.id))

    views = []
    for c in cands:
        values, facts = teams[c.user_id]
        team_ev = {
            k: tuple(e for f in fs for e in by_fact.get((c.user_id, f), ()))
            for k, fs in facts.items()
        }
        views.append(
            CandidateView(
                id=c.user_id,
                profile_version=c.profile_version,
                grade=c.grade,
                formats=tuple(c.formats or ()),
                salary_min=c.salary_min,
                status=candidates.effective_status(c),
                stoplist=frozenset(str(x) for x in c.stoplist_company_ids or ()),
                deleted=c.deleted_at is not None,
                skills=held[c.user_id],
                fsp=fsp[c.user_id],
                team=values,
                team_evidence=team_ev,
                grade_evidence=_grade_evidence(c.grade_breakdown),
                embedding=c.embedding,
            )
        )
    return views


async def match_vacancy_candidates(
    session: AsyncSession,
    vacancy_id: uuid.UUID,
    cfg: MatchConfig,
    trust: TrustConfig,
    *,
    vacancy_embedding: list[float] | None = None,
    today: date | None = None,
) -> list[MatchResult]:
    """Кандидаты под вакансию со скором и объяснением, по убыванию скора."""
    loaded = await load_vacancy(session, vacancy_id, vacancy_embedding)
    if loaded is None:
        return []
    v, adj = loaded
    cands, semantic_only = await select_candidates(session, v, adj, cfg)
    views = await build_views(session, cands, v, adj, trust, today or datetime.now(UTC).date())
    out = [
        r
        for c in views
        if (r := score_candidate(v, c, adj, cfg, semantic_only=c.id in semantic_only)) is not None
    ]
    return sorted(out, key=lambda r: (-r.score, str(r.candidate_id)))
