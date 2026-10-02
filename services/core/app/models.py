"""Реестр моделей для Alembic: импортируй сюда модули с таблицами core."""

from fsp_platform.db import Base
from fsp_platform.outbox import InboxRecord, OutboxRecord  # noqa: F401

metadata = Base.metadata
