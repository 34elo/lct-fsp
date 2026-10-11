"""Импорт ФСП в граф: события `fsp.*` → факты → `evidence`.

Порядок доставки событий не гарантирован, поэтому факты сначала сохраняются в `fsp_*`, а
доказательства пересобираются из сохранённого (`rebuild_evidence`): результат, пришедший раньше
календаря, получит доказательства, когда придёт `fsp.competitions.updated`. Всё идемпотентно:
повтор ничего не меняет и не порождает `evidence.changed`.

Формат `details` — под грейд и командные сигналы (`recompute.grade_inputs`, `team_signals`):
`level, place, participants, stage, final, team_role, team_size, teammates` (+ `competition_id`,
`track`, `label`). Разряд — `fact_type=fsp_rank` с `{rank, discipline}`, сила 0: это сигнал
грейда, а не доказательство навыка.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime

import structlog
from fsp_contracts import new_envelope
from fsp_contracts.commands import FspSync
from fsp_contracts.events import FspCompetitionsUpdated, FspLinked, FspResultsImported
from fsp_platform.outbox import add_to_outbox
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.models import Candidate
from app.graph import service
from app.graph.fsp_models import (
    FspCompetitionRow,
    FspParticipant,
    FspRankRow,
    FspResultRow,
    FspTeamMember,
    FspTeamRow,
)
from app.graph.fsp_strength import FspStrengthConfig, result_strength
from app.graph.service import EvidenceIn
from app.taxonomy.service import DisciplineRule, discipline_rules

log = structlog.get_logger()

NS = uuid.UUID("c2a4d5e0-7b1f-4a52-9d57-3f1b6a0e9c11")
UNKNOWN_RANK_DATE = date(2000, 1, 1)  # дата присвоения разряда неизвестна (сила 0, затухания нет)


def result_id(participant_id: str, competition_id: str, stage: str) -> uuid.UUID:
    return uuid.uuid5(NS, f"result|{participant_id}|{competition_id}|{stage}")


def rank_fact_id(candidate_id: uuid.UUID, discipline: str) -> uuid.UUID:
    return uuid.uuid5(NS, f"rank|{candidate_id}|{discipline}")


def mate_ref(participant_id: str) -> str:
    """Непрозрачная ссылка на напарника: совпадает у одного человека в разных командах."""
    return hashlib.sha256(f"mate|{participant_id}".encode()).hexdigest()[:16]


async def _candidate_exists(session: AsyncSession, candidate_id: uuid.UUID) -> bool:
    cand = await session.get(Candidate, candidate_id)
    return cand is not None and cand.deleted_at is None


# ----------------------------------------------------------------------------- fsp.linked
async def on_linked(session: AsyncSession, evt: FspLinked, cfg: FspStrengthConfig) -> None:
    if not await _candidate_exists(session, evt.candidate_id):
        log.warning("fsp_linked_unknown_candidate", candidate_id=str(evt.candidate_id))
        return
    row = await session.get(FspParticipant, evt.candidate_id)
    clash = await session.scalar(
        select(FspParticipant).where(
            FspParticipant.participant_id == evt.participant_id,
            FspParticipant.candidate_id != evt.candidate_id,
        )
    )
    if clash is not None:  # уникальность гарантирует fsp-connector; тут только страховка
        log.warning("fsp_linked_participant_taken", candidate_id=str(evt.candidate_id))
        return
    is_new = row is None
    if row is None:
        session.add(
            FspParticipant(
                candidate_id=evt.candidate_id,
                participant_id=evt.participant_id,
                verified=evt.verified,
            )
        )
        await session.flush()
    elif row.participant_id != evt.participant_id or row.verified != evt.verified:
        row.participant_id, row.verified = evt.participant_id, evt.verified
        await session.flush()
    else:
        return  # повтор того же состояния
    for m in await session.scalars(
        select(FspTeamMember).where(FspTeamMember.participant_id == evt.participant_id)
    ):
        m.candidate_id = evt.candidate_id
    if is_new:
        cmd = FspSync(candidate_id=evt.candidate_id, reason="linked")
        await add_to_outbox(
            session, new_envelope("fsp.sync", "core", cmd), aggregate_id=evt.candidate_id
        )
    else:  # verified поменялся: пометить уже собранные доказательства
        await rebuild_evidence(session, evt.candidate_id, cfg)


# ----------------------------------------------------------------- fsp.competitions.updated
async def on_competitions(
    session: AsyncSession, evt: FspCompetitionsUpdated, cfg: FspStrengthConfig
) -> None:
    now = datetime.now(UTC)
    changed: set[str] = set()
    for c in evt.competitions:
        row = await session.get(FspCompetitionRow, c.id)
        vals = {
            "title": c.title,
            "discipline": str(c.discipline),
            "level": str(c.level),
            "format": c.format,
            "region": c.region,
            "start_date": c.start_date,
            "end_date": c.end_date,
            "status": c.status,
            "tracks": list(c.tracks),
            "registration_url": c.registration_url,
        }
        if row is None:
            session.add(
                FspCompetitionRow(id=c.id, synced_at=now, raw=c.model_dump(mode="json"), **vals)
            )
            changed.add(c.id)
            continue
        if any(getattr(row, k) != v for k, v in vals.items()):
            for k, v in vals.items():
                setattr(row, k, v)
            row.raw = c.model_dump(mode="json")
            changed.add(c.id)
        row.synced_at = now
    await session.flush()
    if not changed:
        return
    cands = await session.scalars(
        select(FspResultRow.candidate_id)
        .where(FspResultRow.competition_id.in_(changed), FspResultRow.is_active)
        .distinct()
    )
    for cid in sorted(cands, key=str):
        await rebuild_evidence(session, cid, cfg)


# ------------------------------------------------------------------ fsp.results.imported
async def on_results(
    session: AsyncSession, evt: FspResultsImported, cfg: FspStrengthConfig
) -> None:
    cid = evt.candidate_id
    if not await _candidate_exists(session, cid):
        log.warning("fsp_results_unknown_candidate", candidate_id=str(cid))
        return
    pid = evt.participant_id

    # команды и составы (candidate_id — если участник уже на платформе)
    member_ids = {m.participant_id for t in evt.teams for m in t.members}
    known = {
        p.participant_id: p.candidate_id
        for p in await session.scalars(
            select(FspParticipant).where(FspParticipant.participant_id.in_(member_ids))
        )
    }
    for t in evt.teams:
        team = await session.get(FspTeamRow, t.id)
        if team is None:
            session.add(FspTeamRow(id=t.id, name=t.name, competition_id=t.competition_id))
        else:
            team.name, team.competition_id = t.name, t.competition_id
        await session.flush()
        await session.execute(delete(FspTeamMember).where(FspTeamMember.team_id == t.id))
        for m in t.members:
            session.add(
                FspTeamMember(
                    team_id=t.id,
                    participant_id=m.participant_id,
                    candidate_id=known.get(m.participant_id),
                    role=m.role,
                )
            )
    await session.flush()

    # результаты: upsert по (participant_id, competition_id, stage)
    unique = {result_id(pid, r.competition_id, r.stage): r for r in evt.results}  # дубли: последний
    seen = set(unique)
    for rid, r in unique.items():
        vals = {
            "candidate_id": cid,
            "discipline": str(r.discipline),
            "team_id": r.team_id,
            "team_role": r.team_role,
            "place": r.place,
            "participants_total": r.participants_total,
            "score": r.score,
            "track": r.track,
            "date": r.date,
            "raw": r.model_dump(mode="json"),
            "is_active": True,
        }
        row = await session.get(FspResultRow, rid)
        if row is None:
            session.add(
                FspResultRow(
                    id=rid,
                    participant_id=pid,
                    competition_id=r.competition_id,
                    stage=r.stage,
                    **vals,
                )
            )
        else:
            for k, v in vals.items():
                setattr(row, k, v)
    if evt.new:  # полная выгрузка: исчезнувшее из источника гасим, но не удаляем (аудит)
        for row in await session.scalars(
            select(FspResultRow).where(FspResultRow.candidate_id == cid, FspResultRow.is_active)
        ):
            if row.id not in seen:
                row.is_active = False
                await service.deactivate(session, cid, fact_id=row.id)

    # разряды
    have = {
        r.discipline: r
        for r in await session.scalars(select(FspRankRow).where(FspRankRow.candidate_id == cid))
    }
    for rk in evt.ranks:
        cur = have.pop(str(rk.discipline), None)
        if cur is None:
            session.add(
                FspRankRow(
                    candidate_id=cid,
                    discipline=str(rk.discipline),
                    rank=str(rk.rank),
                    assigned_at=rk.assigned_at,
                )
            )
        else:
            cur.rank, cur.assigned_at = str(rk.rank), rk.assigned_at
    if evt.new:
        for disc, cur in have.items():
            await session.delete(cur)
            await service.deactivate(session, cid, fact_id=rank_fact_id(cid, disc))
    await session.flush()
    await rebuild_evidence(session, cid, cfg)


# --------------------------------------------------------------------------- доказательства
def _label(title: str | None, r: FspResultRow, team_role: str | None) -> str:
    parts = [title or f"Соревнование {r.competition_id}"]
    if r.stage == "final":
        parts.append("финал")
    if r.place is not None:
        parts.append(
            f"{r.place} место из {r.participants_total}"
            if r.participants_total
            else f"{r.place} место"
        )
    if team_role == "captain":
        parts.append("капитан")
    return ", ".join(parts)


def _weights(rules: list[DisciplineRule], track: str | None) -> dict[uuid.UUID, float]:
    """Вес навыка по правилам дисциплины и трека (максимум); софт-навыки без точек доверия."""
    w: dict[uuid.UUID, float] = {}
    for rule in rules:
        if rule.kind == "soft" or (rule.track is not None and rule.track != track):
            continue
        w[rule.skill_id] = max(w.get(rule.skill_id, 0.0), rule.weight)
    return w


async def rebuild_evidence(
    session: AsyncSession, candidate_id: uuid.UUID, cfg: FspStrengthConfig
) -> None:
    part = await session.get(FspParticipant, candidate_id)
    verified = bool(part and part.verified)
    rules = await discipline_rules(session)

    results = list(
        await session.scalars(
            select(FspResultRow)
            .where(FspResultRow.candidate_id == candidate_id, FspResultRow.is_active)
            .order_by(FspResultRow.id)
        )
    )
    comps = {
        c.id: c
        for c in await session.scalars(
            select(FspCompetitionRow).where(
                FspCompetitionRow.id.in_({r.competition_id for r in results})
            )
        )
    }
    team_ids = {r.team_id for r in results if r.team_id}
    members: dict[str, list[str]] = {}
    if team_ids:
        for m in await session.scalars(
            select(FspTeamMember).where(FspTeamMember.team_id.in_(team_ids))
        ):
            members.setdefault(m.team_id, []).append(m.participant_id)

    items: list[EvidenceIn] = []
    for r in results:
        comp = comps.get(r.competition_id)
        if comp is None or comp.level is None or r.date is None:
            continue  # нет уровня соревнования: дождёмся календаря
        weights = _weights(rules.get(r.discipline or comp.discipline or "", []), r.track)
        mates = sorted(
            mate_ref(p) for p in members.get(r.team_id or "", []) if p != r.participant_id
        )
        details = {
            "competition_id": r.competition_id,
            "level": comp.level,
            "place": r.place,
            "participants": r.participants_total,
            "stage": r.stage,
            "final": r.stage == "final",
            "team_role": r.team_role,
            "team_size": len(members.get(r.team_id or "", [])) or 1,
            "teammates": mates,
            "track": r.track,
            "discipline": r.discipline or comp.discipline,
            "label": _label(comp.title, r, r.team_role),
        }
        for skill_id, w in weights.items():
            s = result_strength(
                w,
                level=comp.level,
                place=r.place,
                total=r.participants_total,
                stage=r.stage,
                cfg=cfg,
            )
            if s > 0:
                items.append(
                    EvidenceIn(
                        skill_id=skill_id,
                        source="fsp",
                        strength=s,
                        observed_at=r.date,
                        fact_type="fsp_result",
                        fact_id=r.id,
                        details=details,
                        verified=verified,
                    )
                )

    for rk in await session.scalars(
        select(FspRankRow).where(FspRankRow.candidate_id == candidate_id)
    ):
        skill = _rank_skill(rules.get(rk.discipline, []))
        if skill is None:
            log.warning("fsp_rank_no_skill", discipline=rk.discipline)
            continue
        items.append(
            EvidenceIn(
                skill_id=skill,
                source="fsp",
                strength=0.0,
                observed_at=rk.assigned_at or UNKNOWN_RANK_DATE,
                fact_type="fsp_rank",
                fact_id=rank_fact_id(candidate_id, rk.discipline),
                details={"rank": rk.rank, "discipline": rk.discipline},
                verified=verified,
            )
        )
    await service.upsert_evidence(session, candidate_id, items)


def _rank_skill(rules: list[DisciplineRule]) -> uuid.UUID | None:
    """Навык, к которому привязан разряд дисциплины (самый весомый по правилам)."""
    best = [r for r in rules if r.kind != "soft" and r.track is None]
    if not best:
        return None
    return max(best, key=lambda r: (r.weight, r.slug)).skill_id
