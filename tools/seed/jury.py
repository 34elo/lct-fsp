"""Демо-аккаунты жюри (E32-4b): чистый кандидат без грейда и работодатель с проверенной компанией.

Кандидат проходит экспресс-тест с нуля (вход `/me/assessment?mode=express`), работодатель ищет
кандидатов в уже наполненной витрине. Только вымышленные данные, пароль — тестовый (config.yaml).
Идемпотентно: существующие по email пропускаются.
"""

from __future__ import annotations

from typing import Any

from app.candidates import service as candidates
from app.companies import service as companies
from app.consents import service as consents
from app.identity import service as identity
from fsp_contracts.enums import ConsentType
from fsp_platform.db import session_scope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .plan import load_config

JURY_COMPANY = {
    "name": "Жюри Демо",
    "inn": "7700000999",
    "site": "https://jury-demo.example.test",
    "description": "Вымышленная компания для показа жюри.",
}


def jury_emails() -> dict[str, str]:
    demo = load_config()["demo"]
    return {"candidate": demo["jury_candidate_email"], "employer": demo["jury_employer_email"]}


async def _exists(s: AsyncSession, email: str) -> bool:
    from app.identity.models import User

    found = await s.scalar(select(User.id).where(User.email == identity.normalize_email(email)))
    return found is not None


async def seed_jury(
    factory: async_sessionmaker[AsyncSession], *, password: str, pseudo_secret: str
) -> dict[str, Any]:
    emails = jury_emails()
    stats = {"jury_candidate": 0, "jury_employer": 0}
    async with session_scope(factory) as s:
        if not await _exists(s, emails["candidate"]):
            user = await identity.register(s, emails["candidate"], password, "candidate")
            cand = await candidates.get_or_create(s, user.id, pseudo_secret)
            await candidates.update_preferences(
                s,
                cand,
                {
                    "city": "Москва",
                    "relocation": False,
                    "salary_min": 100000,
                    "formats": ["remote"],
                    "employment_types": ["full"],
                    "search_status": "active",
                },
            )
            await consents.set_consents(
                s,
                user.id,
                [(ConsentType(t), True, None) for t in ("pd_processing", "profile_publication")],
            )
            stats["jury_candidate"] = 1
    async with session_scope(factory) as s:
        if not await _exists(s, emails["employer"]):
            user = await identity.register(s, emails["employer"], password, "employer")
            company = await companies.create_company(s, user, dict(JURY_COMPANY))
            await companies.verify(s, company.id)
            stats["jury_employer"] = 1
    return stats
