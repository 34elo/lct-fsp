"""Точка входа бота: long polling + подписчик очереди `bot.telegram`.

Запуск: `python -m fsp_bot.main`. Нужны TG_BOT_TOKEN и SERVICE_TOKEN_BOT из окружения.
"""

from __future__ import annotations

import asyncio
import contextlib

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from fsp_platform.logging import configure_logging
from fsp_platform.messaging import QUEUES, Consumer, declare_topology, make_broker
from redis.asyncio import Redis

from fsp_bot.config import Settings
from fsp_bot.core_client import CoreClient
from fsp_bot.handlers import build_router
from fsp_bot.limiter import SendLimiter
from fsp_bot.sender import Sender

log = structlog.get_logger()


def build_consumer(sender: Sender) -> Consumer:
    consumer = Consumer(QUEUES["bot.telegram"])
    consumer.on("notify.telegram")(sender.handle)
    return consumer


def make_bot(settings: Settings) -> Bot:
    """Bot с адресом Bot API из настроек: ретранслятор на VPS или api.telegram.org по умолчанию."""
    if not settings.tg_api_base:
        return Bot(settings.tg_bot_token)
    api = TelegramAPIServer.from_base(settings.tg_api_base.rstrip("/"))
    return Bot(settings.tg_bot_token, session=AiohttpSession(api=api))


async def main() -> None:
    settings = Settings()
    configure_logging(settings.service_name, settings.log_level)
    if not settings.tg_bot_token:
        raise SystemExit("TG_BOT_TOKEN не задан")
    bot = make_bot(settings)
    redis = Redis.from_url(settings.redis_url)
    storage = RedisStorage(
        redis,
        key_builder=DefaultKeyBuilder(prefix="fsm"),
        state_ttl=settings.fsm_ttl_seconds,
        data_ttl=settings.fsm_ttl_seconds,
    )
    core = CoreClient(settings.core_url, settings.service_token_bot, timeout=settings.core_timeout)
    limiter = SendLimiter(settings.send_rate_global, settings.send_rate_per_chat)
    sender = Sender(
        bot,
        redis,
        limiter,
        max_retries=settings.send_max_retries,
        map_ttl=settings.message_map_ttl_seconds,
        sent_ttl=settings.sent_ttl_seconds,
    )
    broker = make_broker(settings.rabbitmq_url)
    build_consumer(sender).attach(broker)
    dp = Dispatcher(storage=storage)
    dp.include_router(build_router(core))
    await broker.connect()
    await declare_topology(broker)
    await broker.start()
    log.info("bot_started")
    try:
        await dp.start_polling(bot)
    finally:
        await broker.stop()
        await core.aclose()
        await bot.session.close()
        await redis.aclose()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
