"""Подписки на категорию: `POST|GET /subscriptions`, `DELETE /subscriptions/{id}`."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies import service as companies
from app.deps import get_session
from app.identity.deps import require_roles
from app.identity.models import User
from app.matching import needs, subscriptions
from app.matching.subscriptions import SubscriptionCreate, SubscriptionOut
from app.openapi_errors import problem_responses

router = APIRouter(tags=["subscriptions"])

_employer = require_roles("employer")
_NEEDS = needs.NeedsConfig.load()


@router.post(
    "/subscriptions", status_code=201, response_model=SubscriptionOut,
    responses=problem_responses(401, 403, 404, 422, 429),
)  # fmt: skip
async def create_subscription(
    body: SubscriptionCreate,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Any:
    company, _ = await companies.require_company(session, user.id)
    return subscriptions.to_out(await subscriptions.create(session, company.id, body, _NEEDS))


@router.get(
    "/subscriptions",
    response_model=list[SubscriptionOut],
    responses=problem_responses(401, 403),
)
async def list_subscriptions(
    user: User = Depends(_employer), session: AsyncSession = Depends(get_session)
) -> Any:
    found = await companies.my_company(session, user.id)
    if found is None:  # новая компания: подписок ещё нет
        return []
    return [subscriptions.to_out(s) for s in await subscriptions.list_for(session, found[0].id)]


@router.delete(
    "/subscriptions/{subscription_id}", status_code=204, response_class=Response,
    responses=problem_responses(401, 403, 404),
)  # fmt: skip
async def delete_subscription(
    subscription_id: uuid.UUID,
    user: User = Depends(_employer),
    session: AsyncSession = Depends(get_session),
) -> Response:
    company, _ = await companies.require_company(session, user.id)
    await subscriptions.delete(session, company.id, subscription_id)
    return Response(status_code=204)
