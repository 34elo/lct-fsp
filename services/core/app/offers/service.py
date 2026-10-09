"""Офферы: создание с проверками, лимиты, идемпотентность, автомат статусов, журнал.

Правила (api.md §2.5, data-model.md §3.8, flows.md F8, security.md §2):
- вилка обязательна; `salary_to >= salary_from`; слишком широкая вилка — только предупреждение;
- создавать может участник `verified` компании по своей опубликованной вакансии;
- лимиты считаем по БД за скользящие 24 ч: компания — `offer_company_per_day`,
  кандидат — `offer_candidate_per_day` (scoring.yaml `limits`);
- `Idempotency-Key` уникален в паре с компанией; повтор того же запроса возвращает исходный
  оффер, тот же ключ с другим запросом — 409;
- чужой оффер → 404; каждый переход пишет `offer_events` и `offer.*` в outbox в одной транзакции;
- приглашение без вакансии (ADR-022): нужен `title`; второе открытое приглашение без вакансии
  тому же кандидату от той же компании — 409; события `offer.*` идут со schema_version 2;
- отклик (E20-3, `initiator = candidate`): `apply`, вилка из вакансии, контакты раскрыты сразу,
  ответ компании — `APPLICATION_TRANSITIONS`, повтор → 409 `already_applied`;
- интерес (E33-1, ADR-026): `interest → interest_opened → sent` в той же строке; вилка
  обязательна, сообщение ≤ 300, срок `interest_validity_days`; лимит —
  `interest_company_per_week` за скользящие 7 дней; повтор отметки возвращает открытый интерес;
  события `offer.interest.*` (schema_version 3), после приглашения — обычные `offer.*`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from fsp_contracts import new_envelope
from fsp_contracts.enums import CompanyStatus, DeclineReason, OfferStatus
from fsp_contracts.events import OfferEvent as OfferEventPayload
from fsp_contracts.hiring import (
    INTEREST_SCHEMA_VERSION,
    OFFER_SCHEMA_VERSION,
    ContactMethod,
    OfferInitiator,
    OfferInterestEvent,
    SalaryBasis,
)
from fsp_platform.app import ProblemError
from fsp_platform.outbox import add_to_outbox
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.models import Candidate
from app.companies.models import Company
from app.identity import service as identity
from app.matching import service as matching
from app.matching.scoring import DEFAULT_SCORING_PATH
from app.offers.models import Complaint, ContactReveal, Offer, OfferEvent, OfferMessage
from app.vacancies.models import Vacancy
from app.vacancies.service import VacancyStatus

S = OfferStatus
OPEN = (S.sent.value, S.viewed.value)  # ждут ответа кандидата
INTEREST_OPEN = (S.interest.value, S.interest_opened.value)  # интерес до приглашения (ADR-026)
EXPIRABLE = OPEN + INTEREST_OPEN
WINDOW = timedelta(hours=24)
INTEREST_WINDOW = timedelta(days=7)
INTEREST_MESSAGE_MAX = 300

# (из, в) -> кто может: candidate | company | system
TRANSITIONS: dict[tuple[OfferStatus, OfferStatus], str] = {
    (S.sent, S.viewed): "candidate",
    (S.sent, S.accepted): "candidate",
    (S.viewed, S.accepted): "candidate",
    (S.sent, S.declined): "candidate",
    (S.viewed, S.declined): "candidate",
    (S.sent, S.expired): "system",
    (S.viewed, S.expired): "system",
    (S.sent, S.withdrawn): "company",
    (S.viewed, S.withdrawn): "company",
    (S.accepted, S.interview): "company",
    (S.accepted, S.not_hired): "company",
    (S.interview, S.hired): "company",
    (S.interview, S.not_hired): "company",
}
# отклик кандидата (ADR-022, `initiator = candidate`): ответчик - компания, принятие не нужно
# (контакты кандидата раскрываются сразу при отклике), отозвать может сам кандидат
APPLICATION_TRANSITIONS: dict[tuple[OfferStatus, OfferStatus], str] = {
    (S.sent, S.viewed): "company",
    (S.sent, S.interview): "company",
    (S.viewed, S.interview): "company",
    (S.sent, S.not_hired): "company",
    (S.viewed, S.not_hired): "company",
    (S.sent, S.withdrawn): "candidate",
    (S.viewed, S.withdrawn): "candidate",
    (S.sent, S.expired): "system",
    (S.viewed, S.expired): "system",
    (S.interview, S.hired): "company",
    (S.interview, S.not_hired): "company",
}
# интерес работодателя до приглашения (ADR-026): кандидат открывает или отклоняет, компания
# после открытия отправляет приглашение (`interest_opened → sent`) или отзывает интерес
INTEREST_TRANSITIONS: dict[tuple[OfferStatus, OfferStatus], str] = {
    (S.interest, S.interest_opened): "candidate",
    (S.interest, S.declined): "candidate",
    (S.interest_opened, S.declined): "candidate",
    (S.interest_opened, S.sent): "company",
    (S.interest, S.withdrawn): "company",
    (S.interest_opened, S.withdrawn): "company",
    (S.interest, S.expired): "system",
    (S.interest_opened, S.expired): "system",
}
_INTEREST_EVENT = {
    S.interest: "offer.interest.sent", S.interest_opened: "offer.interest.opened",
    S.declined: "offer.interest.declined", S.expired: "offer.interest.expired",
    S.withdrawn: "offer.interest.withdrawn",
}  # fmt: skip
# статусы, которые работодатель выставляет вручную (`POST /offers/{id}/status`)
COMPANY_SET = (S.interview, S.hired, S.not_hired)
_EVENT = {
    S.sent: "offer.sent", S.viewed: "offer.viewed", S.accepted: "offer.accepted",
    S.declined: "offer.declined", S.expired: "offer.expired", S.withdrawn: "offer.withdrawn",
}  # fmt: skip


@dataclass(frozen=True, slots=True)
class OfferLimits:
    company_per_day: int = 20
    candidate_per_day: int = 10
    validity_days: int = 7
    applications_per_day: int = 20
    interest_company_per_week: int = 30
    interest_validity_days: int = 7

    @classmethod
    def load(cls, path: Path | str | None = None) -> OfferLimits:
        data = yaml.safe_load(Path(path or DEFAULT_SCORING_PATH).read_text(encoding="utf-8"))
        lim = (data or {}).get("limits", {})
        base = cls()
        return cls(
            company_per_day=int(lim.get("offer_company_per_day", base.company_per_day)),
            candidate_per_day=int(lim.get("offer_candidate_per_day", base.candidate_per_day)),
            validity_days=int(lim.get("offer_validity_days", base.validity_days)),
            applications_per_day=int(
                lim.get("application_candidate_per_day", base.applications_per_day)
            ),
            interest_company_per_week=int(
                lim.get("interest_company_per_week", base.interest_company_per_week)
            ),
            interest_validity_days=int(
                lim.get("interest_validity_days", base.interest_validity_days)
            ),
        )


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def not_found() -> ProblemError:
    return ProblemError(404, "offer_not_found", "Оффер не найден")


def validate_range(salary_from: int | None, salary_to: int | None) -> tuple[int, int]:
    """Вилка обязательна: обе границы заданы и положительны."""
    if not salary_from or not salary_to or salary_from <= 0 or salary_to <= 0:
        raise ProblemError(
            422, "salary_range_required", "Укажите вилку зарплаты",
            errors=[{"field": "salary_from", "message": "вилка обязательна"}],
        )  # fmt: skip
    if salary_to < salary_from:
        raise ProblemError(
            422, "invalid_salary_range", "salary_to не может быть меньше salary_from"
        )
    return salary_from, salary_to


async def _count_since(
    session: AsyncSession, column: Any, value: uuid.UUID, since: datetime, *, interests: bool = True
):
    q = select(func.count(), func.min(Offer.created_at)).where(
        column == value, Offer.created_at >= since, Offer.initiator == OfferInitiator.employer.value
    )
    if not interests:  # суточный лимит офферов компании: интересы считает недельный лимит
        q = q.where(Offer.interest_at.is_(None))
    count, oldest = (await session.execute(q)).one()
    return count, oldest


async def open_counts(
    session: AsyncSession, candidate_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Сколько офферов кандидат получил и ещё не ответил (sent/viewed, срок не вышел)."""
    if not candidate_ids:
        return {}
    q = (
        select(Offer.candidate_id, func.count())
        .where(
            Offer.candidate_id.in_(candidate_ids),
            Offer.initiator == OfferInitiator.employer.value,
            Offer.status.in_(OPEN),
            Offer.expires_at > datetime.now(UTC),
        )
        .group_by(Offer.candidate_id)
    )
    return {cid: n for cid, n in (await session.execute(q)).all()}


