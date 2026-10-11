"""`/me/telegram/link` и internal API для бота."""

from __future__ import annotations

import hmac
from datetime import timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile
from fsp_contracts.enums import (
    ConsentType,
    DeclineReason,
    OfferStatus,
    SearchStatus,
    WorkFormat,
)
from fsp_platform.app import ProblemError
from fsp_platform.jwt import encode_token
from fsp_platform.ratelimit import RateLimiter
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import service as assessment
from app.candidates import service as candidates
from app.consents import service as consents
from app.deps import get_limiter, get_redis, get_session, get_storage
from app.fsp import service as fsp_service
from app.fsp.client import ConnectorClient
from app.fsp.router import get_connector
from app.graph import service as graph
from app.identity.deps import get_current_user
from app.identity.models import User
from app.notifications.handlers import offer_card_data
from app.offers import service as offers
from app.openapi_errors import problem_responses
from app.resumes import service as resumes
from app.taxonomy import service as taxonomy
from app.telegram import service

BOT_USER_TOKEN_TTL = timedelta(minutes=5)

router = APIRouter(tags=["telegram"])
internal = APIRouter(prefix="/internal", tags=["internal"])


async def require_bot(request: Request, authorization: str | None = Header(default=None)) -> None:
    """`Authorization: Service <token>`; пустой токен в настройках = закрыто."""
    expected = request.app.state.settings.service_token_bot
    scheme, _, token = (authorization or "").partition(" ")
    if not (expected and scheme == "Service" and hmac.compare_digest(token, expected)):
        raise ProblemError(401, "unauthorized", "Нужен сервисный токен")


class DeepLinkOut(BaseModel):
    deep_link: str


@router.post("/me/telegram/link", response_model=DeepLinkOut, responses=problem_responses(401, 429))
async def my_link(
    request: Request,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
    limiter: RateLimiter = Depends(get_limiter),
):
    await limiter.check(f"tglink:user:{user.id}", 10, 60)
    link = await service.create_link_deep_link(
        redis, request.app.state.settings.tg_bot_username, user.id
    )
    return DeepLinkOut(deep_link=link)


class StartIn(BaseModel):
    tg_user_id: int
    chat_id: int
    username: str | None = Field(default=None, max_length=64)
    start_param: str | None = Field(default=None, max_length=256)


class StartOut(BaseModel):
    user_id: UUID
    role: str
    missing_consents: list[str]
    # True, если Telegram связан с аккаунтом сайта (email/пароль), а не только заготовкой бота
    linked: bool


@internal.post("/tg/start", response_model=StartOut, dependencies=[Depends(require_bot)])
async def tg_start(body: StartIn, session: AsyncSession = Depends(get_session)):
    # start_param (`link_<token>`, `ref_<source>`) обрабатывает бот: link — отдельным вызовом
    user, _ = await service.ensure_user(session, body.tg_user_id, body.chat_id, body.username)
    return StartOut(
        user_id=user.id,
        role=user.role,
        missing_consents=await service.missing_consents(session, user.id),
        linked=user.email is not None,
    )


class ConsentsIn(BaseModel):
    tg_user_id: int
    types: list[str] = Field(max_length=10)


async def _user_by_tg(session: AsyncSession, tg_user_id: int) -> User:
    acc = await service.account_by_tg(session, tg_user_id)
    user = await session.get(User, acc.user_id) if acc else None
    if user is None or not user.is_active or user.deleted_at is not None:
        raise ProblemError(404, "telegram_unknown", "Аккаунт Telegram не найден")
    return user


@internal.post("/tg/consents", status_code=204, dependencies=[Depends(require_bot)])
async def tg_consents(body: ConsentsIn, session: AsyncSession = Depends(get_session)):
    user = await _user_by_tg(session, body.tg_user_id)
    await service.grant_consents(session, user.id, body.types)


