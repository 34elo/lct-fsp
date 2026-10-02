"""Типизированная сборка и разбор конвертов по реестрам событий и команд."""

from __future__ import annotations

from pydantic import BaseModel

from fsp_contracts.commands import COMMANDS, CommandSpec
from fsp_contracts.envelope import Envelope, new_envelope
from fsp_contracts.events import EVENTS


class UnknownMessageType(KeyError):
    pass


def payload_model(type: str) -> type[BaseModel]:
    if type in EVENTS:
        return EVENTS[type]
    if type in COMMANDS:
        return COMMANDS[type].model
    raise UnknownMessageType(type)


def _check(type: str, payload: BaseModel) -> None:
    expected = payload_model(type)
    if not isinstance(payload, expected):
        raise TypeError(f"{type}: ожидается {expected.__name__}, получено {type_name(payload)}")


def type_name(obj: object) -> str:
    return obj.__class__.__name__


def new_event(
    type: str, producer: str, payload: BaseModel, *, correlation_id: str | None = None
) -> Envelope:
    if type not in EVENTS:
        raise UnknownMessageType(type)
    _check(type, payload)
    return new_envelope(type, producer, payload, correlation_id=correlation_id)


def new_command(
    type: str, producer: str, payload: BaseModel, *, correlation_id: str | None = None
) -> tuple[Envelope, CommandSpec]:
    """Конверт + спецификация (очередь = routing key, приоритет AMQP)."""
    if type not in COMMANDS:
        raise UnknownMessageType(type)
    _check(type, payload)
    return new_envelope(type, producer, payload, correlation_id=correlation_id), COMMANDS[type]


def parse_payload(envelope: Envelope) -> BaseModel:
    """Payload конверта как pydantic-модель по `type` (ValidationError, если не сходится)."""
    return payload_model(envelope.type).model_validate(envelope.payload)
