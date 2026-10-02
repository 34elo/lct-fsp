"""RabbitMQ поверх FastStream: топология, публикация, потребители с ретраями и DLQ.

messaging.md §2: обменники `events` (topic), `commands` (direct), `ui` (topic), `dlx` (direct).
Очередь `<q>` → при ошибке копия в `<q>.retry.<5s|30s|2m>` (TTL, затем dead-letter обратно
в `<q>`), счётчик в заголовке `x-retry`; после 3 повторов `nack` → `dlx` → `<q>.dlq`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import structlog
from faststream import AckPolicy
from faststream.rabbit import Channel, ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue
from faststream.rabbit.annotations import RabbitMessage
from fsp_contracts import Envelope
from fsp_contracts.commands import COMMANDS, LLM_MAX_PRIORITY
from fsp_contracts.ui import UiMessage, ui_routing_key
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fsp_platform.db import session_scope
from fsp_platform.logging import set_correlation_id
from fsp_platform.outbox import claim_inbox

log = structlog.get_logger()

EVENTS_EXCHANGE = RabbitExchange("events", type=ExchangeType.TOPIC, durable=True)
COMMANDS_EXCHANGE = RabbitExchange("commands", type=ExchangeType.DIRECT, durable=True)
UI_EXCHANGE = RabbitExchange("ui", type=ExchangeType.TOPIC, durable=True)
DLX_EXCHANGE = RabbitExchange("dlx", type=ExchangeType.DIRECT, durable=True)
EXCHANGES = (EVENTS_EXCHANGE, COMMANDS_EXCHANGE, UI_EXCHANGE, DLX_EXCHANGE)

RETRY_HEADER = "x-retry"
# (метка в имени очереди, задержка в мс); число элементов = число повторов до DLQ
RETRY_DELAYS: tuple[tuple[str, int], ...] = (("5s", 5_000), ("30s", 30_000), ("2m", 120_000))


@dataclass(frozen=True)
class QueueSpec:
    """Очередь, её привязки и параметры. Один источник для объявления и подписки."""

    name: str
    exchange: RabbitExchange
    bindings: tuple[str, ...]
    prefetch: int
    max_priority: int | None = None
    retry_delays: tuple[tuple[str, int], ...] = RETRY_DELAYS

    @property
    def dlq(self) -> str:
        return f"{self.name}.dlq"

    def retry_queue(self, attempt: int) -> str:
        return f"{self.name}.retry.{self.retry_delays[attempt][0]}"

    def arguments(self) -> dict[str, Any]:
        args: dict[str, Any] = {
            "x-dead-letter-exchange": DLX_EXCHANGE.name,
            "x-dead-letter-routing-key": self.name,
        }
        if self.max_priority:
            args["x-max-priority"] = self.max_priority
        return args

    def rabbit_queue(self) -> RabbitQueue:
        return RabbitQueue(self.name, durable=True, arguments=self.arguments())


def _commands(name: str, prefetch: int, max_priority: int | None = None) -> QueueSpec:
    """Команды: routing key в `commands` = имя очереди (messaging.md §2.4)."""
    return QueueSpec(name, COMMANDS_EXCHANGE, (name,), prefetch, max_priority)


QUEUES: dict[str, QueueSpec] = {
    q.name: q
    for q in (
        QueueSpec(
            "core.ingest",
            EVENTS_EXCHANGE,
            ("fsp.results.imported", "fsp.competitions.updated", "fsp.linked", "ml.#"),
            8,
        ),
        QueueSpec(
            "core.handlers",
            EVENTS_EXCHANGE,
            (
                "evidence.changed",
                "skills.profile.updated",
                "vacancy.#",
                "offer.#",
                "candidate.#",
                "taxonomy.updated",
                "matches.ready",
            ),
            8,
        ),
        _commands("core.recompute", 4),
        _commands("core.match", 4),
        _commands("core.jobs", 2),
        QueueSpec("core.analytics", EVENTS_EXCHANGE, ("#",), 20),
        _commands("ml.llm", 1, LLM_MAX_PRIORITY),
        _commands("ml.code", 2),
        _commands("fsp.sync", 4),
        _commands("bot.telegram", 10),
    )
}


def make_broker(url: str) -> RabbitBroker:
    """Канал по умолчанию с publisher confirms: publish ждёт подтверждения брокера."""
    return RabbitBroker(url)


async def declare_topology(broker: RabbitBroker, queues: Iterable[QueueSpec] | None = None) -> None:
    """Идемпотентно объявляет обменники, очереди, очереди задержки и DLQ (после connect)."""
    exchanges = {ex.name: await broker.declare_exchange(ex) for ex in EXCHANGES}
    for spec in QUEUES.values() if queues is None else queues:
        queue = await broker.declare_queue(spec.rabbit_queue())
        for key in spec.bindings:
            await queue.bind(exchanges[spec.exchange.name], routing_key=key)
        dlq = await broker.declare_queue(RabbitQueue(spec.dlq, durable=True))
        await dlq.bind(exchanges[DLX_EXCHANGE.name], routing_key=spec.name)
        for attempt, (_, ttl) in enumerate(spec.retry_delays):
            await broker.declare_queue(
                RabbitQueue(
                    spec.retry_queue(attempt),
                    durable=True,
                    arguments={
                        "x-message-ttl": ttl,
                        "x-dead-letter-exchange": "",
                        "x-dead-letter-routing-key": spec.name,
                    },
                )
            )


def route(envelope: Envelope) -> tuple[RabbitExchange, str, int | None]:
    """Команда → `commands` (ключ = очередь, приоритет из реестра); иначе событие → `events`."""
    spec = COMMANDS.get(envelope.type)
    if spec is not None:
        return COMMANDS_EXCHANGE, spec.queue, spec.priority
    return EVENTS_EXCHANGE, envelope.type, None


async def publish_envelope(broker: RabbitBroker, envelope: Envelope) -> None:
    """Persistent-публикация с ожиданием publisher confirm (Nack → исключение)."""
    exchange, routing_key, priority = route(envelope)
    await broker.publish(
        envelope.model_dump(mode="json"),
        exchange=exchange,
        routing_key=routing_key,
        persist=True,
        priority=priority,
        message_id=str(envelope.message_id),
        message_type=envelope.type,
        correlation_id=envelope.correlation_id,
    )


async def publish_ui(broker: RabbitBroker, message: UiMessage) -> None:
    """Сообщение для SSE: обменник `ui`, ключ `ui.user.<id>`, без персистентности."""
    await broker.publish(
        message.model_dump(mode="json"),
        exchange=UI_EXCHANGE,
        routing_key=ui_routing_key(message.user_id),
    )


def durable_queue(name: str, routing_key: str | None = None, **kwargs) -> RabbitQueue:
    return RabbitQueue(name, durable=True, routing_key=routing_key or name, **kwargs)


Handler = Callable[[Envelope], Awaitable[None]]


@dataclass
class Consumer:
    """Подписчик очереди: разбор конверта, диспетчеризация по `type`, ретраи и DLQ.

    Несколько обработчиков на один тип допустимы: при ретрае повторяются все,
    поэтому каждый обязан быть идемпотентным (см. `idempotent`).
    """

    spec: QueueSpec
    handlers: dict[str, list[Handler]] = field(default_factory=lambda: defaultdict(list))

    def on(self, *types: str) -> Callable[[Handler], Handler]:
        def deco(fn: Handler) -> Handler:
            for t in types:
                self.handlers[t].append(fn)
            return fn

        return deco

    async def dispatch(self, envelope: Envelope) -> None:
        handlers = self.handlers.get(envelope.type)
        if not handlers:
            log.debug("message_skipped", queue=self.spec.name, type=envelope.type)
            return
        for handler in handlers:
            await handler(envelope)

    def attach(self, broker: RabbitBroker) -> None:
        spec = self.spec

        async def consume(body: Any, message: RabbitMessage) -> None:
            try:
                envelope = Envelope.model_validate(body)
            except ValidationError:
                log.error("message_invalid", queue=spec.name)
                await message.reject()  # битый конверт → сразу в DLQ
                return
            set_correlation_id(envelope.correlation_id)
            try:
                await self.dispatch(envelope)
            except Exception as exc:
                await _retry_or_dead_letter(broker, spec, message, envelope, exc)
            else:
                await message.ack()

        consume.__name__ = f"consume_{spec.name.replace('.', '_')}"
        broker.subscriber(
            spec.rabbit_queue(),
            channel=Channel(prefetch_count=spec.prefetch),
            ack_policy=AckPolicy.MANUAL,
        )(consume)


async def _retry_or_dead_letter(
    broker: RabbitBroker,
    spec: QueueSpec,
    message: RabbitMessage,
    envelope: Envelope,
    exc: Exception,
) -> None:
    attempt = int(message.headers.get(RETRY_HEADER, 0) or 0)
    fields = dict(queue=spec.name, type=envelope.type, attempt=attempt, error=type(exc).__name__)
    if attempt >= len(spec.retry_delays):
        log.error("message_dead_lettered", **fields)
        await message.nack(requeue=False)
        return
    log.warning("message_retry", **fields)
    raw = message.raw_message
    try:
        await broker.publish(
            message.body,
            queue=spec.retry_queue(attempt),
            persist=True,
            headers={**message.headers, RETRY_HEADER: attempt + 1},
            priority=raw.priority,
            content_type=message.content_type,
            message_id=message.message_id,
            message_type=raw.type,
            correlation_id=message.correlation_id,
        )
    except Exception:
        log.exception("message_retry_publish_failed", queue=spec.name)
        await message.nack(requeue=False)
        return
    await message.ack()


def idempotent(
    session_factory: async_sessionmaker[AsyncSession], handler: str
) -> Callable[[Callable[[Envelope, AsyncSession], Awaitable[None]]], Handler]:
    """Обработчик в одной транзакции с записью inbox: повторная доставка — без эффекта."""

    def deco(fn: Callable[[Envelope, AsyncSession], Awaitable[None]]) -> Handler:
        async def wrapper(envelope: Envelope) -> None:
            async with session_scope(session_factory) as session:
                if not await claim_inbox(session, envelope.message_id, handler):
                    log.info("message_duplicate", handler=handler, type=envelope.type)
                    return
                await fn(envelope, session)

        wrapper.__name__ = handler
        return wrapper

    return deco
