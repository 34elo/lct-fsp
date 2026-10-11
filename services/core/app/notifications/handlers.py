"""Обработчики `core.handlers`: `offer.*`, `skills.profile.updated` → уведомления.

Цепочка: запись в `notifications` + `ui.user.<id>` + команда `notify.telegram`.
Идемпотентность — inbox; команда боту идёт через outbox в той же транзакции.
Отдельные обработчики — для результатов ФСП и регулярных заданий.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

import structlog
from fsp_contracts import Envelope
from fsp_contracts.assessment import CategoryChanged, RegularTaskPublished
from fsp_contracts.enums import OfferStatus
from fsp_contracts.events import FspResultsImported, OfferEvent, SkillsProfileUpdated
from fsp_contracts.hiring import OfferInitiator
from fsp_contracts.notify import TgButton, TgTemplate
from fsp_contracts.ui import (
    OfferCreated,
    OfferMessage,
    OfferUpdated,
    ProfileUpdated,
    UiMessage,
    new_ui_message,
)
from fsp_platform.messaging import Consumer, idempotent
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.companies import service as companies
from app.matching import needs as needs_cfg
from app.matching import subscriptions
from app.notifications import service
from app.notifications.service import UiPublish
from app.offers import service as offers
from app.offers.models import Offer
from app.taxonomy import service as taxonomy
from app.vacancies import service as vacancies

log = structlog.get_logger()

OFFER_EVENTS = (
    "offer.sent",
    "offer.viewed",
    "offer.accepted",
    "offer.declined",
    "offer.expired",
    "offer.withdrawn",
    "offer.message",
    "offer.status_changed",
)
# интерес до приглашения; payload `OfferInterestEvent` читается как `OfferEvent`
INTEREST_EVENTS = (
    "offer.interest.sent",
    "offer.interest.opened",
    "offer.interest.declined",
    "offer.interest.expired",
    "offer.interest.withdrawn",
)

S = OfferStatus
_CLOSED_BY_SYSTEM_TEXT = {
    S.expired: "Срок оффера истёк",
    S.withdrawn: "Оффер отозван",
}
_STATUS_TITLE = {
    S.interview: "Приглашение на интервью",
    S.hired: "Вас взяли на работу",
    S.not_hired: "Работодатель принял решение по офферу",
}


def _buttons(offer_id: uuid.UUID) -> list[list[TgButton]]:
    return [
        [
            TgButton(text="✅ Принять", callback_data=f"o:a:{offer_id}"),
            TgButton(text="❌ Отклонить", callback_data=f"o:d:{offer_id}"),
        ],
        [
            TgButton(text="❓ Задать вопрос", callback_data=f"o:q:{offer_id}"),
            TgButton(text="📄 Подробнее", callback_data=f"o:v:{offer_id}"),
        ],
    ]


def _updated(user_id: uuid.UUID, ev: OfferEvent, awaiting: str | None) -> UiMessage:
    return new_ui_message(
        user_id,
        "offer.updated",
        OfferUpdated(offer_id=ev.offer_id, status=ev.status, awaiting_reply_from=awaiting),
    )


async def offer_card_data(session: AsyncSession, offer: Offer) -> dict:
    """Поля шаблона `offer_new` (и карточки оффера в боте): без ПДн, только вилка и вакансия."""
    company = await companies.get_company(session, offer.company_id)
    vacancy = await vacancies.get(session, offer.vacancy_id) if offer.vacancy_id else None
    snap = offer.match_snapshot or {}
    return {
        "offer_id": str(offer.id),
        "company_name": company.name if company else None,
        "company_responsibility": company.responsibility_score if company else None,
        # приглашение без вакансии показывает своё название
        "vacancy_title": vacancy.title if vacancy else offer.title,
        "formats": list(vacancy.formats) if vacancy else [],
        "employment_type": vacancy.employment_type if vacancy else None,
        "salary_from": offer.salary_from,
        "salary_to": offer.salary_to,
        "salary_basis": offer.salary_basis,
        "message": offer.message,
        "match_score": snap.get("score"),
        "explanation": snap.get("explanation") or [],
        "below_candidate_min": offer.below_candidate_min,
        "expires_at": offer.expires_at.isoformat(),
    }


async def _offer_sent(session: AsyncSession, ev: OfferEvent, out: list[UiMessage]) -> None:
    offer = await offers.get(session, ev.offer_id)
    if offer is None or offer.candidate_id is None:
        return
    data = await offer_card_data(session, offer)
    await service.notify(
        session,
        offer.candidate_id,
        type="offer_new",
        title=f"Новый оффер от «{data['company_name']}»",
        payload={"offer_id": str(offer.id), "vacancy_title": data["vacancy_title"]},
        out=out,
        extra_ui=[
            new_ui_message(offer.candidate_id, "offer.created", OfferCreated(offer_id=offer.id))
        ],
        tg=TgTemplate.offer_new,
        tg_data=data,
        buttons=_buttons(offer.id),
        edit_of=f"offer:{offer.id}",
    )


async def _to_company(
    session: AsyncSession,
    ev: OfferEvent,
    out: list[UiMessage],
    *,
    type: str,
    title: str,
    extra: dict | None = None,
    template: TgTemplate = TgTemplate.offer_updated,
) -> None:
    """Всем участникам компании. Без ПДн кандидата: id оффера, вакансия, статус."""
    vacancy = await vacancies.get(session, ev.vacancy_id) if ev.vacancy_id else None
    if vacancy is not None:
        vacancy_title = vacancy.title
    else:  # приглашение без вакансии: его название
        offer = await offers.get(session, ev.offer_id)
        vacancy_title = offer.title if offer else None
    data = {
        "offer_id": str(ev.offer_id),
        "status": ev.status.value,
        "vacancy_title": vacancy_title,
        **(extra or {}),
    }
    for user_id in await companies.member_user_ids(session, ev.company_id):
        await service.notify(
            session,
            user_id,
            type=type,
            title=title,
            payload={"offer_id": str(ev.offer_id), "status": ev.status.value, **(extra or {})},
            out=out,
            extra_ui=[_updated(user_id, ev, _awaiting(ev))],
            tg=template,
            tg_data=data,
        )


def _awaiting(ev: OfferEvent) -> str | None:
    if ev.status == S.interest:
        return "candidate"
    if ev.status == S.interest_opened:
        return "company"
    if ev.status in (S.sent, S.viewed):
        return "company" if ev.initiator == OfferInitiator.candidate else "candidate"
    return None


async def _to_candidate(
    session: AsyncSession,
    ev: OfferEvent,
    out: list[UiMessage],
    *,
    type: str,
    title: str,
    template: TgTemplate = TgTemplate.offer_updated,
) -> None:
    data = {"offer_id": str(ev.offer_id), "status": ev.status.value}
    await service.notify(
        session,
        ev.candidate_id,
        type=type,
        title=title,
        payload=data,
        out=out,
        extra_ui=[_updated(ev.candidate_id, ev, _awaiting(ev))],
        tg=template,
        tg_data=data,
        edit_of=f"offer:{ev.offer_id}",
    )


async def _offer_event(session: AsyncSession, envelope: Envelope, out: list[UiMessage]) -> None:
    ev = OfferEvent.model_validate(envelope.payload)
    st = ev.status
    match envelope.type:
        case "offer.sent" if ev.initiator == OfferInitiator.candidate:
            await _to_company(
                session, ev, out, type="application_new", title="Новый отклик на вакансию"
            )
        case "offer.sent":
            await _offer_sent(session, ev, out)
        case "offer.viewed" if ev.initiator == OfferInitiator.candidate:
            out.append(_updated(ev.candidate_id, ev, "company"))
        case "offer.viewed":
            out.extend(_updated(u, ev, "candidate") for u in await _members(session, ev))
        case "offer.accepted":
            await _to_company(
                session, ev, out, type="offer_accepted",
                title="Оффер принят, контакты кандидата открыты",
            )  # fmt: skip
            if ev.actor == "candidate":  # правим сообщение с кнопками в боте
                await service.send_tg(
                    session, ev.candidate_id, TgTemplate.offer_accepted,
                    {"offer_id": str(ev.offer_id)}, edit_of=f"offer:{ev.offer_id}",
                )  # fmt: skip
        case "offer.declined":
            extra = {"decline_reason": ev.decline_reason.value} if ev.decline_reason else None
            await _to_company(
                session, ev, out, type="offer_declined", title="Кандидат отклонил оффер",
                extra=extra,
            )  # fmt: skip
        case "offer.expired":
            await _to_company(
                session, ev, out, type="offer_expired", title=_CLOSED_BY_SYSTEM_TEXT[S.expired]
            )
            await _to_candidate(
                session, ev, out, type="offer_expired", title=_CLOSED_BY_SYSTEM_TEXT[S.expired]
            )
        case "offer.withdrawn" if ev.actor == "candidate":  # кандидат отозвал свой отклик
            await _to_company(
                session, ev, out, type="application_withdrawn", title="Кандидат отозвал отклик"
            )
        case "offer.withdrawn":
            await _to_candidate(
                session, ev, out, type="offer_withdrawn", title=_CLOSED_BY_SYSTEM_TEXT[S.withdrawn]
            )
        case "offer.message":
            await _message(session, ev, out)
        case "offer.interest.sent":
            await _to_candidate(
                session, ev, out, type="interest_new", title="Компания интересуется вами"
            )
        case "offer.interest.opened":
            await _to_company(
                session, ev, out, type="interest_opened",
                title="Кандидат открыл ваш интерес: можно отправить приглашение",
            )  # fmt: skip
        case "offer.interest.declined":
            extra = {"decline_reason": ev.decline_reason.value} if ev.decline_reason else None
            await _to_company(
                session, ev, out, type="interest_declined", title="Кандидату не интересно",
                extra=extra,
            )  # fmt: skip
        case "offer.interest.expired":
            await _to_company(
                session, ev, out, type="interest_expired", title="Срок интереса истёк"
            )
            out.append(_updated(ev.candidate_id, ev, None))
        case "offer.interest.withdrawn":
            out.append(_updated(ev.candidate_id, ev, None))
        case "offer.status_changed":
            title = _STATUS_TITLE.get(st, "Статус оффера изменился")
            if ev.actor == "company":
                await _to_candidate(session, ev, out, type="offer_status", title=title)
            else:
                out.extend(_updated(u, ev, None) for u in await _members(session, ev))


async def _members(session: AsyncSession, ev: OfferEvent) -> list[uuid.UUID]:
    return await companies.member_user_ids(session, ev.company_id)


async def _message(session: AsyncSession, ev: OfferEvent, out: list[UiMessage]) -> None:
    """Адресат — противоположная сторона. Текст в уведомление не кладём (он может быть ПДн)."""
    if ev.message_id is None:
        return
    title = "Новое сообщение по офферу"

    def msg_ui(u: uuid.UUID) -> UiMessage:
        body = OfferMessage(offer_id=ev.offer_id, message_id=ev.message_id)
        return new_ui_message(u, "offer.message", body)

    if ev.actor == "candidate":
        await _to_company(
            session, ev, out, type="offer_message", title=title,
            extra={"message_id": str(ev.message_id)}, template=TgTemplate.offer_message,
        )  # fmt: skip
        out.extend(msg_ui(u) for u in await _members(session, ev))
    else:
        data = {"offer_id": str(ev.offer_id), "message_id": str(ev.message_id)}
        await service.notify(
            session, ev.candidate_id, type="offer_message", title=title, payload=data, out=out,
            extra_ui=[msg_ui(ev.candidate_id)], tg=TgTemplate.offer_message, tg_data=data,
        )  # fmt: skip


def _significant(ev: SkillsProfileUpdated) -> bool:
    d = ev.diff
    return bool(d.skills_up or d.skills_new or d.grade or d.category)


def register(
    consumers: Mapping[str, Consumer],
    session_factory: async_sessionmaker[AsyncSession],
    ui_publish: UiPublish | None = None,
) -> None:
    @consumers["core.handlers"].on(*OFFER_EVENTS, *INTEREST_EVENTS)
    @idempotent(session_factory, "notifications.offer")
    async def on_offer(envelope: Envelope, session: AsyncSession) -> None:
        out: list[UiMessage] = []
        await _offer_event(session, envelope, out)
        await service.push(ui_publish, out)

    @consumers["core.handlers"].on("skills.profile.updated")
    @idempotent(session_factory, "notifications.profile")
    async def on_profile(envelope: Envelope, session: AsyncSession) -> None:
        ev = SkillsProfileUpdated.model_validate(envelope.payload)
        if not _significant(ev):  # только при значимом diff
            return
        diff = ev.diff.model_dump(mode="json")
        out: list[UiMessage] = []
        await service.notify(
            session, ev.candidate_id, type="profile_updated", title="Профиль обновился",
            payload={"profile_version": ev.profile_version, "diff": diff}, out=out,
            extra_ui=[
                new_ui_message(
                    ev.candidate_id, "profile.updated",
                    ProfileUpdated(profile_version=ev.profile_version, diff=ev.diff),
                )
            ],
            tg=TgTemplate.profile_updated, tg_data={"diff": diff},
        )  # fmt: skip
        await service.push(ui_publish, out)

    @consumers["core.handlers"].on("fsp.results.imported")
    @idempotent(session_factory, "notifications.fsp_imported")
    async def on_fsp_imported(envelope: Envelope, session: AsyncSession) -> None:
        ev = FspResultsImported.model_validate(envelope.payload)
        if not ev.results:  # синхронизация без новых результатов (сменился только состав команд)
            return
        out: list[UiMessage] = []
        await service.notify(
            session, ev.candidate_id, type="fsp_imported", title="Новый результат ФСП",
            payload={}, out=out,
            tg=TgTemplate.fsp_imported, tg_data={"count": len(ev.results)},
        )  # fmt: skip
        await service.push(ui_publish, out)

    @consumers["core.handlers"].on("regular_task.published")
    @idempotent(session_factory, "notifications.regular_task")
    async def on_regular_task(envelope: Envelope, session: AsyncSession) -> None:
        ev = RegularTaskPublished.model_validate(envelope.payload)
        out: list[UiMessage] = []
        # человеку — название профессии, не slug
        profs = await taxonomy.list_professions(session, include_hidden=True)
        titles = {p.slug: p.title for p in profs}
        title = titles.get(ev.profession, ev.profession)
        for candidate_id in ev.candidate_ids:
            await service.notify(
                session, candidate_id, type="regular_task_published",
                title=f"Новое задание: {title}",
                payload={"family_id": str(ev.family_id), "profession": ev.profession}, out=out,
                tg=TgTemplate.regular_task_published,
                tg_data={"profession": ev.profession, "profession_title": title},
            )  # fmt: skip
        await service.push(ui_publish, out)

    # новый подходящий кандидат → подписка компании (SSE + бот, дайджест не чаще раза в час)
    @consumers["core.handlers"].on("candidate.category.changed")
    @idempotent(session_factory, "notifications.category_subscription")
    async def on_category_changed(envelope: Envelope, session: AsyncSession) -> None:
        ev = CategoryChanged.model_validate(envelope.payload)
        touched = await subscriptions.register_hits(session, ev.candidate_id, ev.categories)
        if not touched:
            return
        cfg = needs_cfg.NeedsConfig.load()
        await service.push(ui_publish, await subscriptions.flush_due(session, cfg, only=touched))
