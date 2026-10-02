"""Контракты между сервисами. Ломающее изменение — новый schema_version или новое имя."""

from fsp_contracts.envelope import Envelope, new_envelope

__all__ = ["Envelope", "new_envelope"]
