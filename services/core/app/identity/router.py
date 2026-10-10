from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fsp_platform.app import ProblemError, problem_response
from fsp_platform.ratelimit import RateLimiter
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service as candidates
from app.companies import service as companies
from app.consents import service as consents
from app.deps import get_limiter, get_session
from app.identity import profile, service
from app.identity.deps import get_current_user, get_user_pending_password
from app.identity.mailer import SmtpMailer
from app.identity.models import User
from app.openapi_errors import problem_responses
from app.telegram import service as telegram

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
    email_verified: bool = False
    # E41-16: вход временным паролем — до смены доступны только `/me` и `/auth/password/initial`
    must_change_password: bool = False

    @classmethod
    def of(cls, u: User) -> UserOut:
        return cls(
            id=u.id,
            email=u.email,
            role=u.role,
            email_verified=u.email_verified_at is not None,
            must_change_password=bool(u.must_change_password),
        )


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


def tokens_out(request: Request, response: Response, issued: service.IssuedTokens) -> AuthOut:
    _set_cookie(request, response, issued.refresh_token)
    return AuthOut(access_token=issued.access_token, user=UserOut.of(issued.user))


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "-")


def _mailer(request: Request) -> SmtpMailer:
    mailer = getattr(request.app.state, "mailer", None)
    return mailer or SmtpMailer(request.app.state.settings)


class VerifyIn(BaseModel):
    code: str = Field(min_length=1, max_length=16)


@router.post(
    "/auth/email/send",
    status_code=204,
    responses=problem_responses(401, 409, 429),
)
async def email_send(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_limiter),
):
    """Повторная отправка кода: не чаще раза в минуту (409 `cooldown`), 5 в час (429)."""
    if user.email_verified_at is not None:
        return Response(status_code=204)
    await limiter.check(f"email_code:{user.id}", 5, 3600)
    await service.send_verification_code(
        session, _mailer(request), request.app.state.settings, user
    )
    return Response(status_code=204)


