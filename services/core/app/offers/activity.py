"""Лента активности работодателя (E35-12b): `GET /employer/activity`.

Собирается из данных компании: попадания в её подписки, интересы и приглашения, ответы на
задания в приглашениях. Только её собственные строки (по `company_id`), кандидат — анонимная
карточка (`pseudo_id`, псевдоним, роль, грейд); контактов и ПДн нет даже после принятия.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fsp_contracts.hiring import ActivityCandidate, ActivityEvent, ActivityFeed, ActivityKind
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service as candidates
from app.companies import service as companies
from app.deps import get_session
from app.identity.deps import require_roles
from app.identity.models import User
from app.matching import subscriptions
from app.matching.service import visible_ids
from app.offers.models import Offer, OfferTask
from app.openapi_errors import problem_responses

router = APIRouter(tags=["employer"])
_employer = require_roles("employer")

_MAX = 100


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _card_link(pseudo_id: str) -> str:
    return f"/employer/candidates/{pseudo_id}"


async def build_feed(
    session: AsyncSession, company_id: uuid.UUID, limit: int
) -> list[ActivityEvent]:
    # (время, вид, id кандидата, оффер, подписка, detail)
    raw: list[tuple[datetime, ActivityKind, uuid.UUID | None, Offer | None, Any, str | None]] = []

    for sub, hit in await subscriptions.recent_hits(session, company_id, limit):
        raw.append((_aware(hit.created_at), ActivityKind.subscription_hit, hit.candidate_id,
                    None, sub, sub.profession))  # fmt: skip

    offers = list(
        await session.scalars(
            select(Offer).where(Offer.company_id == company_id, Offer.candidate_id.is_not(None))
        )
    )
    by_id = {o.id: o for o in offers}
    for o in offers:
        if o.interest_at is not None and o.interest_opened_at is not None:
            raw.append((_aware(o.interest_opened_at), ActivityKind.interest_opened,
                        o.candidate_id, o, None, None))  # fmt: skip
        if o.responded_at is None:
            continue
        in_interest = o.interest_at is not None and o.invited_at is None
        if o.status == "declined":
            kind = (
                ActivityKind.interest_declined if in_interest else ActivityKind.invitation_declined
            )
            raw.append((_aware(o.responded_at), kind, o.candidate_id, o, None, o.decline_reason))
        elif o.status == "accepted" and o.initiator == "employer":
            raw.append((_aware(o.responded_at), ActivityKind.invitation_accepted,
                        o.candidate_id, o, None, None))  # fmt: skip

    tasks = await session.scalars(
        select(OfferTask).where(
            OfferTask.company_id == company_id, OfferTask.answered_at.is_not(None)
        )
    )
    for t in tasks:
        o = by_id.get(t.offer_id)
        if o is not None:
            raw.append((_aware(t.answered_at), ActivityKind.task_answered, o.candidate_id,
                        o, None, t.title))  # fmt: skip

    raw.sort(key=lambda r: r[0], reverse=True)
    raw = raw[:limit]

    # подписочные попадания показываем только пока кандидат виден работодателям
    hit_ids = [r[2] for r in raw if r[1] is ActivityKind.subscription_hit and r[2]]
    visible = await visible_ids(session, hit_ids)

    out: list[ActivityEvent] = []
    for at, kind, cid, offer, sub, detail in raw:
        if cid is None:
            continue
        if kind is ActivityKind.subscription_hit and cid not in visible:
            continue
        cand = await candidates.get(session, cid)
        if cand is None or cand.deleted_at is not None:
            continue
        key = f"{kind.value}:{offer.id if offer else sub.id}:{cid}"
        out.append(
            ActivityEvent(
                id=key, kind=kind, at=at,
                candidate=ActivityCandidate(
                    pseudo_id=cand.pseudo_id, pseudonym=cand.pseudonym,
                    primary_role=cand.primary_role, grade=cand.grade,
                ),
                link=f"/employer/offers/{offer.id}" if offer else _card_link(cand.pseudo_id),
                offer_id=offer.id if offer else None,
                subscription_id=sub.id if sub else None,
                detail=detail,
            )
        )  # fmt: skip
    return out


@router.get(
    "/employer/activity", response_model=ActivityFeed, responses=problem_responses(401, 403, 404)
)
async def employer_activity(
    limit: int = Query(default=30, ge=1, le=_MAX),
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Лента событий компании, новые сверху. Чужие данные в неё не попадают."""
    company, _ = await companies.require_company(session, user.id)
    return ActivityFeed(items=await build_feed(session, company.id, limit))
