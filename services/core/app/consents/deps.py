from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends
from fsp_contracts.enums import ConsentType
from fsp_platform.app import ProblemError
from sqlalchemy.ext.asyncio import AsyncSession

from app.consents import service
from app.deps import get_session
from app.identity.deps import get_current_user
from app.identity.models import User


def require_consent(ctype: ConsentType) -> Callable[..., User]:
    """Зависимость эндпоинта: без действующего согласия — 403 `consent_required`."""

    async def dep(
        user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
    ) -> User:
        if not await service.has_consent(session, user.id, ctype):
            raise ProblemError(
                403,
                "consent_required",
                "Нужно согласие",
                f"Выдайте согласие {ctype.value}",
                errors=[{"field": "consent", "message": ctype.value}],
            )
        return user

    return dep
