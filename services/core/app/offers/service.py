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
  тому же кандидату от той же компании — 409; события `offer.*` идут со schema_version 2.
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
from fsp_contracts.hiring import OFFER_SCHEMA_VERSION, ContactMethod, OfferInitiator
from fsp_platform.app import ProblemError
from fsp_platform.outbox import add_to_outbox
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.models import Candidate
from app.companies.models import Company
from app.matching import service as matching
from app.matching.scoring import DEFAULT_SCORING_PATH
from app.offers.models import Complaint, ContactReveal, Offer, OfferEvent, OfferMessage
from app.vacancies.models import Vacancy
from app.vacancies.service import VacancyStatus

S = OfferStatus
OPEN = (S.sent.value, S.viewed.value)  # ждут ответа кандидата
WINDOW = timedelta(hours=24)

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

    @classmethod
    def load(cls, path: Path | str | None = None) -> OfferLimits:
        data = yaml.safe_load(Path(path or DEFAULT_SCORING_PATH).read_text(encoding="utf-8"))
        lim = (data or {}).get("limits", {})
        base = cls()
        return cls(
            company_per_day=int(lim.get("offer_company_per_day", base.company_per_day)),
            candidate_per_day=int(lim.get("offer_candidate_per_day", base.candidate_per_day)),
            validity_days=int(lim.get("offer_validity_days", base.validity_days)),
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


async def _count_since(session: AsyncSession, column: Any, value: uuid.UUID, since: datetime):
    q = select(func.count(), func.min(Offer.created_at)).where(
        column == value, Offer.created_at >= since
    )
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
            Offer.status.in_(OPEN),
            Offer.expires_at > datetime.now(UTC),
        )
        .group_by(Offer.candidate_id)
    )
    return {cid: n for cid, n in (await session.execute(q)).all()}


def _retry_after(oldest: datetime | None, now: datetime) -> dict[str, str]:
    if oldest is None:
        return {"Retry-After": str(int(WINDOW.total_seconds()))}
    wait = int((_aware(oldest) + WINDOW - now).total_seconds()) + 1
    return {"Retry-After": str(max(1, wait))}


async def _emit(session: AsyncSession, offer: Offer, to: OfferStatus, *, prev, actor, **extra):
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


async def _find_by_key(session: AsyncSession, company_id: uuid.UUID, key: str) -> Offer | None:
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
    now: datetime | None = None,
) -> tuple[Offer, bool]:
    """Новый оффер (приглашение работодателя, ADR-022: вакансия необязательна).

    Возвращает `(оффер, replay)`: `replay=True` — это повтор по тому же ключу.
    """
    now = now or datetime.now(UTC)
    existing = await _find_by_key(session, company.id, idempotency_key)
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
            Offer.candidate_id == candidate.user_id, Offer.status.in_(OPEN),
            Offer.expires_at > now,
        )  # fmt: skip
    if await session.scalar(dup_q.limit(1)) is not None:
        raise ProblemError(409, "offer_exists", "Оффер этому кандидату по вакансии уже отправлен")

    since = now - WINDOW
    n, oldest = await _count_since(session, Offer.company_id, company.id, since)
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
        title=title, description=(description or "").strip() or None,
        contact_method=contact_method.value if contact_method else None,
        initiator=OfferInitiator.employer.value, status=S.sent.value,
        awaiting_reply_from="candidate", match_snapshot=snapshot,
        below_candidate_min=candidate.salary_min is not None and hi < candidate.salary_min,
        idempotency_key=idempotency_key, created_at=now,
        expires_at=now + timedelta(days=limits.validity_days),
    )  # fmt: skip
    try:
        async with session.begin_nested():
            session.add(offer)
            await session.flush()
    except IntegrityError as exc:  # параллельный запрос успел раньше
        existing = await _find_by_key(session, company.id, idempotency_key)
        if existing is not None:
            return _replay(existing, vacancy, candidate), True
        raise ProblemError(
            409, "offer_exists", "Оффер этому кандидату по вакансии уже отправлен"
        ) from exc
    await _log(session, offer, None, S.sent, "company", {"created_by": str(user_id)})
    await _emit(session, offer, S.sent, prev=None, actor="company")
    return offer, False


