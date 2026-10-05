"""Пересчёт профиля кандидата (graph.md §4.4, flows.md F5).

`recompute_profile` собирает `candidate_skills` из активных доказательств в одной транзакции
вызывающего, увеличивает `profile_version` (только если агрегат изменился) и пишет
`skills.profile.updated` в outbox. Команда `core.recompute` пропускается, если
`recomputed_at >= requested_at`: пачка доказательств даёт 1–2 пересчёта без задержек.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

import structlog
from fsp_contracts import new_envelope
from fsp_contracts.enums import FspRankCode, Grade, RoleSlug
from fsp_contracts.events import (
    CategoryChange,
    GradeChange,
    ProfileDiff,
    SkillLevelChange,
    SkillsProfileUpdated,
)
from fsp_platform.outbox import add_to_outbox
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.models import Candidate
from app.graph.category import SkillConf, category_for
from app.graph.embedding import (
    Embedder,
    EmbeddingError,
    SkillLine,
    build_profile_text,
    text_sha,
)
from app.graph.grade import FspResult, GradeInputs, compute_grade
from app.graph.models import CandidateSkill, Evidence
from app.graph.team_signals import FspPerformance, RepoFact, compute_team_signals
from app.graph.trust import EvidenceView, SkillTrust, TrustConfig, combine, inherit
from app.taxonomy.models import Skill
from app.taxonomy.service import SkillGraph

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class RecomputeResult:
    skipped: bool
    changed: bool = False
    profile_version: int = 0


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


_RANKS = [r.value for r in FspRankCode]  # по возрастанию: youth_3 … msic


def _rank_order(rank: str | None) -> int:
    return _RANKS.index(rank) if rank in _RANKS else -1


def _num(v: object) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def grade_inputs(
    cand: Candidate,
    rows: list[tuple[Evidence, Skill]],
    role_skill_ids: set[uuid.UUID] | None,
) -> GradeInputs:
    """Сигналы грейда из активных доказательств (соглашения по `details` — ml.md §5)."""
    fsp: list[FspResult] = []
    rank, rank_ev = None, None
    theta: tuple[float, str] | None = None
    tests: list[uuid.UUID] = []
    code: list[tuple[float, uuid.UUID]] = []
    interview: list[tuple[float, uuid.UUID]] = []
    has_github = has_fsp = False
    for ev, sk in sorted(rows, key=lambda r: str(r[0].id)):
        d = ev.details or {}
        if ev.source == "fsp":
            has_fsp = True
            if ev.fact_type == "fsp_rank":
                if isinstance(d.get("rank"), str) and _rank_order(d["rank"]) >= _rank_order(rank):
                    rank, rank_ev = d["rank"], ev.id  # разрядов несколько (по дисциплинам): лучший
            elif isinstance(d.get("level"), str):
                place = _num(d.get("place"))
                final = bool(d.get("final")) or d.get("stage") == "final"
                fsp.append(FspResult(d["level"], int(place) if place else None, final, ev.id))
        elif ev.source == "test" and (th := _num(d.get("theta"))) is not None:
            if role_skill_ids is None or sk.id in role_skill_ids:
                tests.append(ev.id)
                if theta is None or th > theta[0]:
                    theta = (th, sk.slug)
        elif ev.source == "github":
            has_github = True
            if (m := _num(d.get("code_maturity"))) is not None:
                code.append((m, ev.id))
        elif ev.source == "ai_interview" and (a := _num(d.get("avg_score"))) is not None:
            interview.append((a, ev.id))
    ts = cand.team_signals or {}
    lead = ts.get("leadership")
    lead_v = _num(lead.get("value") if isinstance(lead, dict) else lead) or 0.0
    return GradeInputs(
        experience_months=cand.experience_months,
        fsp_results=fsp,
        fsp_rank=rank,
        fsp_rank_evidence=rank_ev,
        test_theta=theta[0] if theta else None,
        test_evidence=tuple(tests),
        test_skill=theta[1] if theta else None,
        code_maturity=max((m for m, _ in code), default=None),
        code_evidence=tuple(i for _, i in code),
        interview_avg=max((a for a, _ in interview), default=None),
        interview_evidence=tuple(i for _, i in interview),
        leadership=lead_v,
        management_confirmed=bool(ts.get("management_confirmed")),
        has_github=has_github,
        has_fsp_link=has_fsp,
    )


def _int(v: object, default: int = 0) -> int:
    n = _num(v)
    return int(n) if n is not None else default


def team_facts(
    rows: list[tuple[Evidence, Skill]],
) -> tuple[list[FspPerformance], list[RepoFact]]:
    """Выступления ФСП и репозитории из evidence: одно событие на `fact_id` (навыков несколько)."""
    perfs: dict[uuid.UUID, FspPerformance] = {}
    repos: dict[uuid.UUID, RepoFact] = {}
    for ev, _ in sorted(rows, key=lambda r: str(r[0].id)):
        d = ev.details or {}
        if (
            ev.source == "fsp"
            and ev.verified
            and ev.fact_type != "fsp_rank"
            and isinstance(d.get("level"), str)
        ):
            if ev.fact_id in perfs:
                continue
            place, total = _num(d.get("place")), _num(d.get("participants"))
            role = d.get("team_role")
            mates = d.get("teammates")
            perfs[ev.fact_id] = FspPerformance(
                fact_id=ev.fact_id,
                observed_at=ev.observed_at,
                level=d["level"],
                place=int(place) if place else None,
                participants=int(total) if total else None,
                final=bool(d.get("final")) or d.get("stage") == "final",
                team_role=role if role in ("captain", "member") else "individual",
                team_size=_int(d.get("team_size"), 1),
                teammates=tuple(str(m) for m in mates) if isinstance(mates, list) else (),
            )
        elif ev.source == "github" and ev.fact_type == "code_repo" and ev.fact_id not in repos:
            repos[ev.fact_id] = RepoFact(
                ev.fact_id,
                maintainer=bool(d.get("maintainer")),
                external_authors_merged=_int(d.get("external_authors_merged")),
                active_authors=_int(d.get("active_authors"), 1),
            )
    return list(perfs.values()), list(repos.values())


async def _refresh_embedding(
    cand: Candidate, skills: list[SkillLine], embedder: Embedder | None
) -> None:
    """`profile_text` из графа; вектор пересчитывается, только если sha текста изменился.

    Сбой ml-api не валит пересчёт: текст сохраняется, вектор остаётся прежним, sha не
    обновляется, поэтому следующий пересчёт повторит попытку.
    """
    text = build_profile_text(
        primary_role=cand.primary_role,
        roles=[(r["role"], r["weight"]) for r in cand.roles or []],
        grade=cand.grade,
        experience_months=cand.experience_months,
        skills=skills,
    )
    cand.profile_text = text or None
    if not text:
        cand.embedding = cand.embedding_model = cand.profile_text_sha = None
        return
    sha = text_sha(text)
    if embedder is None or (sha == cand.profile_text_sha and cand.embedding is not None):
        return
    try:
        emb = await embedder.embed_passage(text)
    except EmbeddingError as exc:
        log.warning("embedding_failed", candidate_id=str(cand.user_id), error=str(exc))
        return
    cand.embedding, cand.embedding_model, cand.profile_text_sha = emb.vector, emb.model, sha


async def recompute_profile(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    requested_at: datetime | None,
    cfg: TrustConfig,
    graph: SkillGraph | None = None,
    *,
    now: datetime | None = None,
    embedder: Embedder | None = None,
) -> RecomputeResult:
    now = _utc(now or datetime.now(UTC))
    cand = await session.get(Candidate, candidate_id, with_for_update=True)
    if cand is None or cand.deleted_at is not None:
        return RecomputeResult(skipped=True)
    if (
        requested_at is not None
        and cand.recomputed_at is not None
        and _utc(cand.recomputed_at) >= _utc(requested_at)
    ):
        return RecomputeResult(skipped=True, profile_version=cand.profile_version)

    rows = (
        await session.execute(
            select(Evidence, Skill)
            .join(Skill, Skill.id == Evidence.skill_id)
            .where(Evidence.candidate_id == candidate_id, Evidence.is_active)
        )
    ).all()
    by_skill: dict[uuid.UUID, list[EvidenceView]] = {}
    skills: dict[uuid.UUID, Skill] = {}
    for ev, sk in rows:
        skills[sk.id] = sk
        by_skill.setdefault(sk.id, []).append(
            EvidenceView(ev.id, ev.source, ev.strength, ev.observed_at, ev.verified)
        )
    today: date = now.date()
    computed = {}
    for sid, views in by_skill.items():
        trust = combine(views, today, cfg, provisional=skills[sid].status == "provisional")
        if trust is not None:
            computed[sid] = trust

    # (доверие, выведено из навыка | None); выведенное заменяет прямое, только если выше его
    entries: dict[uuid.UUID, tuple[SkillTrust, uuid.UUID | None]] = {
        sid: (t, None) for sid, t in computed.items()
    }
    slugs = {sid: sk.slug for sid, sk in skills.items()}
    if graph is not None:
        slugs.update(graph.slugs)
        entries.update(inherit(computed, graph.parents_of, cfg))

    existing = {
        r.skill_id: r
        for r in await session.scalars(
            select(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id)
        )
    }
    up, new = [], []
    changed = False
    for sid, (t, src) in entries.items():
        slug = slugs[sid]
        top = [str(i) for i in t.top_evidence]
        row = existing.get(sid)
        if row is None:
            session.add(
                CandidateSkill(
                    candidate_id=candidate_id,
                    skill_id=sid,
                    confidence=t.confidence,
                    level=t.level,
                    sources=t.sources,
                    top_evidence=top,
                    claimed_only=t.claimed_only,
                    derived=src is not None,
                    derived_from=src,
                    updated_at=now,
                )
            )
            new.append(SkillLevelChange(slug=slug, to=t.level))
            changed = True
            continue
        if (
            row.confidence,
            row.level,
            list(row.sources),
            list(row.top_evidence),
            row.claimed_only,
            row.derived,
            row.derived_from,
        ) == (
            t.confidence,
            t.level,
            t.sources,
            top,
            t.claimed_only,
            src is not None,
            src,
        ):
            continue
        if t.level > row.level:
            up.append(SkillLevelChange(slug=slug, from_=row.level, to=t.level))
        row.confidence, row.level, row.sources = t.confidence, t.level, t.sources
        row.top_evidence, row.claimed_only, row.updated_at = top, t.claimed_only, now
        row.derived, row.derived_from = src is not None, src
        changed = True
    for sid, row in existing.items():
        if sid not in entries:
            await session.delete(row)
            changed = True

    # E22-4 (ADR-018): роли и грейд ниже — сигналы силы профиля, не категория; её задаёт assessment
    category_diff = None
    if graph is not None:
        cat = category_for(
            {
                slugs[sid]: SkillConf(t.confidence, t.level, tuple(t.sources))
                for sid, (t, _) in entries.items()
            },
            graph,
            cfg.category,
        )
        roles_json, stack = cat.roles_json(), cat.primary_stack
        if (cand.primary_role, cand.roles or [], cand.primary_stack or []) != (
            cat.primary_role,
            roles_json,
            stack,
        ):
            if cat.primary_role is not None and cat.primary_role != cand.primary_role:
                category_diff = CategoryChange(
                    from_=RoleSlug(cand.primary_role) if cand.primary_role else None,
                    to=RoleSlug(cat.primary_role),
                )
            cand.primary_role, cand.roles, cand.primary_stack = cat.primary_role, roles_json, stack
            changed = True

    # командные сигналы L/T/R/G — только из фактов; management_confirmed хранится рядом
    perfs, repos = team_facts(rows)
    signals = compute_team_signals(perfs, repos, today, cfg.team).as_json(
        management_confirmed=bool((cand.team_signals or {}).get("management_confirmed"))
    )
    if (cand.team_signals or None) != signals:
        cand.team_signals = signals
        changed = True

    grade_diff = None
    role_ids = graph.roles.get(cand.primary_role or "") if graph is not None else None
    gres = compute_grade(
        grade_inputs(cand, rows, set(role_ids) if role_ids else None),
        cfg.grade,
        role_skill=(cand.primary_stack or [None])[0],
    )
    new_grade = (
        gres.grade,
        gres.score,
        gres.confidence,
        gres.breakdown_json(),
        gres.next_json(),
    )
    if (
        cand.grade,
        cand.grade_score,
        cand.grade_confidence,
        cand.grade_breakdown,
        cand.grade_next,
    ) != new_grade:
        if gres.grade != cand.grade:
            grade_diff = GradeChange(
                from_=Grade(cand.grade) if cand.grade else None, to=Grade(gres.grade)
            )
        (
            cand.grade,
            cand.grade_score,
            cand.grade_confidence,
            cand.grade_breakdown,
            cand.grade_next,
        ) = new_grade
        changed = True

    await _refresh_embedding(
        cand,
        [
            SkillLine(slugs[sid], t.level, t.confidence, t.claimed_only)
            for sid, (t, _) in entries.items()
        ],
        embedder,
    )

    cand.recomputed_at = now
    if changed:
        cand.profile_version += 1
        event = SkillsProfileUpdated(
            candidate_id=candidate_id,
            profile_version=cand.profile_version,
            diff=ProfileDiff(
                skills_up=up, skills_new=new, grade=grade_diff, category=category_diff
            ),
        )
        await add_to_outbox(
            session, new_envelope("skills.profile.updated", "core", event), candidate_id
        )
    await session.flush()
    return RecomputeResult(skipped=False, changed=changed, profile_version=cand.profile_version)
