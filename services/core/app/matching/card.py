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
from app.graph.grade import PRELIMINARY_BELOW
from app.graph.team_signals import strength_label
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

GRADE_SIGNAL_LABELS = {
    "experience": "Стаж",
    "fsp_achievement": "Достижение на соревнованиях ФСП",
    "fsp_rank": "Спортивный разряд ФСП",
    "tests": "Тесты навыков",
    "code_maturity": "Зрелость кода",
    "ai_interview": "ИИ-интервью",
    "leadership": "Лидерство",
    "constraint_lead_requires_leadership": "Для уровня Lead нужно подтверждённое лидерство",
    "constraint_no_commercial_cap": "Без коммерческого опыта грейд ограничен",
}
TEAM_LEVELS = {
    "regional": "региональный уровень",
    "interregional": "межрегиональный уровень",
    "national": "всероссийский уровень",
    "international": "международный уровень",
}
TEAM_SIGNALS = ("leadership", "teamwork", "results", "growth")


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
        preliminary=c.grade_confidence is None or c.grade_confidence < PRELIMINARY_BELOW,
        breakdown=[
            GradeSignal(signal=b["signal"], points=b["points"],
                        label=GRADE_SIGNAL_LABELS.get(b["signal"], b["signal"]),
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


# --- профиль владельца (`GET /candidates/me/profile`, E4-7) -------------------------------


class RoleWeight(BaseModel):
    role: str
    weight: float


class Category(BaseModel):
    primary_role: str
    roles: list[RoleWeight]
    primary_stack: list[str]


class TeamFactBrief(BaseModel):
    fact_id: str | None = None
    title: str


class TeamSignal(BaseModel):
    signal: str
    value: float
    label: str  # strong | present
    facts: list[TeamFactBrief]


class OwnerProfileParts(BaseModel):
    category: Category | None
    grade: GradeInfo
    skills: list[SkillWithTrust]
    team_signals: list[TeamSignal]


def _team_fact_title(f: dict[str, Any]) -> str:
    kind = f.get("kind")
    head = {
        "captain": "Капитан команды",
        "maintainer": "Мейнтейнер репозитория",
        "team_competition": "Командное соревнование",
        "performance": "Результат на соревновании",
        "trend": "Рост результатов",
    }.get(str(kind), "Подтверждённый факт")
    parts = [head]
    if f.get("level") in TEAM_LEVELS:
        parts.append(TEAM_LEVELS[f["level"]])
    if f.get("place") is not None:
        parts.append(f"{f['place']} место")
    if f.get("year") is not None:
        parts.append(str(f["year"]))
    return ", ".join(parts)


def _team_signals(c: Candidate) -> list[TeamSignal]:
    raw = c.team_signals or {}
    out = []
    for key in TEAM_SIGNALS:
        item = raw.get(key)
        if not isinstance(item, dict):
            continue
        label = strength_label(float(item.get("value", 0)))
        if label is None:
            continue
        out.append(
            TeamSignal(
                signal=key,
                value=float(item["value"]),
                label=label,
                facts=[
                    TeamFactBrief(fact_id=f.get("fact_id"), title=_team_fact_title(f))
                    for f in item.get("facts") or ()
                ],
            )
        )
    return out


def _category(c: Candidate) -> Category | None:
    if c.primary_role is None:
        return None
    return Category(
        primary_role=c.primary_role,
        roles=[RoleWeight(**r) for r in c.roles or ()],
        primary_stack=list(c.primary_stack or ()),
    )


class FspAchievement(BaseModel):
    fact_id: str
    title: str
    level: str
    place: int | None = None
    of: int | None = None
    year: int
    team_role: str | None = None


class FspRankBrief(BaseModel):
    discipline: str
    rank: str


class OwnerFsp(BaseModel):
    verified: bool
    achievements: list[FspAchievement]
    ranks: list[FspRankBrief]


async def owner_fsp(session: AsyncSession, c: Candidate) -> OwnerFsp | None:
    """Достижения и разряды ФСП владельца (факт с несколькими навыками схлопывается по `fact_id`)."""
    achievements: dict[str, FspAchievement] = {}
    ranks: dict[str, FspRankBrief] = {}
    verified = False
    for ev in await graph.evidence_of(session, [c.user_id], source="fsp"):
        d = ev.details or {}
        verified = verified or bool(ev.verified)
        if ev.fact_type == "fsp_rank" and d.get("rank") and d.get("discipline"):
            disc = str(d["discipline"])
            ranks[disc] = FspRankBrief(discipline=disc, rank=str(d["rank"]))
        elif ev.fact_type == "fsp_result" and isinstance(d.get("label"), str):
            achievements.setdefault(
                str(ev.fact_id),
                FspAchievement(
                    fact_id=str(ev.fact_id), title=d["label"], level=str(d.get("level") or ""),
                    place=d.get("place"), of=d.get("participants"), year=ev.observed_at.year,
                    team_role=d.get("team_role"),
                ),
            )  # fmt: skip
    if not achievements and not ranks:
        return None
    ordered = sorted(achievements.values(), key=lambda a: (-a.year, a.place or 10**9))
    return OwnerFsp(verified=verified, achievements=ordered, ranks=list(ranks.values()))


async def build_owner_parts(
    session: AsyncSession, c: Candidate, trust: TrustConfig, today: date | None = None
) -> OwnerProfileParts:
    """Категория, грейд, навыки с доверием и командные сигналы владельца (без анонимизации)."""
    day = today or datetime.now(UTC).date()
    owned = (await graph.all_skills_of(session, [c.user_id]))[c.user_id]
    briefs = await taxonomy.skill_briefs(session, [s.skill_id for s in owned])
    ev_ids = [uuid.UUID(e) for s in owned for e in (s.top_evidence or ())[:TOP_EVIDENCE]]
    evidence = {e.id: e for e in await graph.evidence_by_ids(session, ev_ids)}
    skills = []
    for s in sorted(owned, key=lambda s: (s.claimed_only, -s.confidence, str(s.skill_id))):
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
    return OwnerProfileParts(
        category=_category(c),
        grade=_grade_info(c),
        skills=skills,
        team_signals=_team_signals(c),
    )


async def skill_evidence(
    session: AsyncSession,
    c: Candidate,
    skill_ref: str,
    trust: TrustConfig,
    today: date | None = None,
) -> list[EvidenceBrief] | None:
    """Доказательства навыка владельца; `None` — навыка нет в профиле. `skill_ref` — id или slug."""
    day = today or datetime.now(UTC).date()
    try:
        sid: uuid.UUID | None = uuid.UUID(skill_ref)
    except ValueError:
        sid = (await taxonomy.resolve_slugs(session, [skill_ref])).get(skill_ref)
    if sid is None:
        return None
    owned = {s.skill_id: s for s in (await graph.all_skills_of(session, [c.user_id]))[c.user_id]}
    edge = owned.get(sid)
    if edge is None:
        return None
    rows = await graph.list_active(session, c.user_id, sid)
    if not rows and edge.derived_from is not None:  # выведено по иерархии: берём основание
        rows = await graph.list_active(session, c.user_id, edge.derived_from)
    return [_brief(e, trust, day) for e in rows]