class LinkIn(BaseModel):
    tg_user_id: int
    token: str = Field(min_length=1, max_length=256)
    chat_id: int | None = None  # для нового аккаунта; по умолчанию = tg_user_id
    username: str | None = Field(default=None, max_length=64)


class LinkOut(BaseModel):
    user_id: UUID
    linked: bool = True


@internal.post("/tg/link", response_model=LinkOut, dependencies=[Depends(require_bot)])
async def tg_link(
    body: LinkIn,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    limiter: RateLimiter = Depends(get_limiter),
):
    await limiter.check(f"tglink:tg:{body.tg_user_id}", 10, 60)
    acc = await service.link_by_token(
        session, redis, body.tg_user_id, body.token, chat_id=body.chat_id, username=body.username
    )
    return LinkOut(user_id=acc.user_id)


class TgLinkedOut(BaseModel):
    linked: bool


@internal.get("/tg/linked", response_model=TgLinkedOut, dependencies=[Depends(require_bot)])
async def tg_linked(tg_user_id: int, session: AsyncSession = Depends(get_session)):
    """Привязан ли Telegram к аккаунту сайта. Ничего не создаёт (бот не регистрирует)."""
    return TgLinkedOut(linked=await service.is_linked_tg(session, tg_user_id))


class MagicLinkIn(BaseModel):
    tg_user_id: int
    redirect: str = Field(default="/", max_length=512)


class MagicLinkOut(BaseModel):
    url: str


@internal.post("/auth/magic-link", response_model=MagicLinkOut, dependencies=[Depends(require_bot)])
async def magic_link(
    body: MagicLinkIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    limiter: RateLimiter = Depends(get_limiter),
):
    await limiter.check(f"magiclink:tg:{body.tg_user_id}", 5, 60)
    url = await service.create_magic_link(
        session, redis, request.app.state.settings.web_base_url, body.tg_user_id, body.redirect
    )
    return MagicLinkOut(url=url)


class UserTokenIn(BaseModel):
    tg_user_id: int


class UserTokenOut(BaseModel):
    access_token: str
    expires_in: int


@internal.post("/tg/token", response_model=UserTokenOut, dependencies=[Depends(require_bot)])
async def tg_user_token(
    body: UserTokenIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_limiter),
):
    """Короткий access-токен кандидата: бот ходит с ним в `/assessment/*`.

    Тот же JWT, что и после входа, но живёт `BOT_USER_TOKEN_TTL` (5 минут), refresh не выдаётся.
    """
    await limiter.check(f"tgtoken:tg:{body.tg_user_id}", 120, 60)
    user = await _candidate_by_tg(session, body.tg_user_id)
    token = encode_token(
        request.app.state.settings.jwt_secret,
        str(user.id),
        user.role,
        ttl=BOT_USER_TOKEN_TTL,
        jti=uuid4().hex,
    )
    return UserTokenOut(access_token=token, expires_in=int(BOT_USER_TOKEN_TTL.total_seconds()))


# --- Резюме и профиль из бота --------------------------------------------------

PROFILE_SKILLS = 6
FSP_LINES = 3
FSP_ACHIEVEMENTS = 6


async def _candidate_by_tg(session: AsyncSession, tg_user_id: int) -> User:
    user = await _user_by_tg(session, tg_user_id)
    if user.role != "candidate":
        raise ProblemError(403, "forbidden", "Действие доступно кандидату")
    return user


class ResumeAcceptedOut(BaseModel):
    resume_id: UUID
    job_id: UUID


