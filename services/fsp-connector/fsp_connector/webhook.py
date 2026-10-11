"""Публичный вебхук ФСП/мока: `POST /integrations/fsp/webhook`.

Подпись `X-Signature: sha256=<hex(HMAC(secret, body))>`; идемпотентность по `event_id`
(`webhook_log`). Результат — инкрементальная синхронизация привязанного участника
(`reason=webhook`), события `fsp.*` уходят в outbox в той же транзакции.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Header, Request
from fsp_contracts.fsp import FspWebhook
from fsp_platform.app import ProblemError
from fsp_platform.db import session_scope
from fsp_platform.locks import redis_lock
from pydantic import ValidationError
from sqlalchemy import select

from fsp_connector.models import FspLink, WebhookLog

log = structlog.get_logger()
LOCK_TTL = 120

router = APIRouter(prefix="/integrations/fsp")


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def signature_ok(secret: str, body: bytes, header: str | None) -> bool:
    return bool(header) and hmac.compare_digest(sign(secret, body), header or "")


@router.post("/webhook")
async def receive(request: Request, x_signature: str | None = Header(default=None)) -> dict:
    body = await request.body()
    app = request.app
    if not signature_ok(app.state.settings.fsp_webhook_secret, body, x_signature):
        raise ProblemError(401, "invalid_signature", "Неверная подпись вебхука")
    try:
        event = FspWebhook.model_validate_json(body)
    except ValidationError as exc:
        raise ProblemError(422, "validation_error", "Некорректное тело вебхука") from exc

    factory = app.state.session_factory
    async with session_scope(factory) as s:
        row = await s.get(WebhookLog, event.event_id)
        if row is not None and row.processed_at is not None:
            return {"status": "duplicate"}
        if row is None:
            s.add(
                WebhookLog(
                    event_id=event.event_id,
                    type=event.type,
                    payload=event.model_dump(mode="json"),
                )
            )

    # ошибка синхронизации -> 5xx, строка без processed_at: повторная доставка отработает заново
    async with session_scope(factory) as s:
        candidate_id = await s.scalar(
            select(FspLink.candidate_id).where(FspLink.participant_id == event.participant_id)
        )
        synced = False
        if candidate_id is not None:
            async with redis_lock(app.state.redis, f"fsp_sync:{candidate_id}", LOCK_TTL):
                synced = await app.state.sync.sync_candidate(s, candidate_id, reason="webhook")
        else:
            log.info("fsp_webhook_unknown_participant", event_id=event.event_id)
        row = await s.get(WebhookLog, event.event_id)
        if row is not None:
            row.processed_at = datetime.now(UTC)
    return {"status": "processed", "synced": synced}