def _replay(existing: Offer, vacancy: Vacancy | None, candidate: Candidate) -> Offer:
    vacancy_id = vacancy.id if vacancy else None
    if existing.vacancy_id != vacancy_id or existing.candidate_id != candidate.user_id:
        raise ProblemError(
            409, "idempotency_key_reused", "Idempotency-Key уже использован для другого оффера"
        )
    return existing


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
    vacancy_id: uuid.UUID | None = None, limit: int = 100,
) -> list[Offer]:  # fmt: skip
    q = select(Offer).where(Offer.company_id == company_id)
    if status:
        q = q.where(Offer.status == status)
    if vacancy_id:
        q = q.where(Offer.vacancy_id == vacancy_id)
    return list(await session.scalars(q.order_by(Offer.created_at.desc()).limit(limit)))


async def list_for_candidate(session: AsyncSession, candidate_id: uuid.UUID) -> list[Offer]:
    q = select(Offer).where(Offer.candidate_id == candidate_id)
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


def _is_expired(offer: Offer, now: datetime) -> bool:
    return offer.status in OPEN and _aware(offer.expires_at) <= now


async def transition(
    session: AsyncSession, offer: Offer, to: OfferStatus, *, actor: str,
    now: datetime | None = None,
    payload: dict | None = None, **extra: Any,
) -> Offer:  # fmt: skip
    """Единственная точка смены статуса. Запрещённый переход → 409 `invalid_transition`."""
    now = now or datetime.now(UTC)
    prev = OfferStatus(offer.status)
    allowed = TRANSITIONS.get((prev, to))
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
    offer.awaiting_reply_from = "candidate" if to in (S.sent, S.viewed) else None
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
    return await session.get(ContactReveal, offer.id) is not None


async def require_revealed(session: AsyncSession, offer: Offer) -> ContactReveal:
    reveal = await session.get(ContactReveal, offer.id)
    if reveal is None:
        raise ProblemError(
            409, "contacts_not_revealed", "Контакты откроются после принятия оффера кандидатом"
        )
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


async def mark_viewed(session: AsyncSession, offer: Offer, now: datetime | None = None) -> Offer:
    """Первое открытие кандидатом: `sent → viewed`; в остальных статусах ничего не делает."""
    if offer.status == S.sent.value and not _is_expired(offer, now or datetime.now(UTC)):
        await transition(session, offer, S.viewed, actor="candidate", now=now)
    return offer


async def accept(session: AsyncSession, offer: Offer, now: datetime | None = None) -> Offer:
    return await transition(session, offer, S.accepted, actor="candidate", now=now)


async def decline(
    session: AsyncSession, offer: Offer, reason: DeclineReason, comment: str | None,
    now: datetime | None = None,
) -> Offer:  # fmt: skip
    if OfferStatus(offer.status) not in (S.sent, S.viewed):
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
    """`sent|viewed` с истёкшим сроком → `expired` (cron E8-5 вызывает эту функцию)."""
    now = now or datetime.now(UTC)
    q = (
        select(Offer).where(Offer.status.in_(OPEN), Offer.expires_at <= now)
        .order_by(Offer.expires_at).limit(batch).with_for_update(skip_locked=True)
    )  # fmt: skip
    rows = list(await session.scalars(q))
    for offer in rows:
        await transition(session, offer, S.expired, actor="system", now=now)
    return len(rows)


__all__ = [
    "CHAT_OPEN",
    "COMPANY_SET",
    "COMPLAINT_REASONS",
    "MESSAGES_PER_HOUR",
    "OPEN",
    "REVEALED",
    "TRANSITIONS",
    "OfferLimits",
    "accept",
    "add_complaint",
    "add_message",
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
    "require_revealed",
    "set_status",
    "transition",
    "validate_range",
    "withdraw",
]
