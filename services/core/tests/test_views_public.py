"""Тесты для публичных эндпоинтов: бейджи SVG, профиль, OG-превью (E15-1)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.consents.models import Consent
from factories.base import make_candidate, make_grade
from fsp_contracts.assessment import TestGrade
from fsp_contracts.enums import ConsentType
from fsp_platform.db import session_scope


async def test_badge_endpoints_data_setup(factory):
    """Подготовка данных для тестирования badge endpoint."""
    async with session_scope(factory) as s:
        # Видимый кандидат
        cand1 = await make_candidate(s)
        cand1.visibility["public_profile"] = True
        consent1 = Consent(
            user_id=cand1.user_id,
            type=ConsentType.profile_publication,
            version="2025-09-01",
            granted_at=datetime.now(UTC),
        )
        s.add(consent1)
        await make_grade(s, cand1.user_id, "backend", TestGrade.middle)

        # Скрытый кандидат
        cand2 = await make_candidate(s)
        cand2.visibility["public_profile"] = False
        consent2 = Consent(
            user_id=cand2.user_id,
            type=ConsentType.profile_publication,
            version="2025-09-01",
            granted_at=datetime.now(UTC),
        )
        s.add(consent2)
        await make_grade(s, cand2.user_id, "backend", TestGrade.junior)

        # Без согласия
        cand3 = await make_candidate(s)
        cand3.visibility["public_profile"] = True
        await make_grade(s, cand3.user_id, "qa", TestGrade.senior)

        # Без грейда
        cand4 = await make_candidate(s)
        cand4.visibility["public_profile"] = True
        consent4 = Consent(
            user_id=cand4.user_id,
            type=ConsentType.profile_publication,
            version="2025-09-01",
            granted_at=datetime.now(UTC),
        )
        s.add(consent4)

        await s.flush()


async def test_slug_is_hmac_not_user_id(factory):
    """Slug (pseudo_id) это HMAC, не раскрывает user_id."""
    async with session_scope(factory) as s:
        cand = await make_candidate(s)
        pseudo_id = cand.pseudo_id
        user_id_str = str(cand.user_id)
        await s.flush()

        # Проверяем:
        # 1. pseudo_id не равен user_id
        assert pseudo_id != user_id_str
        # 2. pseudo_id не содержит user_id
        assert user_id_str not in pseudo_id
        # 3. pseudo_id это 12-символьный hex (HMAC)
        assert len(pseudo_id) == 12
        assert all(c in "0123456789abcdef" for c in pseudo_id)
