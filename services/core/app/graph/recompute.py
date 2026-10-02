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

from fsp_contracts import new_envelope
from fsp_contracts.events import ProfileDiff, SkillLevelChange, SkillsProfileUpdated
from fsp_platform.outbox import add_to_outbox
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.models import Candidate
from app.graph.models import CandidateSkill, Evidence
from app.graph.trust import EvidenceView, TrustConfig, combine
from app.taxonomy.models import Skill


@dataclass(frozen=True, slots=True)
class RecomputeResult:
    skipped: bool
    changed: bool = False
    profile_version: int = 0


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


async def recompute_profile(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    requested_at: datetime | None,
    cfg: TrustConfig,
    *,
    now: datetime | None = None,
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

    existing = {
        r.skill_id: r
        for r in await session.scalars(
            select(CandidateSkill).where(
                CandidateSkill.candidate_id == candidate_id, CandidateSkill.derived.is_(False)
            )
        )
    }
    up, new = [], []
    changed = False
    for sid, t in computed.items():
        slug = skills[sid].slug
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
        ) == (
            t.confidence,
            t.level,
            t.sources,
            top,
            t.claimed_only,
        ):
            continue
        if t.level > row.level:
            up.append(SkillLevelChange(slug=slug, from_=row.level, to=t.level))
        row.confidence, row.level, row.sources = t.confidence, t.level, t.sources
        row.top_evidence, row.claimed_only, row.updated_at = top, t.claimed_only, now
        changed = True
    for sid, row in existing.items():
        if sid not in computed:
            await session.delete(row)
            changed = True

    cand.recomputed_at = now
    if changed:
        cand.profile_version += 1
        event = SkillsProfileUpdated(
            candidate_id=candidate_id,
            profile_version=cand.profile_version,
            diff=ProfileDiff(skills_up=up, skills_new=new),
        )
        await add_to_outbox(
            session, new_envelope("skills.profile.updated", "core", event), candidate_id
        )
    await session.flush()
    return RecomputeResult(skipped=False, changed=changed, profile_version=cand.profile_version)