async def first_invitations(
    session: AsyncSession, *, real_only: bool = False
) -> tuple[int, dict[uuid.UUID, datetime]]:
    """Приглашения компаний: сколько всего и `candidate_id → время первого` (счётчики лендинга).

    `real_only` — без демо-приглашений (E40-1).
    """
    employer = Offer.initiator == OfferInitiator.employer.value
    if real_only:
        employer = employer & Offer.is_demo.is_(False)
    total = await session.scalar(select(func.count()).select_from(Offer).where(employer))
    rows = await session.execute(
        select(Offer.candidate_id, func.min(Offer.created_at))
        .where(employer, Offer.candidate_id.is_not(None))
        .group_by(Offer.candidate_id)
    )
    return int(total or 0), {cid: at for cid, at in rows}


def _retry_after(oldest: datetime | None, now: datetime) -> dict[str, str]:
    if oldest is None:
        return {"Retry-After": str(int(WINDOW.total_seconds()))}
    wait = int((_aware(oldest) + WINDOW - now).total_seconds()) + 1
    return {"Retry-After": str(max(1, wait))}


def _in_interest_phase(offer: Offer) -> bool:
    """Интерес, по которому ещё не отправлено приглашение (ADR-026)."""
    return offer.interest_at is not None and offer.invited_at is None


async def _emit(session: AsyncSession, offer: Offer, to: OfferStatus, *, prev, actor, **extra):
    if _in_interest_phase(offer):
        interest = OfferInterestEvent(
            offer_id=offer.id, candidate_id=offer.candidate_id, company_id=offer.company_id,
            vacancy_id=offer.vacancy_id, status=to, prev_status=prev, actor=actor,
            decline_reason=extra.get("decline_reason"), salary_from=offer.salary_from,
            salary_to=offer.salary_to,
        )  # fmt: skip
        env = new_envelope(
            _INTEREST_EVENT[to], "core", interest, schema_version=INTEREST_SCHEMA_VERSION
        )
        await add_to_outbox(session, env, offer.id)
        return
    name = _EVENT.get(to, "offer.status_changed")
    payload = OfferEventPayload(
        offer_id=offer.id, candidate_id=offer.candidate_id, company_id=offer.company_id,
        vacancy_id=offer.vacancy_id, status=to, prev_status=prev, actor=actor,
        initiator=OfferInitiator(offer.initiator), **extra,
    )  # fmt: skip
    await add_to_outbox(session, _envelope(name, payload), offer.id)


def _envelope(name: str, payload: OfferEventPayload):
    return new_envelope(name, "core", payload, schema_version=OFFER_SCHEMA_VERSION)