@internal.post(
    "/tg/resumes",
    status_code=202,
    response_model=ResumeAcceptedOut,
    dependencies=[Depends(require_bot)],
)
async def tg_resume_upload(
    request: Request,
    file: Annotated[UploadFile, File()],
    tg_user_id: Annotated[int, Form()],
    session: AsyncSession = Depends(get_session),
    storage=Depends(get_storage),
    limiter: RateLimiter = Depends(get_limiter),
):
    """Те же проверки, что у сайта: сигнатура PDF/DOCX, до 10 МБ, 10 в сутки, согласие ПДн."""
    user = await _candidate_by_tg(session, tg_user_id)
    if not await consents.has_consent(session, user.id, ConsentType.pd_processing):
        raise ProblemError(
            403, "consent_required", "Нужно согласие", "Выдайте согласие pd_processing"
        )
    await limiter.check(f"resume:{user.id}", resumes.UPLOAD_LIMIT, resumes.UPLOAD_WINDOW)
    data = await file.read(resumes.MAX_BYTES + 1)
    if not getattr(request.app.state, "bucket_ready", False):
        await storage.ensure_bucket()
        request.app.state.bucket_ready = True
    await candidates.get_or_create(session, user.id, request.app.state.settings.pseudo_id_secret)
    resume, job_id = await resumes.upload(session, storage, user.id, data)
    return ResumeAcceptedOut(resume_id=resume.id, job_id=job_id)


class TgResumeOut(BaseModel):
    status: str
    error: str | None = None
    experience_months: int | None = None
    skills: list[str] = []
    unknown_skills: int = 0


def _resume_out(resume) -> TgResumeOut:
    out = TgResumeOut(status=resume.status, error=resume.error)
    if resume.parsed:
        parsed = resumes.ParsedResume.model_validate(resume.parsed)
        out.experience_months = parsed.total_experience_months
        out.skills = [s.raw for s in parsed.skills if s.slug][:12]
        out.unknown_skills = len(parsed.unknown_skills)
    return out


@internal.get(
    "/tg/resumes/{resume_id}", response_model=TgResumeOut, dependencies=[Depends(require_bot)]
)
async def tg_resume_status(
    resume_id: UUID, tg_user_id: int, session: AsyncSession = Depends(get_session)
):
    user = await _candidate_by_tg(session, tg_user_id)
    return _resume_out(await resumes.get_owned(session, user.id, resume_id))


class TgConfirmIn(BaseModel):
    tg_user_id: int


@internal.post(
    "/tg/resumes/{resume_id}/confirm",
    response_model=TgResumeOut,
    dependencies=[Depends(require_bot)],
)
async def tg_resume_confirm(
    resume_id: UUID, body: TgConfirmIn, session: AsyncSession = Depends(get_session)
):
    """Подтверждение без правок; правки — на сайте."""
    user = await _candidate_by_tg(session, body.tg_user_id)
    resume = await resumes.get_owned(session, user.id, resume_id)
    await resumes.confirm(session, resume, resumes.ParsedResumeEdits())
    return _resume_out(resume)


class TgSkill(BaseModel):
    name: str
    level: int
    claimed_only: bool


class TgProfileOut(BaseModel):
    primary_role: str | None
    grade: str | None
    grade_preliminary: bool
    skills: list[TgSkill]
    fsp: list[str]


@internal.get("/tg/profile", response_model=TgProfileOut, dependencies=[Depends(require_bot)])
async def tg_profile(
    request: Request, tg_user_id: int, session: AsyncSession = Depends(get_session)
):
    """Краткий профиль для сообщения: свой, поэтому названия навыков и ФСП-результаты можно."""
    user = await _candidate_by_tg(session, tg_user_id)
    cand = await candidates.get_or_create(
        session, user.id, request.app.state.settings.pseudo_id_secret
    )
    edges = (await graph.all_skills_of(session, [user.id])).get(user.id, [])
    edges = sorted(edges, key=lambda s: (s.claimed_only, -s.confidence, str(s.skill_id)))
    top = edges[:PROFILE_SKILLS]
    names = await taxonomy.skill_names(session, [e.skill_id for e in top])
    slugs = await taxonomy.skill_slugs(session, [e.skill_id for e in top])
    skills = [
        TgSkill(
            name=names.get(e.skill_id) or slugs.get(e.skill_id, ""),
            level=e.level,
            claimed_only=e.claimed_only,
        )
        for e in top
        if e.skill_id in slugs
    ]
    return TgProfileOut(
        primary_role=cand.primary_role,
        grade=cand.grade,
        grade_preliminary=cand.grade_confidence is None or cand.grade_confidence < 0.5,
        skills=skills,
        fsp=(await _fsp_labels(session, user.id))[:FSP_LINES],
    )


