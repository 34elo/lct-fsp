"""Тонкая обёртка над FastStream (RabbitMQ)."""

from __future__ import annotations

from faststream.rabbit import RabbitBroker, RabbitExchange, RabbitQueue
from fsp_contracts import Envelope

EVENTS_EXCHANGE = RabbitExchange("events", type="topic", durable=True)


def make_broker(url: str) -> RabbitBroker:
    return RabbitBroker(url)


async def publish_envelope(broker: RabbitBroker, envelope: Envelope) -> None:
    """Публикация события в обменник events с routing key = type; persistent, с confirm."""
    await broker.publish(
        envelope.model_dump(mode="json"),
        exchange=EVENTS_EXCHANGE,
        routing_key=envelope.type,
        persist=True,
        correlation_id=envelope.correlation_id,
    )


def durable_queue(name: str, routing_key: str | None = None, **kwargs) -> RabbitQueue:
    return RabbitQueue(name, durable=True, routing_key=routing_key or name, **kwargs)
