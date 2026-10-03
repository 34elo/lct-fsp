"""`CandidateCardFull` (api.md §3): расширенная анонимная карточка для работодателя.

Нет: user_id, ФИО, контактов, ссылок на репозитории и анализ кода (пока нет модуля),
образования. Компании в опыте — только при `visibility.companies`. Просмотр — в `profile_views`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service as candidates
from app.candidates.models import Candidate
from app.graph import service as graph
from app.graph.trust import EvidenceView, TrustConfig, effective_strength
from app.matching import search
from app.matching.scoring import MatchConfig
from app.matching.service import build_views, load_vacancy
from app.offers import service as offers
from app.resumes import service as resumes
from app.taxonomy import service as taxonomy

SOURCE_TITLES = {
    "self": "Заявлено кандидатом",
    "resume": "Указано в резюме",
    "github": "Анализ публичного кода",
    "test": "Тест навыка",
    "ai_interview": "ИИ-интервью",
    "fsp": "Результат ФСП",
    "codeforces": "Рейтинг Codeforces",
}
TOP_EVIDENCE = 3


class SkillInfo(BaseModel):
    slug: str
    name: str
    group: str


class EvidenceBrief(BaseModel):
    id: str
    source: str
    strength: float
    observed_at: date
    title: str
    verified: bool


class SkillWithTrust(BaseModel):
    skill: SkillInfo
    confidence: float
    level: int
    sources: list[str]
    claimed_only: bool
    status: str
    derived_from: str | None = None
    top_evidence: list[EvidenceBrief]


class GradeSignal(BaseModel):
    signal: str
    label: str
    points: float
    evidence_ids: list[str]


class NextGrade(BaseModel):
    grade: str
    points_needed: float
    hints: list[str]


class GradeInfo(BaseModel):
    grade: str | None
    score: float | None
    confidence: float | None
    preliminary: bool
    breakdown: list[GradeSignal]
    next_grade: NextGrade | None = None


class ExperienceBrief(BaseModel):
    title: str | None
    company: str | None = None  # только при visibility.companies
    months: int
    skills: list[str]


class CandidateCardFull(search.CandidateCard):
    skills: list[SkillWithTrust]
    grade_info: GradeInfo
    experience: list[ExperienceBrief]
    offers_from_you: list[dict[str, Any]]


def _months(start: str | None, end: str | None, today: date) -> int:
    def parse(v: str | None) -> tuple[int, int] | None:
        try:
            y, m = (v or "").split("-")
            return int(y), int(m)
        except ValueError:
            return None

    s = parse(start)
    if s is None:
        return 0
    e = parse(end) or (today.year, today.month)
    return max(0, (e[0] - s[0]) * 12 + e[1] - s[1])


def _grade_info(c: Candidate) -> GradeInfo:
    nxt = c.grade_next
    return GradeInfo(
        grade=c.grade,
        score=c.grade_score,
        confidence=c.grade_confidence,
        preliminary=c.grade_confidence is None or c.grade_confidence < 0.5,
        breakdown=[
            GradeSignal(signal=b["signal"], label=b["signal"], points=b["points"],
                        evidence_ids=list(b.get("evidence_ids") or []))
            for b in c.grade_breakdown or ()
        ],
        next_grade=NextGrade(
            grade=nxt["grade"], points_needed=nxt["points_needed"],
            hints=[h["text"] for h in nxt.get("hints") or ()],
        ) if nxt else None,
    )  # fmt: skip


def _brief(ev: Any, trust: TrustConfig, today: date) -> EvidenceBrief:
    d = ev.details or {}
    title = d.get("label") if ev.source == "fsp" and isinstance(d.get("label"), str) else None
    s = effective_strength(
        EvidenceView(ev.id, ev.source, ev.strength, ev.observed_at, ev.verified), today, trust
    )
    return EvidenceBrief(
        id=str(ev.id), source=ev.source, strength=round(s, 4), observed_at=ev.observed_at,
        title=title or SOURCE_TITLES.get(ev.source, ev.source), verified=ev.verified,
    )  # fmt: skip


async def get_visible(
    session: AsyncSession, pseudo_id: str, company_id: uuid.UUID
) -> Candidate | None:
    """Карточка доступна, если анкета видна в поиске (не dnd, есть роль, нет стоп-листа)."""
    c = await candidates.get_by_pseudo_id(session, pseudo_id)
    if (
        c is None
        or c.search_status == "dnd"
        or c.primary_role is None
        or str(company_id) in (c.stoplist_company_ids or ())
    ):
        return None
    return c


async def build_card(
    session: AsyncSession,
    c: Candidate,
    *,
    vacancy_id: uuid.UUID | None,
    cfg: MatchConfig,
    trust: TrustConfig,
    company_id: uuid.UUID | None = None,
    today: date | None = None,
) -> CandidateCardFull:
    day = today or datetime.now(UTC).date()
    owned = (await graph.all_skills_of(session, [c.user_id]))[c.user_id]
    sids = [s.skill_id for s in owned]
    briefs = await taxonomy.skill_briefs(session, sids)
    names = {sid: (b[0], b[1]) for sid, b in briefs.items()}
    highlights = (await search._fsp_highlights(session, [c.user_id], trust, day)).get(c.user_id, [])

    result = None
    if vacancy_id is not None:
        loaded = await load_vacancy(session, vacancy_id)
        if loaded is not None:
            v, adj = loaded
            (view,) = await build_views(session, [c], v, adj, trust, day)
            result = search.score_candidate(v, view, adj, cfg)
    base = search._card(c, owned, names, highlights, result)

    ev_ids = [uuid.UUID(e) for s in owned for e in (s.top_evidence or ())[:TOP_EVIDENCE]]
    evidence = {e.id: e for e in await graph.evidence_by_ids(session, ev_ids)}
    ordered = sorted(owned, key=lambda s: (s.claimed_only, -s.confidence, str(s.skill_id)))
    skills = []
    for s in ordered:
        if s.skill_id not in briefs:
            continue
        slug, name, group, status = briefs[s.skill_id]
        skills.append(
            SkillWithTrust(
                skill=SkillInfo(slug=slug, name=name, group=group),
                confidence=s.confidence, level=s.level, sources=list(s.sources or ()),
                claimed_only=s.claimed_only,
                status="provisional" if status == "provisional" else "active",
                derived_from=briefs[s.derived_from][0] if s.derived_from in briefs else None,
                top_evidence=[
                    _brief(evidence[uuid.UUID(e)], trust, day)
                    for e in (s.top_evidence or ())[:TOP_EVIDENCE]
                    if uuid.UUID(e) in evidence
                ],
            )
        )  # fmt: skip

    show_companies = bool((c.visibility or {}).get("companies"))
    experience = [
        ExperienceBrief(
            title=e["title"], company=e["company"] if show_companies else None,
            months=_months(e["start"], e["end"], day), skills=e["skills"],
        )
        for e in await resumes.experience_for_profile(session, c.user_id)
    ]  # fmt: skip
    return CandidateCardFull(
        **base.model_dump(),
        skills=skills,
        grade_info=_grade_info(c),
        experience=experience,
        offers_from_you=(
            await offers.briefs_for(session, company_id, c.user_id) if company_id else []
        ),
    )
