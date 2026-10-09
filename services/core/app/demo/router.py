"""`POST /auth/jury` — вход «Демо для жюри» в свою песочницу (E40-1). Только при `DEMO_MODE`."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from fsp_platform.app import ProblemError
from fsp_platform.ratelimit import RateLimiter
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.demo import service
from app.deps import get_limiter, get_session
from app.identity import service as identity
from app.identity.router import AuthOut, _client_ip, tokens_out
from app.openapi_errors import problem_responses

router = APIRouter(tags=["auth"])


class JuryIn(BaseModel):
    role: Literal["candidate", "employer"]
    pair: str | None = Field(default=None, max_length=32)  # ключ песочницы из прошлого входа


class JuryAuthOut(AuthOut):
    pair: str  # ключ песочницы: браузер хранит и передаёт при следующем входе


@router.post("/auth/jury", response_model=JuryAuthOut, responses=problem_responses(404, 429))
async def jury_enter(
    body: JuryIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_limiter),
) -> JuryAuthOut:
    """Вход жюри без пароля: своя пара «кандидат + работодатель» (демо, `is_demo`).

    Тот же `pair` — та же песочница; без него или с чужим форматом — новая. Вне `DEMO_MODE` — 404.
    """
    s = request.app.state.settings
    if not s.demo_mode:
        raise ProblemError(404, "not_found", "Не найдено")
    await limiter.check(f"jury:ip:{_client_ip(request)}", 30, 600)
    user, pair, created = await service.enter(
        session, body.role, body.pair, pseudo_secret=s.pseudo_id_secret
    )
    issued = await identity.issue_tokens(
        session, s.jwt_secret, user, request.headers.get("user-agent")
    )
    out = tokens_out(request, response, issued)
    if created and body.role == "candidate":
        await session.commit()  # кандидат существует до привязки ФСП
        from app.fsp.router import get_connector

        try:
            connector = get_connector(request)
        except ProblemError:
            connector = None
        if connector is not None:
            await service.copy_fsp_registry(connector, str(user.email))
    return JuryAuthOut(**out.model_dump(), pair=pair)