# --- ФСП, категория, статус и настройки из бота ----------------------------


async def _fsp_labels(session: AsyncSession, user_id: UUID) -> list[str]:
    labels: dict[UUID, str] = {}
    for ev in await graph.evidence_of(session, [user_id], source="fsp"):
        label = (ev.details or {}).get("label")
        if ev.fact_type == "fsp_result" and isinstance(label, str):
            labels.setdefault(ev.fact_id, label)
    return list(labels.values())


async def _require_pd(session: AsyncSession, user_id: UUID) -> None:
    if not await consents.has_consent(session, user_id, ConsentType.pd_processing):
        raise ProblemError(
            403, "consent_required", "Нужно согласие", "Выдайте согласие pd_processing"
        )


class TgFspOut(BaseModel):
    linked: bool
    verified: bool
    participant_id: str | None = None
    achievements: list[str] = []
    teams: list[str] = []


@internal.get("/tg/fsp", response_model=TgFspOut, dependencies=[Depends(require_bot)])
async def tg_fsp(tg_user_id: int, session: AsyncSession = Depends(get_session)):
    user = await _candidate_by_tg(session, tg_user_id)
    link = await fsp_service.link_status(session, user.id)
    teams = [t["name"] for t in await fsp_service.teams_of(session, user.id) if t["name"]]
    labels = (await _fsp_labels(session, user.id))[:FSP_ACHIEVEMENTS]
    return TgFspOut(**link, achievements=labels, teams=teams)


class TgFspLinkIn(BaseModel):
    tg_user_id: int
    participant_id: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=254)


class TgFspLinkOut(BaseModel):
    method: str
    masked_contact: str | None = None


@internal.post("/tg/fsp/link", response_model=TgFspLinkOut, dependencies=[Depends(require_bot)])
async def tg_fsp_link(
    body: TgFspLinkIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_limiter),
    connector: ConnectorClient = Depends(get_connector),
):
    """Те же правила, что у `/candidates/me/fsp/link` (10 попыток / 10 мин, нужно согласие ПДн)."""
    user = await _candidate_by_tg(session, body.tg_user_id)
    await _require_pd(session, user.id)
    await limiter.check(f"fsplink:{user.id}", 10, 600)
    if not (body.participant_id or body.email):
        raise ProblemError(422, "validation_error", "Укажите ID участника или email")
    await candidates.get_or_create(session, user.id, request.app.state.settings.pseudo_id_secret)
    data = await connector.link(
        user.id, participant_id=body.participant_id, email=body.email, manual=False
    )
    return TgFspLinkOut(method=data["method"], masked_contact=data.get("masked_contact"))


class TgFspVerifyIn(BaseModel):
    tg_user_id: int
    code: str = Field(min_length=1, max_length=16)


@internal.post("/tg/fsp/verify", dependencies=[Depends(require_bot)])
async def tg_fsp_verify(
    body: TgFspVerifyIn,
    session: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_limiter),
    connector: ConnectorClient = Depends(get_connector),
):
    user = await _candidate_by_tg(session, body.tg_user_id)
    await _require_pd(session, user.id)
    await limiter.check(f"fspverify:{user.id}", 20, 600)
    data = await connector.verify(user.id, body.code)
    return {"verified": bool(data.get("verified"))}


