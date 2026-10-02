"""Согласия (security.md §2): каждое — отдельный документ, версионируется, отзывается."""

from __future__ import annotations

import uuid
from datetime import datetime

from fsp_contracts.enums import ConsentType
from fsp_platform.app import ProblemError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.consents.models import Consent
from app.identity.models import utcnow

REQUIRED = frozenset({ConsentType.pd_processing})
# Текущая версия текста каждого согласия; смена версии = повторный запрос согласия.
CURRENT_VERSIONS: dict[ConsentType, str] = {t: "2025-09-01" for t in ConsentType}


async def active(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Consent]:
    """Действующие (не отозванные) согласия по типу; при дублях — последнее выданное."""
    rows = await session.scalars(
        select(Consent)
        .where(Consent.user_id == user_id, Consent.revoked_at.is_(None))
        .order_by(Consent.granted_at)
    )
    return {c.type: c for c in rows}


async def has_consent(session: AsyncSession, user_id: uuid.UUID, ctype: ConsentType) -> bool:
    return str(ctype) in await active(session, user_id)


async def set_consents(
    session: AsyncSession,
    user_id: uuid.UUID,
    changes: list[tuple[ConsentType, bool, str | None]],
) -> None:
    """Выдать/отозвать. Идемпотентно: повтор выдачи той же версии ничего не меняет."""
    now: datetime = utcnow()
    current = await active(session, user_id)
    for ctype, granted, version in changes:
        cur = current.get(ctype.value)
        if granted:
            expected = CURRENT_VERSIONS[ctype]
            if version is not None and version != expected:
                raise ProblemError(
                    409,
                    "consent_version_mismatch",
                    "Текст согласия обновился",
                    f"Актуальная версия {ctype.value}: {expected}",
                )
            if cur is not None and cur.version == expected:
                continue
            if cur is not None:
                cur.revoked_at = now
            session.add(
                Consent(user_id=user_id, type=ctype.value, version=expected, granted_at=now)
            )
        elif cur is not None:
            cur.revoked_at = now
    await session.flush()
