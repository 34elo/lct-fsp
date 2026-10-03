"""Обработчики core.ingest: результат разбора резюме от ml (messaging.md §3)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

import structlog
from fsp_contracts import Envelope
from fsp_contracts.events import MlResumeResult
from fsp_contracts.ui import ResumeStatus, UiMessage, new_ui_message
from fsp_platform.messaging import Consumer, idempotent
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.resumes import service

log = structlog.get_logger()

UiPublish = Callable[[UiMessage], Awaitable[None]]


def register(
    consumers: Mapping[str, Consumer],
    session_factory: async_sessionmaker[AsyncSession],
    ui_publish: UiPublish | None = None,
) -> None:
    @consumers["core.ingest"].on("ml.resume.completed", "ml.resume.failed")
    @idempotent(session_factory, "resumes.ml_result")
    async def on_resume_result(envelope: Envelope, session: AsyncSession) -> None:
        res = MlResumeResult.model_validate(envelope.payload)
        failed = envelope.type == "ml.resume.failed" or res.parsed is None
        resume = await service.apply_result(
            session,
            res.resume_id,
            res.candidate_id,
            None if failed else res.parsed,
            (res.error or "unknown") if failed else None,
        )
        if resume is None or ui_publish is None:
            return
        # UI: «вот что я понял» или причина отказа (api.md §4)
        event = "resume.failed" if failed else "resume.parsed"
        msg = new_ui_message(
            res.candidate_id, event, ResumeStatus(resume_id=res.resume_id, reason=res.error)
        )
        try:
            await ui_publish(msg)
        except Exception:  # SSE — удобство, а не часть транзакции: не роняем обработчик
            log.warning("ui_publish_failed", event=event)
