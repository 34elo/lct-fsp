"""Привязка ФСП для web: OAuth «Войти через ФСП», код, ручной ID (api.md §1, §2.2)."""

from __future__ import annotations

import uuid
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from fsp_contracts.enums import ConsentType
from fsp_platform.app import ProblemError
from fsp_platform.ratelimit import RateLimiter
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service as candidates
from app.consents.deps import require_consent
from app.deps import get_limiter, get_redis, get_session
from app.fsp import service
from app.fsp.client import ConnectorClient
from app.identity.deps import _bearer, get_current_user, require_roles
from app.identity.models import User
from app.matching import card
from app.openapi_errors import problem_responses
from app.telegram.service import safe_redirect

router = APIRouter(tags=["fsp"])
_owner = require_roles("candidate")
_writer = require_consent(ConsentType.pd_processing)


async def owner(user: User = Depends(_owner)) -> User:
    return user


async def writer(user: User = Depends(owner), _: User = Depends(_writer)) -> User:
    return user


def get_connector(request: Request) -> ConnectorClient:
    client = getattr(request.app.state, "fsp_client", None)
    if client is None:
        s = request.app.state.settings
        if not (s.fsp_connector_url and s.service_token_core):
            raise ProblemError(503, "fsp_unavailable", "Интеграция с ФСП не настроена")
        client = ConnectorClient(s.fsp_connector_url, s.service_token_core)
        request.app.state.fsp_client = client
    return client


async def _ensure_candidate(request: Request, session: AsyncSession, user: User) -> None:
    secret = request.app.state.settings.pseudo_id_secret
    await candidates.get_or_create(session, user.id, secret)  # FK fsp_participants → candidates


# ------------------------------------------------------------------------------- OAuth
class StartOut(BaseModel):
    url: str


@router.get(
    "/auth/fsp/start",
    response_model=StartOut,
    responses={302: {"description": "redirect"}, **problem_responses(401, 403, 503)},
)
async def fsp_start(
    request: Request,
    redirect: bool = Query(default=False, description="true — 302 на ФСП вместо JSON"),
    next: str = Query(default="/me", max_length=200),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    connector: ConnectorClient = Depends(get_connector),
):
    """Для вошедшего кандидата — привязка ФСП. Анонимный вход через ФСП пока не поддержан."""
    if not _bearer(request):
        if redirect:
            return RedirectResponse("/login?fsp=need_login", status_code=302)
        raise ProblemError(401, "unauthorized", "Войдите, чтобы привязать ФСП")
    user = await get_current_user(request, session)
    if user.role != "candidate":
        raise ProblemError(403, "forbidden", "Недостаточно прав")
    await _ensure_candidate(request, session, user)
    verifier, challenge = service.pkce_pair()
    state = await service.put_state(redis, user.id, verifier, safe_redirect(next))
    url = await connector.authorize_url(state, challenge)
    if redirect:
        return RedirectResponse(url, status_code=302)
    return StartOut(url=url)


@router.get("/auth/fsp/callback", include_in_schema=True)
async def fsp_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    redis: Redis = Depends(get_redis),
    connector: ConnectorClient = Depends(get_connector),
):
    """Возврат из ФСП: обмен кода и привязка; всегда 302 обратно в SPA."""
    base = request.app.state.settings.web_base_url.rstrip("/")

    def back(path: str, **q: str) -> RedirectResponse:
        sep = "&" if "?" in path else "?"
        return RedirectResponse(f"{base}{path}{sep}{urlencode(q)}", status_code=302)

    data = await service.take_state(redis, state) if state else None
    if data is None:
        return back("/me", fsp="error", reason="state_invalid")
    next_path = data["next"]
    if error or not code:
        return back(next_path, fsp="error", reason="denied")

    try:
        await connector.exchange(uuid.UUID(data["user_id"]), code, data["verifier"])
    except ProblemError as exc:
        return back(next_path, fsp="error", reason=exc.code)
    return back(next_path, fsp="linked")


# ------------------------------------------------------------------- код и ручной ID
class LinkIn(BaseModel):
    participant_id: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=254)
    manual: bool = False


class LinkOut(BaseModel):
    method: Literal["code", "manual"]
    masked_contact: str | None = None