@router.post("/auth/email/verify", status_code=204, responses=problem_responses(400, 401, 429))
async def email_verify(
    body: VerifyIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Код из письма → `email_verified_at`. Неверный/истёкший — 400."""
    if not await service.verify_code(session, request.app.state.settings, user, body.code):
        # счётчик попыток должен попасть в БД, поэтому не исключение, а обычный ответ
        return problem_response(400, "invalid_code", "Неверный код", "Проверьте код из письма")
    return Response(status_code=204)


@router.post(
    "/auth/register",
    status_code=201,
    response_model=AuthOut,
    responses=problem_responses(400, 409, 422, 429),
)
async def register(
    body: RegisterIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_limiter),
):
    await limiter.check(f"register:ip:{_client_ip(request)}", 10, 60)
    user = await service.register(session, body.email, body.password, body.role)
    settings = request.app.state.settings
    await service.send_verification_code(session, _mailer(request), settings, user)
    issued = await service.issue_tokens(
        session, request.app.state.settings.jwt_secret, user, request.headers.get("user-agent")
    )
    return tokens_out(request, response, issued)


@router.post("/auth/login", response_model=AuthOut, responses=problem_responses(400, 401, 429))
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
    # E43-3: refresh-токен должен быть в БД до того, как клиент получит ответ (см. password_initial)
    await session.commit()
    return tokens_out(request, response, issued)


class MagicIn(BaseModel):
    token: str = Field(min_length=1, max_length=256)


@router.post("/auth/telegram", response_model=AuthOut, responses=problem_responses(400, 401, 429))
async def auth_telegram(
    body: dict[str, Any],
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_limiter),
):
    """Telegram Login Widget → вход или регистрация кандидата (security.md §1)."""
    await limiter.check(f"tglogin:ip:{_client_ip(request)}", 10, 60)
    s = request.app.state.settings
    user = await telegram.login_widget(session, body, s.tg_bot_token)
    issued = await service.issue_tokens(
        session, s.jwt_secret, user, request.headers.get("user-agent")
    )
    return tokens_out(request, response, issued)


@router.post("/auth/magic", response_model=AuthOut, responses=problem_responses(400, 401, 429))
async def auth_magic(
    body: MagicIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_limiter),
):
    """Одноразовая ссылка из бота (Redis GETDEL, 5 мин) → вход."""
    await limiter.check(f"magic:ip:{_client_ip(request)}", 10, 60)
    user = await telegram.consume_magic(session, request.app.state.redis, body.token)
    issued = await service.issue_tokens(
        session,
        request.app.state.settings.jwt_secret,
        user,
        request.headers.get("user-agent"),
    )
    return tokens_out(request, response, issued)


@router.post("/auth/refresh", response_model=AuthOut, responses=problem_responses(401))
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
    return tokens_out(request, response, issued)


@router.post("/auth/logout", status_code=204, responses=problem_responses(401))
async def logout(request: Request, session: AsyncSession = Depends(get_session)):
    _check_origin(request)
    await service.logout(session, request.cookies.get(REFRESH_COOKIE))
    resp = Response(status_code=204)
    _clear_cookie(request, resp)
    return resp


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.post(
    "/auth/password/change", status_code=204, responses=problem_responses(401, 403, 422, 429)
)
async def password_change(
    body: PasswordChangeIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_limiter),
):
    """Смена пароля любой ролью: текущий пароль + новый (≥ 8). Остальные сессии закрываются."""
    await limiter.check(f"password_change:{user.id}", 5, 3600)
    await service.change_password(
        session, user, body.current_password, body.new_password, request.cookies.get(REFRESH_COOKIE)
    )
    return Response(status_code=204)


class PasswordInitialIn(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


@router.post(
    "/auth/password/initial", status_code=204, responses=problem_responses(401, 403, 409, 422, 429)
)
async def password_initial(
    body: PasswordInitialIn,
    user: User = Depends(get_user_pending_password),
    session: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_limiter),
):
    """Первая смена временного пароля HR (E41-16): без текущего пароля, вход уже выполнен им.

    Не требуется — 409 `password_change_not_required`; срок вышел — 403 `temp_password_expired`;
    совпадает с временным — 422 `same_password`; 5 в час (429).
    """
    await limiter.check(f"password_initial:{user.id}", 5, 3600)
    await service.set_initial_password(session, user, body.new_password)
    # E43-3: get_session закрывается ПОСЛЕ отправки ответа (FastAPI ≥ 0.118, scope="request").
    # Фронт сразу после 204 читает /me и входит новым паролем — без явного commit он мог застать
    # старый хеш и must_change_password=true. Фиксируем до ответа.
    await session.commit()
    return Response(status_code=204)


class MeCompany(BaseModel):
    id: UUID
    name: str
    status: str
    role: str
    logo_url: str | None = None  # E41-12


class MeOut(UserOut):
    consents: list[str]
    avatar_url: str | None = None  # E41-12: своё фото; у кандидата — со строкой доступа
    telegram_linked: bool = False
    company: MeCompany | None = None


@router.get("/me", response_model=MeOut, responses=problem_responses(401))
async def me(
    request: Request,
    user: User = Depends(get_user_pending_password),
    session: AsyncSession = Depends(get_session),
):
    """consents — действующие типы; company — E6-1; candidate — E3-1."""
    found = await companies.my_company(session, user.id) if user.role == "employer" else None
    if user.role == "candidate":
        cand = await candidates.get(session, user.id)
        avatar = (
            candidates.avatar_url(cand, request.app.state.settings.jwt_secret) if cand else None
        )
    else:
        row = await profile.get(session, user.id)
        avatar = profile.avatar_url(user.id, row.avatar_key) if row else None
    return MeOut(
        **UserOut.of(user).model_dump(),
        avatar_url=avatar,
        consents=sorted(await consents.active(session, user.id)),
        telegram_linked=await telegram.is_linked(session, user.id),
        company=MeCompany(
            id=found[0].id,
            name=found[0].name,
            status=found[0].status,
            role=found[1].role,
            logo_url=companies.logo_url(found[0]),
        )
        if found
        else None,
    )
