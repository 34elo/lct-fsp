"""Отправка `notify.telegram`: лимиты, редактирование по `edit_of`, ретраи по RetryAfter."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from fsp_contracts import Envelope
from fsp_contracts.notify import NotifyTelegram
from redis.asyncio import Redis

from fsp_bot.limiter import SendLimiter
from fsp_bot.templates import render, render_keyboard

log = structlog.get_logger()


class Sender:
    def __init__(
        self,
        bot: Bot,
        redis: Redis,
        limiter: SendLimiter,
        *,
        max_retries: int = 3,
        map_ttl: int = 30 * 86400,
        sent_ttl: int = 86400,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.bot, self.redis, self.limiter = bot, redis, limiter
        self.max_retries, self.map_ttl, self.sent_ttl = max_retries, map_ttl, sent_ttl
        self._sleep = sleep

    @staticmethod
    def _map_key(chat_id: int, edit_of: str) -> str:
        return f"bot:msg:{chat_id}:{edit_of}"

    async def handle(self, envelope: Envelope) -> None:
        """Обработчик команды. Повторная доставка того же `message_id` второго сообщения не шлёт."""
        cmd = NotifyTelegram.model_validate(envelope.payload)
        sent_key = f"bot:sent:{envelope.message_id}"
        if await self.redis.exists(sent_key):
            log.info("notify_duplicate", template=cmd.template)
            return
        await self.deliver(cmd)
        await self.redis.set(sent_key, 1, ex=self.sent_ttl)

    async def deliver(self, cmd: NotifyTelegram) -> None:
        text = render(cmd.template, cmd.data)
        markup = render_keyboard(cmd.buttons)
        try:
            if cmd.edit_of:
                raw = await self.redis.get(self._map_key(cmd.chat_id, cmd.edit_of))
                if raw is not None:
                    if await self._edit(cmd.chat_id, int(raw), text, markup):
                        return
            message_id = await self._call(
                lambda: self.bot.send_message(
                    cmd.chat_id, text, parse_mode="HTML", reply_markup=markup
                ),
                cmd.chat_id,
            )
        except TelegramForbiddenError:
            # Пользователь заблокировал бота: повтор не поможет, сообщение снимаем с очереди
            log.warning("chat_unavailable", template=cmd.template)
            return
        if cmd.edit_of and message_id is not None:
            await self.redis.set(
                self._map_key(cmd.chat_id, cmd.edit_of), message_id, ex=self.map_ttl
            )
        log.info("notify_sent", template=cmd.template)

    async def _edit(self, chat_id: int, message_id: int, text: str, markup: Any) -> bool:
        """True — сообщение отредактировано (или уже такое же); False — слать новое."""
        try:
            await self._call(
                lambda: self.bot.edit_message_text(
                    text,
                    chat_id=chat_id,
                    message_id=message_id,
                    parse_mode="HTML",
                    reply_markup=markup,
                ),
                chat_id,
            )
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc):
                return True
            log.info("edit_failed_send_new", error=str(exc)[:80])
            return False
        return True

    async def _call(self, make: Callable[[], Awaitable[Any]], chat_id: int) -> int | None:
        for attempt in range(self.max_retries + 1):
            await self.limiter.acquire(chat_id)
            try:
                result = await make()
            except TelegramRetryAfter as exc:
                if attempt == self.max_retries:
                    raise
                log.warning("telegram_retry_after", seconds=exc.retry_after)
                await self._sleep(exc.retry_after)
            else:
                return getattr(result, "message_id", None)
        return None  # недостижимо
