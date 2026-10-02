"""Анкета кандидата: ленивое создание, псевдоним, pseudo_id, предпочтения, видимость, стоп-лист."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.models import DEFAULT_VISIBILITY, Candidate
from app.identity.models import utcnow

ACTIVE_DAYS = 7
STOPLIST_MAX = 200


def make_pseudo_id(secret: str, user_id: uuid.UUID) -> str:
    """HMAC(secret, user_id), 12 символов: по нему нельзя перебрать пользователей."""
    return hmac.new(secret.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()[:12]


def make_pseudonym() -> str:
    """Не зависит от ПДн; роль на момент создания неизвестна, поэтому нейтральный префикс."""
    return f"Candidate #{secrets.randbelow(9000) + 1000}"


async def get_or_create(session: AsyncSession, user_id: uuid.UUID, secret: str) -> Candidate:
    cand = await session.get(Candidate, user_id)
    if cand is not None:
        return cand
    for _ in range(20):  # коллизии 4-значных псевдонимов решаем повтором в savepoint
        cand = Candidate(
            user_id=user_id,
            pseudonym=make_pseudonym(),
            pseudo_id=make_pseudo_id(secret, user_id),
            visibility=dict(DEFAULT_VISIBILITY),
            formats=[],
            employment_types=[],
            stoplist_company_ids=[],
        )
        try:
            async with session.begin_nested():
                session.add(cand)
                await session.flush()
            return cand
        except IntegrityError:
            session.expunge(cand)
            existing = await session.get(Candidate, user_id)
            if existing is not None:  # параллельный запрос успел раньше
                return existing
    raise RuntimeError("pseudonym_exhausted")


async def get_by_pseudo_id(session: AsyncSession, pseudo_id: str) -> Candidate | None:
    return await session.scalar(
        select(Candidate).where(Candidate.pseudo_id == pseudo_id, Candidate.deleted_at.is_(None))
    )


async def update_preferences(session: AsyncSession, cand: Candidate, changes: dict) -> Candidate:
    """Частичное обновление; `search_status=active` ставит active_until=+7д, иной — сбрасывает."""
    for key in ("salary_min", "city", "relocation", "formats", "employment_types"):
        if key in changes:
            value = changes[key]
            if key in ("formats", "employment_types"):
                value = sorted({str(v) for v in value or []})
            setattr(cand, key, value)
    if "search_status" in changes and changes["search_status"] is not None:
        status = str(changes["search_status"])
        cand.search_status = status
        cand.active_until = utcnow() + timedelta(days=ACTIVE_DAYS) if status == "active" else None
    await session.flush()
    return cand


async def update_visibility(session: AsyncSession, cand: Candidate, changes: dict) -> Candidate:
    cand.visibility = {**DEFAULT_VISIBILITY, **cand.visibility, **changes}
    await session.flush()
    return cand


async def set_stoplist(
    session: AsyncSession, cand: Candidate, company_ids: list[uuid.UUID]
) -> Candidate:
    cand.stoplist_company_ids = sorted({str(c) for c in company_ids})
    await session.flush()
    return cand


def effective_status(cand: Candidate) -> str:
    """«Активно ищу» действует до active_until; потом считается как open."""
    if cand.search_status != "active":
        return cand.search_status
    until = cand.active_until
    if until is not None and until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    return "active" if until is not None and until > utcnow() else "open"