class VerifyIn(BaseModel):
    code: str = Field(min_length=1, max_length=16)


class VerifyOut(BaseModel):
    verified: bool


@router.post(
    "/candidates/me/fsp/link",
    response_model=LinkOut,
    responses=problem_responses(401, 403, 422, 429, 503),
)
async def fsp_link(
    body: LinkIn,
    request: Request,
    user: User = Depends(writer),
    session: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_limiter),
    connector: ConnectorClient = Depends(get_connector),
):
    await limiter.check(f"fsplink:{user.id}", 10, 600)
    if not (body.participant_id or body.email):
        raise ProblemError(422, "validation_error", "Укажите ID участника или email")
    await _ensure_candidate(request, session, user)
    data = await connector.link(
        user.id, participant_id=body.participant_id, email=body.email, manual=body.manual
    )
    return LinkOut(method=data["method"], masked_contact=data.get("masked_contact"))


@router.post(
    "/candidates/me/fsp/verify",
    response_model=VerifyOut,
    responses=problem_responses(401, 403, 422, 429, 503),
)
async def fsp_verify(
    body: VerifyIn,
    user: User = Depends(writer),
    limiter: RateLimiter = Depends(get_limiter),
    connector: ConnectorClient = Depends(get_connector),
):
    await limiter.check(f"fspverify:{user.id}", 20, 600)
    data = await connector.verify(user.id, body.code)
    return VerifyOut(verified=bool(data.get("verified")))


@router.post("/candidates/me/fsp/sync", status_code=202, responses=problem_responses(401, 403, 503))
async def fsp_sync(
    user: User = Depends(writer),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
):
    await service.request_sync(session, redis, user.id)
    return {"status": "accepted"}


# -------------------------------------------------------------------------- чтение
class FspLink(BaseModel):
    linked: bool
    verified: bool
    participant_id: str | None = None


class FspTeam(BaseModel):
    id: str
    name: str
    role: str | None = None


class FspOverview(BaseModel):
    link: FspLink
    achievements: list[card.FspAchievement]
    ranks: list[card.FspRankBrief]
    teams: list[FspTeam]


@router.get("/candidates/me/fsp", response_model=FspOverview, responses=problem_responses(401, 403))
async def fsp_overview(
    request: Request,
    user: User = Depends(owner),
    session: AsyncSession = Depends(get_session),
):
    cand = await candidates.get_or_create(
        session, user.id, request.app.state.settings.pseudo_id_secret
    )
    own = await card.owner_fsp(session, cand)
    return FspOverview(
        link=FspLink(**await service.link_status(session, user.id)),
        achievements=own.achievements if own else [],
        ranks=own.ranks if own else [],
        teams=[FspTeam(**t) for t in await service.teams_of(session, user.id)],
    )


# -------------------------------------------------------------------------- админ: демо (E13-3)
_admin = require_roles("fsp_admin")


@router.post(
    "/admin/demo/fsp-result",
    status_code=202,
    responses=problem_responses(400, 401, 403),
)
async def admin_demo_create_fsp_result(
    request: Request,
    user: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
    connector: ConnectorClient = Depends(get_connector),
):
    """Админ: демо-кнопка создания результата ФСП для случайного кандидата (E13-3).
    Создаёт результат в мок-ФСП и отправляет вебхук для синхронизации.
    Доступно только при DEMO_MODE=true."""
    if not request.app.state.settings.demo_mode:
        raise ProblemError(400, "demo_disabled", "Демо-режим отключен")
    await service.demo_create_result(session, connector)
    return {"status": "accepted"}


@router.post(
    "/admin/demo/reset",
    status_code=202,
    responses=problem_responses(400, 401, 403),
)
async def admin_demo_reset_fsp(
    request: Request,
    user: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
    connector: ConnectorClient = Depends(get_connector),
):
    """Админ: демо-кнопка сброса всех результатов ФСП к снапшоту (E13-3).
    Доступно только при DEMO_MODE=true."""
    if not request.app.state.settings.demo_mode:
        raise ProblemError(400, "demo_disabled", "Демо-режим отключен")
    await service.demo_reset(session, connector)
    return {"status": "accepted"}
