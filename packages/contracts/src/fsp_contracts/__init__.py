"""Контракты между сервисами v1. Ломающее изменение — новый schema_version или новое имя.

Модули: `enums`, `events` (обменник events), `commands` (обменник commands),
`ui` (SSE, обменник ui), `notify` (notify.telegram), `fsp` (DTO ФСП), `ml` (DTO ML),
`registry` (типизированные конверты), `asyncapi` (каталог AsyncAPI).
"""

from fsp_contracts.envelope import Envelope, new_envelope
from fsp_contracts.registry import (
    UnknownMessageType,
    new_command,
    new_event,
    parse_payload,
    payload_model,
)

__all__ = [
    "Envelope",
    "UnknownMessageType",
    "new_command",
    "new_envelope",
    "new_event",
    "parse_payload",
    "payload_model",
]
