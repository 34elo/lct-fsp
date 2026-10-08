"""Internal API fsp-connector для core-api (api.md §2.9): `Authorization: Service <token>`."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fsp_platform.app import ProblemError
from pydantic import BaseModel

from fsp_connector.linking import LinkService, token_ok

STATUS = {
    "fsp_not_found": (404, "Участник ФСП не найден"),
    "fsp_auth_error": (502, "ФСП отклонила запрос"),
    "fsp_bad_response": (502, "Некорректный ответ ФСП"),
    "fsp_unavailable": (503, "ФСП временно недоступна"),
    "fsp_error": (502, "Ошибка ФСП"),
}


async def require_core(request: Request, authorization: str | None = Header(default=None)) -> None:
    if not token_ok(request.app.state.settings.service_token_core, authorization):
        raise ProblemError(401, "unauthorized", "Нужен сервисный токен")


def get_links(request: Request) -> LinkService:
    return request.app.state.links


router = APIRouter(prefix="/internal", dependencies=[Depends(require_core)])


class ExchangeIn(BaseModel):
    code: str
    code_verifier: str
    candidate_id: UUID


class ExchangeOut(BaseModel):
    participant_id: str
    verified: bool


class LinkIn(BaseModel):
    candidate_id: UUID
    participant_id: str | None = None
    email: str | None = None
    manual: bool = False  # явный ручной ID без кода


class LinkOut(BaseModel):
    method: Literal["code", "manual"]
    masked_contact: str | None = None


class VerifyIn(BaseModel):
    candidate_id: UUID
    code: str


class VerifyOut(BaseModel):
    verified: bool


@router.get("/oauth/authorize-url")
async def authorize_url(
    state: str, code_challenge: str, links: LinkService = Depends(get_links)
) -> dict[str, str]:
    return {"url": links.authorize_url(state, code_challenge)}


@router.post("/oauth/exchange")
async def oauth_exchange(body: ExchangeIn, links: LinkService = Depends(get_links)) -> ExchangeOut:
    pid, verified = await links.exchange(body.candidate_id, body.code, body.code_verifier)
    return ExchangeOut(participant_id=pid, verified=verified)


@router.post("/links")
async def create_link(body: LinkIn, links: LinkService = Depends(get_links)) -> LinkOut:
    if body.manual:
        if not body.participant_id:
            raise ProblemError(422, "validation_error", "Для ручной привязки нужен participant_id")
        await links.link_manual(body.candidate_id, body.participant_id)
        return LinkOut(method="manual")
    method, masked = await links.start(body.candidate_id, body.participant_id, body.email)
    return LinkOut(method=method, masked_contact=masked.masked if masked else None)


@router.post("/links/verify")
async def verify_link(body: VerifyIn, links: LinkService = Depends(get_links)) -> VerifyOut:
    return VerifyOut(verified=await links.verify(body.candidate_id, body.code))


# -------------------------------------------------------------------------- демо (E13-3)
@router.post("/demo/fsp-result", status_code=202)
async def demo_create_fsp_result(request: Request) -> dict[str, str]:
    """Демо: создать результат ФСП для случайного кандидата (E13-3)."""
    if not request.app.state.settings.demo_mode:
        raise ProblemError(400, "demo_disabled", "Демо-режим отключен")
    from fsp_connector.service import demo_create_result

    await demo_create_result(request.app.state.adapter)
    return {"status": "accepted"}


@router.post("/demo/reset", status_code=202)
async def demo_reset_fsp(request: Request) -> dict[str, str]:
    """Демо: сброс результатов ФСП (E13-3)."""
    if not request.app.state.settings.demo_mode:
        raise ProblemError(400, "demo_disabled", "Демо-режим отключен")
    from fsp_connector.service import demo_reset

    await demo_reset(request.app.state.adapter)
    return {"status": "accepted"}
