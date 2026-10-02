"""structlog (JSON) со сквозным correlation_id. ПДн в логи не пишем."""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from uuid import uuid4

import structlog

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_correlation_id(value: str | None = None) -> str:
    cid = value or uuid4().hex
    _correlation_id.set(cid)
    return cid


def _add_correlation_id(_logger, _method, event_dict):
    cid = _correlation_id.get()
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def configure_logging(service: str, level: str = "INFO") -> None:
    logging.basicConfig(stream=sys.stdout, level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_correlation_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.EventRenamer("message"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        cache_logger_on_first_use=False,
    )
    structlog.contextvars.bind_contextvars(service=service)
