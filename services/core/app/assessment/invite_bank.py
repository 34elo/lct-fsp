"""Банк заданий для приглашения: `service.invite_task_*`.

Задание к приглашению — своё задание конструктора (только «Готово»: без допуска админа)
или семейство общего банка (`pilot`/`active`). Результат — доказательство `task` в профиль
(`fact_type=invite_task`, `fact_id=offer_id`, идемпотентно); в θ и грейд не идёт. Функции не делают
`commit`.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fsp_platform.app import ProblemError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.attempts import build_item, family_of, item_seed
from app.assessment.families.base import Kind
from app.assessment.models import FamilyRow
from app.graph import service as graph

BANK_STATUSES = ("pilot", "active")
EVIDENCE_SOURCE = "task"
EVIDENCE_MAX = 0.5  # задание работодателя — одно из независимых доказательств, не больше половины
FACT_TYPE = "invite_task"


@dataclass(frozen=True)
class InviteTaskInfo:
    title: str
    kind: str
    minutes: int


def is_ready(row: FamilyRow) -> bool:
    """Задание компании доступно для приглашений после «Готово»; банк — по статусу."""
    if row.company_id is None:
        return row.status in BANK_STATUSES
    return bool((row.spec or {}).get("ready"))


def _not_found() -> ProblemError:
    return ProblemError(404, "not_found", "Задание не найдено")


async def _row(
    session: AsyncSession, family_id: uuid.UUID, company_id: uuid.UUID | None
) -> FamilyRow:
    row = await session.get(FamilyRow, family_id)
    if row is None:
        raise _not_found()
    if row.company_id is not None:
        if company_id is None or row.company_id != company_id:
            raise _not_found()
    elif row.status not in BANK_STATUSES or row.kind == Kind.open.value:
        raise _not_found()
    return row


async def describe(
    session: AsyncSession, family_id: uuid.UUID, *, company_id: uuid.UUID, user_id: uuid.UUID
) -> InviteTaskInfo:
    row = await _row(session, family_id, company_id)
    if not is_ready(row):
        raise ProblemError(409, "task_not_ready", "Задание ещё черновик: нажмите «Готово»")
    fam = family_of(row)
    if fam is None:
        raise ProblemError(409, "family_unavailable", "Семейство заданий недоступно")
    item = build_item(fam, 0, None)
    form = (row.spec or {}).get("form") or {}
    return InviteTaskInfo(
        title=str(form.get("title") or row.slug),
        kind=row.kind,
        minutes=max(1, math.ceil(item.time_limit_s / 60)),
    )


async def _family(session: AsyncSession, family_id: uuid.UUID):
    row = await session.get(FamilyRow, family_id)
    fam = family_of(row) if row is not None else None
    if row is None or fam is None:
        raise ProblemError(503, "family_unavailable", "Семейство заданий недоступно")
    return row, fam


def _seed(candidate_id: uuid.UUID, offer_id: uuid.UUID, family_id: uuid.UUID) -> int:
    return item_seed(candidate_id, offer_id, family_id)


async def item(
    session: AsyncSession, family_id: uuid.UUID, *, candidate_id: uuid.UUID, offer_id: uuid.UUID
) -> dict[str, Any]:
    _, fam = await _family(session, family_id)
    return build_item(fam, _seed(candidate_id, offer_id, family_id), None).public()


async def submit(
    session: AsyncSession,
    family_id: uuid.UUID,
    *,
    candidate_id: uuid.UUID,
    offer_id: uuid.UUID,
    answer: Any,
) -> float | None:
    row, fam = await _family(session, family_id)
    if row.kind == Kind.open.value:
        return None
    seed = _seed(candidate_id, offer_id, family_id)
    it = build_item(fam, seed, None)
    score = max(0.0, min(1.0, float(fam.score(it, answer))))
    strength = round(EVIDENCE_MAX * score, 4)
    if strength > 0:
        await graph.upsert_evidence(
            session,
            candidate_id,
            [
                graph.EvidenceIn(
                    skill_id=row.skill_id,
                    source=EVIDENCE_SOURCE,
                    strength=strength,
                    observed_at=datetime.now(UTC).date(),
                    fact_type=FACT_TYPE,
                    fact_id=offer_id,
                    details={"score": round(score, 4), "kind": row.kind, "level": row.level},
                )
            ],
        )
    return score
