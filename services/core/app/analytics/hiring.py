"""События аналитики блока 2 (E31-2b): категории, приглашения, отклики; потребности и шорт-лист.

Доменные `offer.*` и `candidate.category.changed` переводятся в `analytics_hiring` чистыми
функциями (их вызывает `mapper`): очередь `core.analytics` идемпотентна (inbox), поэтому
повторная доставка не дублирует запись. Событий потребностей и шорт-листа в брокере нет, их
эндпоинты пишут через `track_employer()` в своей транзакции, при реальном изменении.
В `props` только id, числа, флаги и slug'и (metrics.md §7): текста потребности нет.
"""

from __future__ import annotations

from typing import Any

from fsp_contracts.analytics import AnalyticsEvent
from fsp_contracts.enums import OfferStatus
from fsp_contracts.events import OfferEvent
from fsp_contracts.hiring import OfferInitiator


def _decision(status: OfferStatus) -> str | None:
    return {
        OfferStatus.accepted: "accepted",
        OfferStatus.declined: "declined",
        OfferStatus.expired: "expired",
    }.get(status)


def invite_events(c: Any, p: OfferEvent) -> list[AnalyticsEvent]:
    """Приглашение работодателя: `invite_sent` и итог `invite_answered`."""
    oid = str(p.offer_id)
    if c.envelope.type == "offer.sent":
        props = {"invite_id": oid, "with_vacancy": p.vacancy_id is not None}
        return [c.ev("invite_sent", p.company_id, "employer", props)]
    decision = _decision(p.status)
    if decision is None or c.envelope.type == "offer.message":
        return []
    props = {"invite_id": oid, "decision": decision}
    if p.decline_reason:
        props["reason"] = p.decline_reason.value
    return [c.ev("invite_answered", p.candidate_id, "candidate", props)]


def response_events(c: Any, p: OfferEvent) -> list[AnalyticsEvent]:
    """Отклик кандидата: `response_created` и ответ компании (интервью → принят, отказ → нет)."""
    rid = str(p.offer_id)
    if c.envelope.type == "offer.sent":
        if p.vacancy_id is None:
            return []
        props = {"response_id": rid, "vacancy_id": str(p.vacancy_id)}
        return [c.ev("response_created", p.candidate_id, "candidate", props)]
    if c.envelope.type == "offer.status_changed" and p.actor == "company":
        decision = {OfferStatus.interview: "accepted", OfferStatus.not_hired: "declined"}.get(
            p.status
        )
        if decision and p.prev_status in (OfferStatus.sent, OfferStatus.viewed):
            props = {"response_id": rid, "decision": decision}
            return [c.ev("response_answered", p.company_id, "employer", props)]
    return []


def offer_events(c: Any, p: OfferEvent) -> list[AnalyticsEvent]:
    if p.initiator == OfferInitiator.candidate:
        return response_events(c, p)
    return invite_events(c, p)


def category_events(c: Any, p: Any) -> list[AnalyticsEvent]:
    """`candidate.category.changed` → `category_changed` на каждую категорию набора."""
    return [
        c.ev(
            "category_changed", p.candidate_id, "candidate",
            {"profession": cat.profession, "grade": cat.grade, "trigger": "recompute"},
        )
        for cat in p.categories
    ]  # fmt: skip


def interest_events(c: Any, p: OfferEvent) -> list[AnalyticsEvent]:
    """События интереса (offer.interest.*): shown, answered (opened/declined/expired/withdrawn).

    Интерес — это приглашение на фазе, когда компания ещё не отправила формальное предложение.
    После того как компания отправляет предложение (invited_at устанавливается), событие
    interest_to_invite отмечает переход. После этого обычные offer.* события.
    """
    oid = str(p.offer_id)
    match c.envelope.type:
        case "offer.interest.sent":
            props = {"interest_id": oid, "with_vacancy": p.vacancy_id is not None}
            return [c.ev("interest_shown", p.company_id, "employer", props)]
        case "offer.interest.opened":
            props = {"interest_id": oid, "decision": "opened"}
            return [c.ev("interest_answered", p.candidate_id, "candidate", props)]
        case "offer.interest.declined":
            props = {"interest_id": oid, "decision": "declined"}
            if p.decline_reason:
                props["reason"] = p.decline_reason.value
            return [c.ev("interest_answered", p.candidate_id, "candidate", props)]
        case "offer.interest.expired":
            props = {"interest_id": oid, "decision": "expired"}
            return [c.ev("interest_answered", p.candidate_id, "candidate", props)]
        case "offer.interest.withdrawn":
            props = {"interest_id": oid, "decision": "withdrawn"}
            return [c.ev("interest_answered", p.company_id, "employer", props)]
    return []
