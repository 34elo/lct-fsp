from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fsp_platform.app import ProblemError, problem_response
from fsp_platform.ratelimit import RateLimiter
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies import service as companies
from app.consents import service as consents
from app.deps import get_limiter, get_session
from app.identity import service
from app.identity.deps import get_current_user
from app.identity.models import User

router = APIRouter(tags=["auth"])
REFRESH_COOKIE = "rt"


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)
    role: Literal["candidate", "employer"]


class LoginIn(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: UUID
    email: str | None
    role: str

    @classmethod
    def of(cls, u: User) -> UserOut:
        return cls(id=u.id, email=u.email, role=u.role)


class AuthOut(BaseModel):
    access_token: str
    user: UserOut


def _set_cookie(request: Request, response: Response, token: str) -> None:
    s = request.app.state.settings
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=int(service.REFRESH_TTL.total_seconds()),
        path=s.auth_cookie_path,
        httponly=True,
        secure=s.env != "dev",
        samesite="lax",
    )


def _clear_cookie(request: Request, response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=request.app.state.settings.auth_cookie_path)


def _check_origin(request: Request) -> None:
    """CSRF для cookie-эндпоинтов (security.md §1): Origin, если есть, должен быть разрешённым."""
    origin = request.headers.get("origin")
    allowed = request.app.state.settings.allowed_origins
    if origin and allowed and origin not in allowed:
        raise ProblemError(403, "forbidden_origin", "Недопустимый источник запроса")


def _tokens_out(request: Request, response: Response, issued: service.IssuedTokens) -> AuthOut:
    _set_cookie(request, response, issued.refresh_token)
    return AuthOut(access_token=issued.access_token, user=UserOut.of(issued.user))


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "-")


@router.post("/auth/register", status_code=201, response_model=AuthOut)
async def register(
    body: RegisterIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_limiter),
):
    await limiter.check(f"register:ip:{_client_ip(request)}", 10, 60)
    user = await service.register(session, body.email, body.password, body.role)
    issued = await service.issue_tokens(
        session, request.app.state.settings.jwt_secret, user, request.headers.get("user-agent")
    )
    return _tokens_out(request, response, issued)


@router.post("/auth/login", response_model=AuthOut)
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_limiter),
):
    # messaging.md §7: 10/мин на IP, 5/мин на email
    await limiter.check(f"login:ip:{_client_ip(request)}", 10, 60)
    await limiter.check(f"login:email:{service.normalize_email(body.email)}", 5, 60)
    user = await service.authenticate(session, body.email, body.password)
    issued = await service.issue_tokens(
        session, request.app.state.settings.jwt_secret, user, request.headers.get("user-agent")
    )
    return _tokens_out(request, response, issued)


@router.post("/auth/refresh", response_model=AuthOut)
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    _check_origin(request)
    issued = await service.rotate(
        session,
        request.app.state.settings.jwt_secret,
        request.cookies.get(REFRESH_COOKIE),
        request.headers.get("user-agent"),
    )
    if issued is None:
        # отзыв семьи должен попасть в БД, поэтому не исключение, а обычный ответ
        resp = problem_response(401, "refresh_reused", "Сессия недействительна", "Войдите заново")
        _clear_cookie(request, resp)
        return resp
    return _tokens_out(request, response, issued)


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, session: AsyncSession = Depends(get_session)):
    _check_origin(request)
    await service.logout(session, request.cookies.get(REFRESH_COOKIE))
    resp = Response(status_code=204)
    _clear_cookie(request, resp)
    return resp


class MeCompany(BaseModel):
    id: UUID
    name: str
    status: str
    role: str


class MeOut(UserOut):
    consents: list[str]
    company: MeCompany | None = None


@router.get("/me", response_model=MeOut)
async def me(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """consents — действующие типы; company — E6-1; candidate, telegram_linked — E3-1, E1-3."""
    found = await companies.my_company(session, user.id) if user.role == "employer" else None
    return MeOut(
        **UserOut.of(user).model_dump(),
        consents=sorted(await consents.active(session, user.id)),
        company=MeCompany(
            id=found[0].id, name=found[0].name, status=found[0].status, role=found[1].role
        )
        if found
        else None,
    )