async def _log(
    session: AsyncSession, offer: Offer, prev: OfferStatus | None, to: OfferStatus, actor: str,
    payload: dict | None = None,
) -> None:  # fmt: skip
    session.add(
        OfferEvent(
            offer_id=offer.id, from_status=prev.value if prev else None, to_status=to.value,
            actor=actor, payload=payload,
        )
    )  # fmt: skip
    await session.flush()


async def find_by_key(session: AsyncSession, company_id: uuid.UUID, key: str) -> Offer | None:
    return await session.scalar(
        select(Offer).where(Offer.company_id == company_id, Offer.idempotency_key == key)
    )


async def create(
    session: AsyncSession,
    *,
    company: Company,
    user_id: uuid.UUID,
    vacancy: Vacancy | None,
    candidate: Candidate,
    salary_from: int | None,
    salary_to: int | None,
    message: str | None,
    idempotency_key: str,
    limits: OfferLimits,
    title: str | None = None,
    description: str | None = None,
    contact_method: ContactMethod | None = None,
    salary_basis: SalaryBasis | None = None,
    team_offer_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> tuple[Offer, bool]:
    """Новый оффер (приглашение работодателя, ADR-022: вакансия необязательна).

    Возвращает `(оффер, replay)`: `replay=True` — это повтор по тому же ключу.
    """
    now = now or datetime.now(UTC)
    existing = await find_by_key(session, company.id, idempotency_key)
    if existing is not None:
        return _replay(existing, vacancy, candidate), True

    if company.status != CompanyStatus.verified.value:
        raise ProblemError(403, "company_not_verified", "Компания не прошла верификацию")
    title = (title or "").strip() or None
    if vacancy is None and title is None:
        raise ProblemError(
            422, "title_required", "Укажите название приглашения",
            errors=[{"field": "title", "message": "без вакансии название обязательно"}],
        )  # fmt: skip
    if vacancy is not None and vacancy.status != VacancyStatus.published.value:
        raise ProblemError(409, "vacancy_not_published", "Вакансия не опубликована")
    lo, hi = validate_range(salary_from, salary_to)

    if vacancy is not None:
        dup_q = select(Offer.id).where(
            Offer.vacancy_id == vacancy.id, Offer.candidate_id == candidate.user_id
        )
    else:  # без вакансии: одно открытое приглашение от компании кандидату
        dup_q = select(Offer.id).where(
            Offer.vacancy_id.is_(None), Offer.company_id == company.id,
            Offer.candidate_id == candidate.user_id, Offer.status.in_(EXPIRABLE),
            Offer.expires_at > now,
        )  # fmt: skip
    if await session.scalar(dup_q.limit(1)) is not None:
        raise ProblemError(409, "offer_exists", "Оффер этому кандидату по вакансии уже отправлен")

    since = now - WINDOW
    n, oldest = await _count_since(session, Offer.company_id, company.id, since, interests=False)
    if n >= limits.company_per_day:
        raise ProblemError(
            429, "offer_limit_exceeded", "Лимит офферов на сутки исчерпан",
            headers=_retry_after(oldest, now),
        )  # fmt: skip
    n, oldest = await _count_since(session, Offer.candidate_id, candidate.user_id, since)
    if n >= limits.candidate_per_day:
        raise ProblemError(
            429, "candidate_offer_limit_exceeded", "Кандидат получил слишком много офферов",
            headers=_retry_after(oldest, now),
        )  # fmt: skip

    snapshot = await matching.snapshot(session, vacancy.id, candidate.user_id) if vacancy else None
    offer = Offer(
        id=uuid.uuid4(), vacancy_id=vacancy.id if vacancy else None,
        candidate_id=candidate.user_id, company_id=company.id, created_by=user_id,
        salary_from=lo, salary_to=hi, message=(message or "").strip() or None,
        salary_basis=(salary_basis.value if salary_basis else None)
        or (vacancy.salary_basis if vacancy else None) or SalaryBasis.gross.value,
        title=title, description=(description or "").strip() or None,
        contact_method=contact_method.value if contact_method else None,
        initiator=OfferInitiator.employer.value, status=S.sent.value,
        awaiting_reply_from="candidate", match_snapshot=snapshot,
        below_candidate_min=candidate.salary_min is not None and hi < candidate.salary_min,
        idempotency_key=idempotency_key, created_at=now, team_offer_id=team_offer_id,
        expires_at=now + timedelta(days=limits.validity_days),
        is_demo=bool(company.is_demo) or await identity.is_demo_user(session, candidate.user_id),
    )  # fmt: skip
    try:
        async with session.begin_nested():
            session.add(offer)
            await session.flush()
    except IntegrityError as exc:  # параллельный запрос успел раньше
        existing = await find_by_key(session, company.id, idempotency_key)
        if existing is not None:
            return _replay(existing, vacancy, candidate), True
        raise ProblemError(
            409, "offer_exists", "Оффер этому кандидату по вакансии уже отправлен"
        ) from exc
    await _log(session, offer, None, S.sent, "company", {"created_by": str(user_id)})
    await _emit(session, offer, S.sent, prev=None, actor="company")
    return offer, False


async def apply(
    session: AsyncSession, *, vacancy: Vacancy, candidate: Candidate, message: str | None,
    limits: OfferLimits, now: datetime | None = None,
) -> Offer:  # fmt: skip
    """Отклик кандидата на опубликованную вакансию (ADR-022, `initiator = candidate`).

    Вилка берётся из вакансии. Контакты кандидата раскрываются компании сразу: отклик - его
    согласие (solution.md §2). Повторный отклик -> 409 `already_applied`.
    """
    now = now or datetime.now(UTC)
    if vacancy.status != VacancyStatus.published.value:
        raise ProblemError(404, "vacancy_not_found", "Вакансия не найдена")
    if str(vacancy.company_id) in (candidate.stoplist_company_ids or []):
        raise ProblemError(409, "company_in_stoplist", "Компания в вашем стоп-листе")
    dup = await session.scalar(
        select(Offer.id).where(
            Offer.vacancy_id == vacancy.id, Offer.candidate_id == candidate.user_id
        ).limit(1)
    )  # fmt: skip
    if dup is not None:
        raise ProblemError(409, "already_applied", "Вы уже откликались на эту вакансию")
    n = await session.scalar(
        select(func.count()).where(
            Offer.candidate_id == candidate.user_id,
            Offer.initiator == OfferInitiator.candidate.value,
            Offer.created_at >= now - WINDOW,
        )
    )
    if (n or 0) >= limits.applications_per_day:
        raise ProblemError(429, "application_limit_exceeded", "Лимит откликов на сутки исчерпан")
    offer = Offer(
        id=uuid.uuid4(), vacancy_id=vacancy.id, candidate_id=candidate.user_id,
        company_id=vacancy.company_id, created_by=candidate.user_id,
        salary_from=vacancy.salary_from, salary_to=vacancy.salary_to,
        salary_basis=vacancy.salary_basis,
        message=(message or "").strip() or None, title=vacancy.title,
        initiator=OfferInitiator.candidate.value, status=S.sent.value,
        awaiting_reply_from="company", created_at=now,
        match_snapshot=await matching.snapshot(session, vacancy.id, candidate.user_id),
        below_candidate_min=False, expires_at=now + timedelta(days=limits.validity_days),
        is_demo=bool(vacancy.is_demo) or await identity.is_demo_user(session, candidate.user_id),
    )  # fmt: skip
    try:
        async with session.begin_nested():
            session.add(offer)
            await session.flush()
    except IntegrityError as exc:  # параллельный повтор
        raise ProblemError(409, "already_applied", "Вы уже откликались на эту вакансию") from exc
    await _log(session, offer, None, S.sent, "candidate", {"initiator": "candidate"})
    await _reveal(session, offer, now)
    await _emit(session, offer, S.sent, prev=None, actor="candidate")
    return offer


# --- интерес до приглашения (E33-1, ADR-026) -------------------------------------------


def interest_not_found() -> ProblemError:
    return ProblemError(404, "interest_not_found", "Интерес не найден")


async def create_interest(
    session: AsyncSession,
    *,
    company: Company,
    user_id: uuid.UUID,
    candidate: Candidate,
    salary_from: int | None,
    salary_to: int | None,
    message: str | None,
    limits: OfferLimits,
    vacancy: Vacancy | None = None,
    title: str | None = None,
    salary_basis: SalaryBasis | None = None,
    now: datetime | None = None,
) -> tuple[Offer, bool]:
    """Отметка «интересен» с вилкой. Возвращает `(интерес, replay)`.

    Повтор отметки, пока интерес той же компании кандидату открыт, возвращает его же
    (`replay=True`), без новой строки, события и расхода лимита.
    """
    now = now or datetime.now(UTC)
    if company.status != CompanyStatus.verified.value:
        raise ProblemError(403, "company_not_verified", "Компания не прошла верификацию")
    open_q = select(Offer).where(
        Offer.company_id == company.id, Offer.candidate_id == candidate.user_id,
        Offer.status.in_(EXPIRABLE), Offer.expires_at > now,
    )  # fmt: skip
    existing = list(await session.scalars(open_q))
    for o in existing:
        if o.status in INTEREST_OPEN:
            return o, True
    if existing:  # уже идёт приглашение: интерес не нужен
        raise ProblemError(409, "offer_exists", "Приглашение этому кандидату уже отправлено")
    if vacancy is not None and vacancy.status != VacancyStatus.published.value:
        raise ProblemError(409, "vacancy_not_published", "Вакансия не опубликована")
    lo, hi = validate_range(salary_from, salary_to)
    message = (message or "").strip() or None
    if message and len(message) > INTEREST_MESSAGE_MAX:
        raise ProblemError(
            422, "message_too_long", f"Сообщение — не длиннее {INTEREST_MESSAGE_MAX} символов"
        )
    if vacancy is not None:
        dup = await session.scalar(
            select(Offer.id).where(
                Offer.vacancy_id == vacancy.id, Offer.candidate_id == candidate.user_id
            ).limit(1)
        )  # fmt: skip
        if dup is not None:
            raise ProblemError(409, "offer_exists", "По этой вакансии кандидату уже писали")

    q = select(func.count(), func.min(Offer.interest_at)).where(
        Offer.company_id == company.id, Offer.interest_at >= now - INTEREST_WINDOW
    )
    n, oldest = (await session.execute(q)).one()
    if n >= limits.interest_company_per_week:
        wait = INTEREST_WINDOW - (now - _aware(oldest)) if oldest else INTEREST_WINDOW
        raise ProblemError(
            429, "interest_limit_exceeded", "Лимит интересов на неделю исчерпан",
            headers={"Retry-After": str(max(1, int(wait.total_seconds()) + 1))},
        )  # fmt: skip
    n, oldest = await _count_since(session, Offer.candidate_id, candidate.user_id, now - WINDOW)
    if n >= limits.candidate_per_day:
        raise ProblemError(
            429, "candidate_offer_limit_exceeded", "Кандидат получил слишком много офферов",
            headers=_retry_after(oldest, now),
        )  # fmt: skip

    snapshot = await matching.snapshot(session, vacancy.id, candidate.user_id) if vacancy else None
    offer = Offer(
        id=uuid.uuid4(), vacancy_id=vacancy.id if vacancy else None,
        candidate_id=candidate.user_id, company_id=company.id, created_by=user_id,
        salary_from=lo, salary_to=hi, message=message,
        salary_basis=(salary_basis.value if salary_basis else None)
        or (vacancy.salary_basis if vacancy else None) or SalaryBasis.gross.value,
        title=(title or "").strip() or None, initiator=OfferInitiator.employer.value,
        status=S.interest.value, awaiting_reply_from="candidate", match_snapshot=snapshot,
        below_candidate_min=candidate.salary_min is not None and hi < candidate.salary_min,
        interest_at=now, created_at=now,
        expires_at=now + timedelta(days=limits.interest_validity_days),
        is_demo=bool(company.is_demo) or await identity.is_demo_user(session, candidate.user_id),
    )  # fmt: skip
    session.add(offer)
    await session.flush()
    await _log(session, offer, None, S.interest, "company", {"created_by": str(user_id)})
    await _emit(session, offer, S.interest, prev=None, actor="company")
    return offer, False


def _require_interest(offer: Offer) -> Offer:
    if offer.interest_at is None:
        raise interest_not_found()
    return offer


async def interests_for(
    session: AsyncSession, candidate_id: uuid.UUID, now: datetime | None = None
) -> list[Offer]:
    """Открытые интересы кандидату (без приглашения, срок не вышел), новые сверху."""
    now = now or datetime.now(UTC)
    q = select(Offer).where(
        Offer.candidate_id == candidate_id, Offer.status.in_(INTEREST_OPEN),
        Offer.expires_at > now,
    )  # fmt: skip
    return list(await session.scalars(q.order_by(Offer.created_at.desc())))


async def category_interest_salaries(
    session: AsyncSession, candidate_ids: list[uuid.UUID]
) -> list[tuple[int, int]]:
    """Вилки `(от, до)` интересов и приглашений кандидатам из списка (E39-16)."""
    if not candidate_ids:
        return []
    rows = await session.execute(
        select(Offer.salary_from, Offer.salary_to).where(
            Offer.candidate_id.in_(candidate_ids), Offer.interest_at.is_not(None)
        )
    )
    return [(a, b) for a, b in rows]


async def open_interest(session: AsyncSession, offer: Offer, now: datetime | None = None) -> Offer:
    """Кандидат открыл интерес: `interest → interest_opened`. Повтор — без изменений."""
    _require_interest(offer)
    if offer.status == S.interest.value:
        return await transition(session, offer, S.interest_opened, actor="candidate", now=now)
    if offer.status == S.declined.value or offer.status in (S.expired.value, S.withdrawn.value):
        raise ProblemError(409, "invalid_transition", f"Интерес уже закрыт: {offer.status}")
    return offer  # уже открыт или дошёл до приглашения


async def decline_interest(
    session: AsyncSession, offer: Offer, reason: DeclineReason, comment: str | None,
    now: datetime | None = None,
) -> Offer:  # fmt: skip
    """«Не интересно» с причиной. Повтор с той же причиной — без изменений."""
    _require_interest(offer)
    if offer.status == S.declined.value and offer.invited_at is None:
        if offer.decline_reason == reason.value:
            return offer
        raise ProblemError(409, "invalid_transition", "Интерес уже отклонён")
    if offer.status not in INTEREST_OPEN:
        raise ProblemError(409, "invalid_transition", f"Интерес уже закрыт: {offer.status}")
    return await decline(session, offer, reason, comment, now=now)


async def invite_from_interest(
    session: AsyncSession, offer: Offer, *, limits: OfferLimits, title: str | None = None,
    description: str | None = None, contact_method: ContactMethod | None = None,
    message: str | None = None, salary_from: int | None = None, salary_to: int | None = None,
    now: datetime | None = None,
) -> Offer:  # fmt: skip
    """Приглашение после открытого интереса: `interest_opened → sent` в той же строке.

    Вилку можно уточнить (снова обязательна и валидна). Без вакансии нужен `title`. Повтор после
    отправки возвращает приглашение без изменений.
    """
    now = now or datetime.now(UTC)
    _require_interest(offer)
    if offer.invited_at is not None:
        return offer
    if offer.status != S.interest_opened.value:
        raise ProblemError(
            409, "interest_not_opened", "Приглашение можно отправить, когда кандидат открыл интерес"
        )
    if _is_expired(offer, now):
        raise ProblemError(409, "offer_expired", "Срок действия интереса истёк")
    lo, hi = validate_range(
        salary_from if salary_from is not None else offer.salary_from,
        salary_to if salary_to is not None else offer.salary_to,
    )
    title = (title or "").strip() or offer.title
    if offer.vacancy_id is None and not title:
        raise ProblemError(
            422, "title_required", "Укажите название приглашения",
            errors=[{"field": "title", "message": "без вакансии название обязательно"}],
        )  # fmt: skip
    cand = await session.get(Candidate, offer.candidate_id) if offer.candidate_id else None
    offer.salary_from, offer.salary_to, offer.title = lo, hi, title
    offer.below_candidate_min = bool(cand and cand.salary_min is not None and hi < cand.salary_min)
    offer.description = (description or "").strip() or offer.description
    offer.contact_method = contact_method.value if contact_method else offer.contact_method
    offer.message = (message or "").strip() or offer.message
    offer.invited_at = now
    offer.expires_at = now + timedelta(days=limits.validity_days)
    return await transition(session, offer, S.sent, actor="company", now=now)


def _replay(existing: Offer, vacancy: Vacancy | None, candidate: Candidate) -> Offer:
    vacancy_id = vacancy.id if vacancy else None
    if existing.vacancy_id != vacancy_id or existing.candidate_id != candidate.user_id:
        raise ProblemError(
            409, "idempotency_key_reused", "Idempotency-Key уже использован для другого оффера"
        )
    return existing


async def avg_response_hours(
    session: AsyncSession, role: str | None, min_sample: int = 3
) -> float | None:
    """Средний срок ответа кандидатов категории (роли) на приглашения, часы (E33-5).

    Старт — `invited_at` (приглашение после интереса) или `created_at`; конец — `responded_at`.
    Откликов кандидата (`initiator = candidate`) и без ответа не считаем; мало данных — None.
    """
    if not role:
        return None
    stmt = (
        select(Offer.invited_at, Offer.created_at, Offer.responded_at)
        .join(Candidate, Candidate.user_id == Offer.candidate_id)
        .where(
            Candidate.primary_role == role, Offer.initiator == "employer",
            Offer.responded_at.is_not(None),
        )
    )  # fmt: skip
    hours = [
        (_aware(done) - _aware(start or created)).total_seconds() / 3600
        for start, created, done in (await session.execute(stmt)).all()
    ]
    hours = [h for h in hours if h >= 0]
    return round(sum(hours) / len(hours), 1) if len(hours) >= min_sample else None


async def get(session: AsyncSession, offer_id: uuid.UUID) -> Offer | None:
    """Оффер без проверки доступа — для внутренних обработчиков событий."""
    return await session.get(Offer, offer_id)


async def get_for_company(
    session: AsyncSession, company_id: uuid.UUID, offer_id: uuid.UUID, *, lock: bool = False
) -> Offer:
    q = select(Offer).where(Offer.id == offer_id, Offer.company_id == company_id)
    offer = await session.scalar(q.with_for_update() if lock else q)
    if offer is None:
        raise not_found()
    return offer


async def get_for_candidate(
    session: AsyncSession, candidate_id: uuid.UUID, offer_id: uuid.UUID, *, lock: bool = False
) -> Offer:
    q = select(Offer).where(Offer.id == offer_id, Offer.candidate_id == candidate_id)
    offer = await session.scalar(q.with_for_update() if lock else q)
    if offer is None:
        raise not_found()
    return offer


async def list_for_company(
    session: AsyncSession, company_id: uuid.UUID, *, status: str | None = None,
    vacancy_id: uuid.UUID | None = None, initiator: str | None = None, limit: int = 100,
) -> list[Offer]:  # fmt: skip
    q = select(Offer).where(Offer.company_id == company_id)
    if initiator:
        q = q.where(Offer.initiator == initiator)
    if status:
        q = q.where(Offer.status == status)
    if vacancy_id:
        q = q.where(Offer.vacancy_id == vacancy_id)
    return list(await session.scalars(q.order_by(Offer.created_at.desc()).limit(limit)))


async def list_for_candidate(
    session: AsyncSession, candidate_id: uuid.UUID, *, initiator: str | None = None
) -> list[Offer]:
    """Офферы и отклики кандидата; интересы без приглашения — отдельно (`interests_for`)."""
    q = select(Offer).where(
        Offer.candidate_id == candidate_id,
        (Offer.interest_at.is_(None)) | (Offer.invited_at.is_not(None)),
    )
    if initiator:
        q = q.where(Offer.initiator == initiator)
    return list(await session.scalars(q.order_by(Offer.created_at.desc())))


async def briefs_for(
    session: AsyncSession, company_id: uuid.UUID, candidate_id: uuid.UUID
) -> list[dict[str, str]]:
    """`offers_from_you` для карточки кандидата."""
    q = (
        select(Offer.id, Offer.status)
        .where(Offer.company_id == company_id, Offer.candidate_id == candidate_id)
        .order_by(Offer.created_at.desc())
    )
    return [{"id": str(i), "status": s} for i, s in (await session.execute(q)).all()]


async def invited(session: AsyncSession, company_id: uuid.UUID, candidate_id: uuid.UUID) -> bool:
    """Компания уже пригласила кандидата (E39-15: ФИО в карточке). Интерес без приглашения
    (ADR-026) не считается; отклик кандидата — считается (он сам вышел на контакт)."""
    q = (
        select(Offer.id)
        .where(
            Offer.company_id == company_id,
            Offer.candidate_id == candidate_id,
            or_(Offer.interest_at.is_(None), Offer.invited_at.is_not(None)),
        )
        .limit(1)
    )
    return (await session.scalar(q)) is not None


def _is_expired(offer: Offer, now: datetime) -> bool:
    return offer.status in EXPIRABLE and _aware(offer.expires_at) <= now


async def transition(
    session: AsyncSession, offer: Offer, to: OfferStatus, *, actor: str,
    now: datetime | None = None,
    payload: dict | None = None, **extra: Any,
) -> Offer:  # fmt: skip
    """Единственная точка смены статуса. Запрещённый переход → 409 `invalid_transition`."""
    now = now or datetime.now(UTC)
    prev = OfferStatus(offer.status)
    is_application = offer.initiator == OfferInitiator.candidate.value
    if is_application:
        table = APPLICATION_TRANSITIONS
    else:
        table = INTEREST_TRANSITIONS if prev.value in INTEREST_OPEN else TRANSITIONS
    allowed = table.get((prev, to))
    if allowed is None or allowed != actor:
        raise ProblemError(
            409, "invalid_transition", f"Переход {prev.value} → {to.value} невозможен"
        )
    if actor != "system" and _is_expired(offer, now):
        raise ProblemError(409, "offer_expired", "Срок действия оффера истёк")
    offer.status = to.value
    if to == S.viewed:
        offer.viewed_at = now
    if to in (S.accepted, S.declined, S.withdrawn, S.expired):
        offer.responded_at = now
    waiting = "company" if is_application else "candidate"
    offer.awaiting_reply_from = waiting if to in (S.sent, S.viewed, S.interest) else None
    if to == S.interest_opened:  # кандидат открыл интерес: ход компании
        offer.interest_opened_at, offer.awaiting_reply_from = now, "company"
    await session.flush()
    await _log(session, offer, prev, to, actor, payload)
    if to == S.accepted:
        await _reveal(session, offer, now)
    await _emit(session, offer, to, prev=prev, actor=actor, **extra)
    return offer


async def _reveal(session: AsyncSession, offer: Offer, now: datetime) -> None:
    """Контакты раскрываются только здесь, в транзакции перехода в `accepted` (security.md §3)."""
    if await session.get(ContactReveal, offer.id) is None:
        session.add(
            ContactReveal(
                offer_id=offer.id, candidate_id=offer.candidate_id,
                company_id=offer.company_id, revealed_at=now,
            )
        )  # fmt: skip
        await session.flush()


REVEALED = (S.accepted.value, S.interview.value, S.hired.value, S.not_hired.value)


async def is_revealed(session: AsyncSession, offer: Offer) -> bool:
    reveal = await session.get(ContactReveal, offer.id)
    return reveal is not None and reveal.revoked_at is None


async def require_revealed(session: AsyncSession, offer: Offer) -> ContactReveal:
    reveal = await session.get(ContactReveal, offer.id)
    if reveal is None:
        raise ProblemError(
            409, "contacts_not_revealed", "Контакты откроются после принятия оффера кандидатом"
        )
    if reveal.revoked_at is not None:
        raise ProblemError(409, "contacts_revoked", "Кандидат отозвал доступ к контактам")
    return reveal


async def revoke_contacts(
    session: AsyncSession, offer: Offer, now: datetime | None = None
) -> ContactReveal:
    """Отзыв доступа к контактам (E32-5a). Нечего отзывать — 409; повторный отзыв — no-op."""
    reveal = await session.get(ContactReveal, offer.id)
    if reveal is None:
        raise ProblemError(409, "contacts_not_revealed", "Контакты ещё не раскрыты")
    if reveal.revoked_at is None:
        reveal.revoked_at = now or datetime.now(UTC)
        await session.flush()
    return reveal


# --- переписка ---------------------------------------------------------------------------

CHAT_OPEN = (S.sent.value, S.viewed.value, S.accepted.value, S.interview.value)
MESSAGES_PER_HOUR = 30
COMPLAINT_REASONS = ("spam", "discrimination", "fake_company", "salary_mismatch", "abuse", "other")


async def list_events(session: AsyncSession, offer: Offer) -> list[OfferEvent]:
    """Журнал переходов оффера по времени (таймлайн для обеих сторон)."""
    q = select(OfferEvent).where(OfferEvent.offer_id == offer.id).order_by(OfferEvent.id)
    return list((await session.scalars(q)).all())


async def list_messages(
    session: AsyncSession, offer: Offer, limit: int = 200
) -> list[OfferMessage]:
    q = (
        select(OfferMessage).where(OfferMessage.offer_id == offer.id)
        .order_by(OfferMessage.created_at, OfferMessage.id).limit(limit)
    )  # fmt: skip
    return list(await session.scalars(q))


async def add_message(
    session: AsyncSession, offer: Offer, *, side: str, user_id: uuid.UUID, text: str,
    channel: str = "web", now: datetime | None = None,
) -> OfferMessage:  # fmt: skip
    """Сообщение от стороны оффера; пока оффер не закрыт (отказ, отзыв, срок, итог) — можно."""
    now = now or datetime.now(UTC)
    text = text.strip()
    if not text:
        raise ProblemError(422, "empty_message", "Пустое сообщение")
    if offer.status not in CHAT_OPEN:
        raise ProblemError(409, "offer_closed", "Переписка по этому офферу закрыта")
    if _is_expired(offer, now):
        raise ProblemError(409, "offer_expired", "Срок действия оффера истёк")
    # E39-26: вместо чата — по одному сообщению от стороны. Сообщение компании — сопроводительное
    # к приглашению (`offer.message`), ответ кандидата — одно, вместе с «Принять».
    already = await session.scalar(
        select(OfferMessage.id).where(
            OfferMessage.offer_id == offer.id, OfferMessage.author_side == side
        )
    )
    if already is not None or (side == "company" and offer.message):
        raise ProblemError(409, "message_limit", "В приглашении одно сообщение от каждой стороны")
    msg = OfferMessage(
        id=uuid.uuid4(), offer_id=offer.id, author_side=side, author_user_id=user_id,
        text=text, channel=channel, created_at=now,
    )  # fmt: skip
    session.add(msg)
    if offer.status in (S.accepted.value, S.interview.value):
        offer.awaiting_reply_from = "company" if side == "candidate" else "candidate"
    await session.flush()
    payload = OfferEventPayload(
        offer_id=offer.id, candidate_id=offer.candidate_id, company_id=offer.company_id,
        vacancy_id=offer.vacancy_id, status=OfferStatus(offer.status), actor=side,
        message_id=msg.id, initiator=OfferInitiator(offer.initiator),
    )  # fmt: skip
    await add_to_outbox(session, _envelope("offer.message", payload), offer.id)
    return msg


async def add_complaint(
    session: AsyncSession, offer: Offer, *, user_id: uuid.UUID, reason: str, comment: str | None
) -> Complaint:  # fmt: skip
    if reason not in COMPLAINT_REASONS:
        raise ProblemError(422, "invalid_reason", "Неизвестная причина жалобы")
    dup = await session.scalar(
        select(Complaint.id).where(
            Complaint.offer_id == offer.id, Complaint.reporter_user_id == user_id
        )
    )
    if dup is not None:
        raise ProblemError(409, "complaint_exists", "Жалоба на этот оффер уже подана")
    row = Complaint(
        id=uuid.uuid4(), offer_id=offer.id, reporter_user_id=user_id, reason=reason,
        comment=(comment or "").strip() or None,
    )  # fmt: skip
    session.add(row)
    await session.flush()
    return row


COMPLAINT_STATUSES = ("open", "resolved", "dismissed")


async def list_complaints(
    session: AsyncSession, status: str | None = None, limit: int = 100
) -> list[tuple[Complaint, Offer, Company | None]]:
    """Жалобы для админа: новые сверху; вместе с оффером и компанией."""
    q = (
        select(Complaint, Offer, Company)
        .join(Offer, Offer.id == Complaint.offer_id)
        .join(Company, Company.id == Offer.company_id, isouter=True)
        .order_by(Complaint.created_at.desc(), Complaint.id)
        .limit(limit)
    )
    if status is not None:
        q = q.where(Complaint.status == status)
    return [(c, o, co) for c, o, co in (await session.execute(q)).all()]


async def count_complaints(session: AsyncSession, status: str) -> int:
    """Число жалоб в статусе — счётчик на главной админки (E39-29)."""
    q = select(func.count()).select_from(Complaint).where(Complaint.status == status)
    return int(await session.scalar(q) or 0)


async def resolve_complaint(
    session: AsyncSession, complaint_id: uuid.UUID, decision: str
) -> tuple[Complaint, Offer, Company | None]:
    """`open → resolved|dismissed`; повтор того же решения идемпотентен, смена решения — 409."""
    row = await session.get(Complaint, complaint_id, with_for_update=True)
    if row is None:
        raise ProblemError(404, "complaint_not_found", "Жалоба не найдена")
    if row.status == "open":
        row.status = decision
        await session.flush()
    elif row.status != decision:
        raise ProblemError(409, "invalid_status", "Жалоба уже разобрана другим решением")
    offer = await session.get(Offer, row.offer_id)
    assert offer is not None
    return row, offer, await session.get(Company, offer.company_id)


async def mark_viewed(session: AsyncSession, offer: Offer, now: datetime | None = None) -> Offer:
    """Первое открытие кандидатом: `sent → viewed`; в остальных статусах ничего не делает."""
    if offer.initiator != OfferInitiator.employer.value:
        return offer
    if offer.status == S.sent.value and not _is_expired(offer, now or datetime.now(UTC)):
        await transition(session, offer, S.viewed, actor="candidate", now=now)
    return offer


async def mark_viewed_by_company(
    session: AsyncSession, offer: Offer, now: datetime | None = None
) -> Offer:
    """Компания открыла отклик: `sent -> viewed` (виден кандидату)."""
    now = now or datetime.now(UTC)
    if (
        offer.initiator == OfferInitiator.candidate.value
        and offer.status == S.sent.value
        and not _is_expired(offer, now)
    ):
        await transition(session, offer, S.viewed, actor="company", now=now)
    return offer


async def withdraw_application(
    session: AsyncSession, offer: Offer, now: datetime | None = None
) -> Offer:
    """Кандидат отзывает свой отклик (только `initiator = candidate`)."""
    if offer.initiator != OfferInitiator.candidate.value:
        raise not_found()
    return await transition(session, offer, S.withdrawn, actor="candidate", now=now)


async def accept(session: AsyncSession, offer: Offer, now: datetime | None = None) -> Offer:
    """Кандидат принимает приглашение: `transition` в `accepted` (там же открываются контакты,
    api.md §2.5).
    """
    return await transition(session, offer, S.accepted, actor="candidate", now=now)


async def decline(
    session: AsyncSession, offer: Offer, reason: DeclineReason, comment: str | None,
    now: datetime | None = None,
) -> Offer:  # fmt: skip
    """Кандидат отклоняет приглашение работодателя с причиной; свой отклик так не закрыть — 409
    (api.md §2.5).
    """
    if offer.status not in EXPIRABLE or (offer.initiator == OfferInitiator.candidate.value):
        raise ProblemError(
            409, "invalid_transition", f"Переход {offer.status} → declined невозможен"
        )
    offer.decline_reason, offer.decline_comment = reason.value, (comment or "").strip() or None
    return await transition(
        session, offer, S.declined, actor="candidate", now=now, decline_reason=reason
    )


async def withdraw(session: AsyncSession, offer: Offer, now: datetime | None = None) -> Offer:
    return await transition(session, offer, S.withdrawn, actor="company", now=now)


async def set_status(
    session: AsyncSession, offer: Offer, to: OfferStatus, now: datetime | None = None
) -> Offer:
    if to not in COMPANY_SET:
        raise ProblemError(422, "invalid_status", "Допустимы interview, hired, not_hired")
    return await transition(session, offer, to, actor="company", now=now)


async def expire_due(session: AsyncSession, now: datetime | None = None, batch: int = 200) -> int:
    """`sent|viewed|interest|interest_opened` с истёкшим сроком → `expired` (cron E8-5)."""
    now = now or datetime.now(UTC)
    q = (
        select(Offer).where(Offer.status.in_(EXPIRABLE), Offer.expires_at <= now)
        .order_by(Offer.expires_at).limit(batch).with_for_update(skip_locked=True)
    )  # fmt: skip
    rows = list(await session.scalars(q))
    for offer in rows:
        await transition(session, offer, S.expired, actor="system", now=now)
    return len(rows)


__all__ = [
    "CHAT_OPEN",
    "COMPANY_SET",
    "EXPIRABLE",
    "INTEREST_OPEN",
    "INTEREST_TRANSITIONS",
    "create_interest",
    "decline_interest",
    "interests_for",
    "invite_from_interest",
    "open_interest",
    "COMPLAINT_REASONS",
    "MESSAGES_PER_HOUR",
    "APPLICATION_TRANSITIONS",
    "OPEN",
    "REVEALED",
    "TRANSITIONS",
    "OfferLimits",
    "accept",
    "COMPLAINT_STATUSES",
    "add_complaint",
    "list_complaints",
    "resolve_complaint",
    "add_message",
    "apply",
    "briefs_for",
    "create",
    "decline",
    "expire_due",
    "get_for_candidate",
    "get_for_company",
    "is_revealed",
    "list_for_candidate",
    "list_for_company",
    "list_messages",
    "mark_viewed",
    "mark_viewed_by_company",
    "require_revealed",
    "set_status",
    "transition",
    "validate_range",
    "withdraw",
    "withdraw_application",
]
