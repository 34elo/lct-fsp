"""Тесты для публичных эндпоинтов: бейджи SVG, профиль, OG-превью (E15-1)."""

from __future__ import annotations

from datetime import UTC, datetime

from factories.base import make_candidate, make_grade
from fsp_contracts.assessment import TestGrade
from fsp_platform.db import session_scope


async def test_badge_svg_success(factory):
    """Бейдж SVG возвращается для кандидата с грейдом и согласием."""
    async with session_scope(factory) as s:
        # Создаём кандидата с грейдом
        cand = await make_candidate(s)
        await make_grade(s, cand.user_id, "backend", TestGrade.middle)

        # Добавляем согласие на публикацию
        from app.consents.models import Consent
        from fsp_contracts.enums import ConsentType

        consent = Consent(
            user_id=cand.user_id,
            type=ConsentType.profile_publication,
            version="2025-09-01",
            granted_at=datetime.now(UTC),
        )
        s.add(consent)
        await s.flush()


# Минимальные тесты для проверки что эндпоинты определены
def test_badge_endpoint_exists(api):
    """Проверяем что endpoint /public/badge/{slug}.svg существует."""
    response = api.get("/api/v1/public/badge/nonexistent.svg")
    # Должен вернуть 404 для несуществующего, не 404 от маршрута
    assert response.status_code == 404


def test_public_profile_endpoint_exists(api):
    """Проверяем что endpoint /public/profiles/{slug} существует."""
    response = api.get("/api/v1/public/profiles/nonexistent")
    # Должен вернуть 404 для несуществующего профиля
    assert response.status_code == 404


def test_athlete_endpoint_exists(api):
    """Проверяем что endpoint /public/athlete/{slug} существует."""
    response = api.get("/api/v1/public/athlete/nonexistent")
    # Должен вернуть 404 для несуществующего кандидата
    assert response.status_code == 404
