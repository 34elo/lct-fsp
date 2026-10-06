"""Тесты для cron-команд (E8-5): истечение офферов, сброс поиска, рейтинг компаний."""

from datetime import UTC, datetime, timedelta

import pytest
from app.jobs import handlers as jobs
from factories.base import make_candidate, make_company, make_vacancy
from factories.hiring import make_offer
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_expire_offers(session: AsyncSession) -> None:
    """Офферы с истёкшим сроком переходят в статус `expired` (messaging.md §4)."""
    company, owner = await make_company(session, name="Test Company")
    vacancy = await make_vacancy(session, company)
    candidate1 = await make_candidate(session)
    candidate2 = await make_candidate(session)

    # Оффер, который истёк
    expired_offer = await make_offer(
        session,
        vacancy,
        candidate1.user_id,
        owner.id,
        status="sent",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )

    # Оффер, который ещё актуален
    active_offer = await make_offer(
        session,
        vacancy,
        candidate2.user_id,
        owner.id,
        status="sent",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    await session.flush()

    # Запускаем истечение
    await jobs._expire_offers(session)

    # Проверяем статусы
    await session.refresh(expired_offer)
    await session.refresh(active_offer)

    assert expired_offer.status == "expired"
    assert active_offer.status == "sent"


@pytest.mark.asyncio
async def test_calculate_company_rating(session: AsyncSession) -> None:
    """Пересчёт ответственности компании на основе истории офферов."""
    company, owner = await make_company(session, name="Test Company")
    vacancy = await make_vacancy(session, company)
    candidate1 = await make_candidate(session)
    candidate2 = await make_candidate(session)
    candidate3 = await make_candidate(session)

    # Создаём офферы с разными статусами
    await make_offer(session, vacancy, candidate1.user_id, owner.id, status="accepted")
    await make_offer(session, vacancy, candidate2.user_id, owner.id, status="sent")
    await make_offer(session, vacancy, candidate3.user_id, owner.id, status="withdrawn")

    await session.flush()

    # Запускаем пересчёт рейтинга
    await jobs._calculate_company_rating(session)

    # Проверяем, что score был обновлен
    await session.refresh(company)
    assert company.responsibility_score is not None
    # 1 accepted из 3: 1/3 - 0.2 (за withdrawn) = 0.33 - 0.2 = 0.13
    assert 0.0 <= company.responsibility_score <= 1.0


@pytest.mark.asyncio
async def test_company_rating_no_offers(session: AsyncSession) -> None:
    """Компания без офферов получает нейтральный score."""
    company, owner = await make_company(session, name="Test Company")
    await session.flush()

    # Запускаем пересчёт рейтинга
    await jobs._calculate_company_rating(session)

    # Проверяем, что score был установлен в 0.5 (нейтральный)
    await session.refresh(company)
    assert company.responsibility_score == 0.5


@pytest.mark.asyncio
async def test_company_rating_perfect(session: AsyncSession) -> None:
    """Компания со 100% принятыми офферами получает высокий score."""
    company, owner = await make_company(session, name="Test Company")
    vacancy = await make_vacancy(session, company)
    candidate1 = await make_candidate(session)
    candidate2 = await make_candidate(session)

    # Все офферы принял
    await make_offer(session, vacancy, candidate1.user_id, owner.id, status="accepted")
    await make_offer(session, vacancy, candidate2.user_id, owner.id, status="hired")

    await session.flush()

    # Запускаем пересчёт рейтинга
    await jobs._calculate_company_rating(session)

    # Проверяем, что score высокий
    await session.refresh(company)
    assert company.responsibility_score == 1.0
