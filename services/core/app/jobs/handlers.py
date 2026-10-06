"""Cron-команды `core.jobs` (messaging.md §4): истечение офферов, сброс поиска, рейтинг компаний.

Все обработчики вызываются раз в час (или чаще для offers.expire) из scheduler.
Идемпотентность не требуется: это cron, повтор означает просто повторный расчёт.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fsp_contracts import Envelope
from fsp_platform.messaging import Consumer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.companies.models import Company
from app.matching import needs as needs_cfg
from app.matching import subscriptions
from app.offers import service as offers
from app.offers.models import Offer

log = structlog.get_logger()


async def _expire_offers(session: AsyncSession) -> None:
    """Переведи `sent|viewed` офферы с истёкшим сроком в статус `expired` (E8-5)."""
    count = await offers.expire_due(session)
    if count > 0:
        log.info("offers_expired", count=count)


async def _expire_active_status(session: AsyncSession, now: datetime | None = None) -> None:
    """«Активно ищу» истекает на чтении: `candidates.service.effective_status` трактует
    просроченный `active` как `open`. Таблицу кандидатов (зона Б1) не трогаем (E8-5)."""
    return None


async def _calculate_company_rating(session: AsyncSession, now: datetime | None = None) -> None:
    """Пересчёт ответственности компаний на основе истории офферов (E8-5).

    Формула:
    - Доля принятых офферов из отправленных: (accepted + hired) / sent
    - Штраф за отозванные: -0.2 за каждое
    - Штраф за просроченные (без ответа): -0.1 за каждое
    - Финальный score: max(0, min(1, доля + штрафы))
    """
    now = now or datetime.now(UTC)

    # Получаем статистику по каждой компании
    # Группируем офферы по компании и считаем по статусам
    q = (
        select(
            Company,
            func.count(Offer.id).filter(Offer.status.in_(("sent", "viewed"))).label("open_count"),
            func.count(Offer.id).filter(Offer.status == "accepted").label("accepted_count"),
            func.count(Offer.id).filter(Offer.status == "hired").label("hired_count"),
            func.count(Offer.id).filter(Offer.status == "withdrawn").label("withdrawn_count"),
            func.count(Offer.id).filter(Offer.status == "expired").label("expired_count"),
            func.count(Offer.id).label("total_count"),
        )
        .outerjoin(Offer, Offer.company_id == Company.id)
        .group_by(Company.id)
    )

    companies_data = await session.execute(q)

    for company, _open_c, accepted_c, hired_c, withdrawn_c, expired_c, total_c in companies_data:
        if total_c == 0:
            # Нет офферов — нейтральный score
            score = 0.5
        else:
            # Доля успешных (accepted + hired)
            successful = accepted_c + hired_c
            success_rate = successful / total_c

            # Штрафы: за каждый отозванный и просроченный
            penalties = (withdrawn_c * 0.2) + (expired_c * 0.1)

            # Финальный score: 0 to 1
            score = max(0.0, min(1.0, success_rate - penalties))

        company.responsibility_score = score

    await session.flush()
    log.info("company_ratings_updated")


def register(
    consumers: dict[str, Consumer],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Регистрирует обработчики cron-команд в очереди `core.jobs`."""

    @consumers["core.jobs"].on("offers.expire")
    async def on_offers_expire(envelope: Envelope, session: AsyncSession) -> None:
        """Периодическое истечение офферов (каждые 5 минут, messaging.md §4)."""
        # CoreJob.model_validate(envelope.payload)  # пусто, но валидируем
        await _expire_offers(session)
        # E33-4: отложенные дайджесты подписок на категории (интервал проверяет flush_due)
        await subscriptions.flush_due(session, needs_cfg.NeedsConfig.load())

    @consumers["core.jobs"].on("active_status.expire")
    async def on_active_status_expire(envelope: Envelope, session: AsyncSession) -> None:
        """Сброс статуса 'активно ищу' по истечении периода (каждый час)."""
        # CoreJob.model_validate(envelope.payload)  # пусто
        await _expire_active_status(session)

    @consumers["core.jobs"].on("company.rating")
    async def on_company_rating(envelope: Envelope, session: AsyncSession) -> None:
        """Пересчёт ответственности компаний (каждый час)."""
        # CoreJob.model_validate(envelope.payload)  # пусто
        await _calculate_company_rating(session)
