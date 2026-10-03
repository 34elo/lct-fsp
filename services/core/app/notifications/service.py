"""Создание уведомлений и раздача по каналам (web: SSE, tg: команда `notify.telegram`).

Telegram — только при привязанном чате и действующем согласии `telegram_notifications`.
В данных для работодателя до accept нет ПДн кандидата: только id оффера, вакансия, статус.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import structlog
from fsp_contracts import new_envelope
from fsp_contracts.enums import ConsentType
from fsp_contracts.notify import NotifyTelegram, TgButton, TgTemplate
from fsp_contracts.ui import NotificationNew, UiMessage, new_ui_message
from fsp_platform.outbox import add_to_outbox
from sqlalchemy.ext.asyncio import AsyncSession

from app.consents import service as consents
from app.notifications.models import Notification
from app.telegram import service as telegram

log = structlog.get_logger()

UiPublish = Callable[[UiMessage], Awaitable[None]]


async def tg_chat_id(session: AsyncSession, user_id: uuid.UUID) -> int | None:
    account = await telegram.account_of_user(session, user_id)
    if account is None:
        return None
    if not await consents.has_consent(session, user_id, ConsentType.telegram_notifications):
        return None
    return account.chat_id


async def notify(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    type: str,
    title: str,
    payload: dict[str, Any],
    out: list[UiMessage],
    extra_ui: Sequence[UiMessage] = (),
    tg: TgTemplate | None = None,
    tg_data: dict[str, Any] | None = None,
    buttons: list[list[TgButton]] | None = None,
    edit_of: str | None = None,
) -> Notification:
    """Запись в БД + команда боту в outbox (одна транзакция). SSE-сообщения кладём в `out`."""
    chat_id = await tg_chat_id(session, user_id) if tg is not None else None
    n = Notification(
        id=uuid.uuid4(),
        user_id=user_id,
        type=type,
        payload={"title": title, **payload},
        channels=["web", "tg"] if chat_id is not None else ["web"],
        delivered={"tg": "queued"} if chat_id is not None else {},
    )
    session.add(n)
    await session.flush()
    if chat_id is not None and tg is not None:
        cmd = NotifyTelegram(
            chat_id=chat_id,
            template=tg,
            data=tg_data or {},
            buttons=buttons or [],
            edit_of=edit_of,
        )
        await add_to_outbox(session, new_envelope("notify.telegram", "core", cmd), n.id)
    out.extend(extra_ui)
    out.append(
        new_ui_message(
            user_id, "notification.new", NotificationNew(id=n.id, type=type, title=title)
        )
    )
    return n


async def push(ui_publish: UiPublish | None, messages: list[UiMessage]) -> None:
    """SSE — удобство, а не часть транзакции: сбой публикации не роняет обработчик."""
    if ui_publish is None:
        return
    for m in messages:
        try:
            await ui_publish(m)
        except Exception:
            log.warning("ui_publish_failed", event=m.event)


async def send_tg(
    session: AsyncSession,
    user_id: uuid.UUID,
    template: TgTemplate,
    data: dict[str, Any],
    *,
    edit_of: str | None = None,
) -> bool:
    """Только Telegram, без записи в ленту (например, правка сообщения после ответа в боте)."""
    chat_id = await tg_chat_id(session, user_id)
    if chat_id is None:
        return False
    cmd = NotifyTelegram(chat_id=chat_id, template=template, data=data, edit_of=edit_of)
    await add_to_outbox(session, new_envelope("notify.telegram", "core", cmd), user_id)
    return True
