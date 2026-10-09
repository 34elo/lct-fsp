"""Цифры для лендинга (E39-35): `GET /public/stats`.

Только агрегаты: никаких идентификаторов, имён и ПДн. Без авторизации, кеш в Redis на 5 минут.
Пока данных нет, поле `null`, и лендинг скрывает свой счётчик.
"""

from __future__ import annotations

from datetime import UTC, datetime
from statistics import median
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fsp_contracts.enums import CompanyStatus
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import service as assessment
from app.companies import service as companies
from app.deps import get_redis, get_session
from app.offers import service as offers

CACHE_KEY = "c:public:stats"
CACHE_TTL_S = 300

router = APIRouter(prefix="/public", tags=["public"])


class PublicStatsOut(BaseModel):
    candidates: int | None = None  # прошли тест и получили грейд
    companies: int | None = None  # проверенные компании
    invitations: int | None = None  # приглашения от компаний
    median_days_to_invite: int | None = None  # от первого грейда до первого приглашения


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def median_days(graded: dict[UUID, datetime], invited: dict[UUID, datetime]) -> int | None:
    """Медиана дней между первым грейдом и первым приглашением (у кого есть обе даты)."""
    days = [
        max(0.0, (_aware(invited[cid]) - _aware(at)).total_seconds() / 86400)
        for cid, at in graded.items()
        if cid in invited
    ]
    return round(median(days)) if days else None


async def build(session: AsyncSession) -> PublicStatsOut:
    graded = await assessment.graded_candidates_first_at(session)
    invitations, invited = await offers.first_invitations(session)
    verified = await companies.count_by_status(session, CompanyStatus.verified.value)
    return PublicStatsOut(
        candidates=len(graded) or None,
        companies=verified or None,
        invitations=invitations or None,
        median_days_to_invite=median_days(graded, invited),
    )


@router.get("/stats", response_model=PublicStatsOut, summary="Цифры для лендинга")
async def get_stats(
    response: Response,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> PublicStatsOut:
    """Кандидаты, компании, приглашения и медиана дней до первого приглашения. Кеш 5 минут."""
    response.headers["Cache-Control"] = f"public, max-age={CACHE_TTL_S}"
    try:
        raw = await redis.get(CACHE_KEY)
        if raw:
            return PublicStatsOut.model_validate_json(raw)
    except Exception:  # noqa: BLE001 - кеш необязателен
        pass
    out = await build(session)
    try:
        await redis.set(CACHE_KEY, out.model_dump_json(), ex=CACHE_TTL_S)
    except Exception:  # noqa: BLE001
        pass
    return out