@internal.post("/tg/fsp/sync", status_code=202, dependencies=[Depends(require_bot)])
async def tg_fsp_sync(
    body: TgConfirmIn,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
):
    user = await _candidate_by_tg(session, body.tg_user_id)
    await _require_pd(session, user.id)
    await fsp_service.request_sync(session, redis, user.id)
    return {"status": "accepted"}


class TgCategoryItem(BaseModel):
    profession: str
    title: str
    grade: str
    needs_confirmation: bool
    valid_until: str


class TgClaim(BaseModel):
    profession: str
    title: str
    status: str
    declared_grade: str | None
    confirmed_grade: str | None


class TgCategoryOut(BaseModel):
    categories: list[TgCategoryItem]
    claims: list[TgClaim]


@internal.get("/tg/category", response_model=TgCategoryOut, dependencies=[Depends(require_bot)])
async def tg_category(tg_user_id: int, session: AsyncSession = Depends(get_session)):
    """Подтверждённые категории (грейды теста) и «заявлено vs подтверждено»."""
    user = await _candidate_by_tg(session, tg_user_id)
    profs = await taxonomy.list_professions(session, include_hidden=True)  # грейды остаются
    titles = {p.slug: p.title for p in profs}
    grades = await assessment.get_grades(session, user.id)
    claims = await assessment.claimed_vs_confirmed(session, user.id)
    return TgCategoryOut(
        categories=[
            TgCategoryItem(
                profession=g.profession,
                title=titles.get(g.profession, g.profession),
                grade=g.grade.value,
                needs_confirmation=g.needs_confirmation,
                valid_until=g.valid_until.isoformat(),
            )
            for g in grades
        ],
        claims=[
            TgClaim(
                profession=c.profession,
                title=titles.get(c.profession, c.profession),
                status=c.status,
                declared_grade=c.declared_grade.value if c.declared_grade else None,
                confirmed_grade=c.confirmed_grade.value if c.confirmed_grade else None,
            )
            for c in claims
        ],
    )


class TgSettingsOut(BaseModel):
    salary_min: int | None
    formats: list[str]
    search_status: str


async def _settings_out(request: Request, session: AsyncSession, user: User) -> TgSettingsOut:
    cand = await candidates.get_or_create(
        session, user.id, request.app.state.settings.pseudo_id_secret
    )
    return TgSettingsOut(
        salary_min=cand.salary_min,
        formats=list(cand.formats or []),
        search_status=candidates.effective_status(cand),
    )


@internal.get("/tg/settings", response_model=TgSettingsOut, dependencies=[Depends(require_bot)])
async def tg_settings(
    request: Request, tg_user_id: int, session: AsyncSession = Depends(get_session)
):
    user = await _candidate_by_tg(session, tg_user_id)
    return await _settings_out(request, session, user)


class TgSettingsIn(BaseModel):
    tg_user_id: int
    salary_min: int | None = Field(default=None, ge=0, le=100_000_000)
    formats: list[WorkFormat] | None = None


@internal.patch("/tg/settings", response_model=TgSettingsOut, dependencies=[Depends(require_bot)])
async def tg_settings_update(
    body: TgSettingsIn, request: Request, session: AsyncSession = Depends(get_session)
):
    """Только минимальная зарплата и форматы; остальное — на сайте. `salary_min: null` очищает."""
    user = await _candidate_by_tg(session, body.tg_user_id)
    await _require_pd(session, user.id)
    cand = await candidates.get_or_create(
        session, user.id, request.app.state.settings.pseudo_id_secret
    )
    changes = body.model_dump(exclude_unset=True, exclude={"tg_user_id"})
    await candidates.update_preferences(session, cand, changes)
    return await _settings_out(request, session, user)


class TgStatusIn(BaseModel):
    tg_user_id: int
    status: SearchStatus


@internal.patch("/tg/status", response_model=TgSettingsOut, dependencies=[Depends(require_bot)])
async def tg_status(
    body: TgStatusIn, request: Request, session: AsyncSession = Depends(get_session)
):
    """Статус поиска: `active` на 7 дней, `open`, `dnd` (как `PATCH /candidates/me/preferences`)."""
    user = await _candidate_by_tg(session, body.tg_user_id)
    await _require_pd(session, user.id)
    cand = await candidates.get_or_create(
        session, user.id, request.app.state.settings.pseudo_id_secret
    )
    await candidates.update_preferences(session, cand, {"search_status": body.status.value})
    return await _settings_out(request, session, user)


# --- Офферы из бота --------------------------------------------------------------

ACTIVE_OFFERS = (
    OfferStatus.sent.value,
    OfferStatus.viewed.value,
    OfferStatus.accepted.value,
    OfferStatus.interview.value,
)
TG_OFFERS_LIMIT = 10


class TgOfferOut(BaseModel):
    """Данные карточки оффера: те же поля, что у `notify.telegram` `offer_new`, плюс статус."""

    offer_id: str
    status: str
    company_name: str | None
    company_responsibility: float | None
    vacancy_title: str | None
    formats: list[str]
    employment_type: str | None
    salary_from: int
    salary_to: int
    salary_basis: str = "gross"
    message: str | None
    match_score: float | None
    explanation: list[dict]
    below_candidate_min: bool
    expires_at: str


async def _offer_out(session: AsyncSession, offer) -> TgOfferOut:
    data = await offer_card_data(session, offer)
    return TgOfferOut(status=offer.status, **data)


@internal.get("/tg/offers", response_model=list[TgOfferOut], dependencies=[Depends(require_bot)])
async def tg_offers(tg_user_id: int, session: AsyncSession = Depends(get_session)):
    """Активные офферы кандидата (меню «Офферы»): новые первыми, не больше 10."""
    user = await _candidate_by_tg(session, tg_user_id)
    rows = [  # свои отклики в меню «Офферы» не показываем
        o
        for o in await offers.list_for_candidate(session, user.id, initiator="employer")
        if o.status in ACTIVE_OFFERS
    ]
    return [await _offer_out(session, o) for o in rows[:TG_OFFERS_LIMIT]]


@internal.post(
    "/tg/offers/{offer_id}/view", response_model=TgOfferOut, dependencies=[Depends(require_bot)]
)
async def tg_offer_view(
    offer_id: UUID, body: TgConfirmIn, session: AsyncSession = Depends(get_session)
):
    """«Подробнее»: первое открытие переводит `sent → viewed`."""
    user = await _candidate_by_tg(session, body.tg_user_id)
    offer = await offers.get_for_candidate(session, user.id, offer_id, lock=True)
    await offers.mark_viewed(session, offer)
    return await _offer_out(session, offer)


@internal.post(
    "/tg/offers/{offer_id}/accept", response_model=TgOfferOut, dependencies=[Depends(require_bot)]
)
async def tg_offer_accept(
    offer_id: UUID, body: TgConfirmIn, session: AsyncSession = Depends(get_session)
):
    user = await _candidate_by_tg(session, body.tg_user_id)
    offer = await offers.get_for_candidate(session, user.id, offer_id, lock=True)
    await offers.accept(session, offer)
    return await _offer_out(session, offer)


class TgDeclineIn(BaseModel):
    tg_user_id: int
    reason: DeclineReason
    comment: str | None = Field(default=None, max_length=1000)


@internal.post(
    "/tg/offers/{offer_id}/decline", response_model=TgOfferOut, dependencies=[Depends(require_bot)]
)
async def tg_offer_decline(
    offer_id: UUID, body: TgDeclineIn, session: AsyncSession = Depends(get_session)
):
    user = await _candidate_by_tg(session, body.tg_user_id)
    offer = await offers.get_for_candidate(session, user.id, offer_id, lock=True)
    await offers.decline(session, offer, body.reason, body.comment)
    return await _offer_out(session, offer)
