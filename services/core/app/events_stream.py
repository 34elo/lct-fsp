"""SSE `/events/stream`: раздаёт сообщения `ui.user.<id>` открытым соединениям.

Каждый экземпляр core-api держит свою эксклюзивную auto-delete очередь `ui.<instance>`,
привязанную к обменнику `ui` по `ui.user.*`. Сообщение, пришедшее в очередь,
кладётся в память всех соединений этого пользователя на этом экземпляре.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from faststream.rabbit import RabbitQueue
from fsp_contracts.ui import UiMessage
from fsp_platform.app import ProblemError
from fsp_platform.jwt import TokenError, decode_token
from fsp_platform.messaging import UI_EXCHANGE, make_broker

log = structlog.get_logger()

ACCESS_COOKIE = "access_token"
QUEUE_SIZE = 100
RETRY_MS = 3000


class UiHub:
    """Соединения SSE по пользователям + подписка на очередь `ui.<instance>`."""

    def __init__(self, rabbitmq_url: str | None = None, instance: str | None = None):
        self.instance = instance or uuid.uuid4().hex[:12]
        self._url = rabbitmq_url
        self._broker = None
        self._conns: dict[str, set[asyncio.Queue[tuple[int, str, dict]]]] = defaultdict(set)
        self._seq = 0

    @property
    def queue_name(self) -> str:
        return f"ui.{self.instance}"

    def subscribe(self, user_id: UUID | str) -> asyncio.Queue[tuple[int, str, dict]]:
        q: asyncio.Queue[tuple[int, str, dict]] = asyncio.Queue(QUEUE_SIZE)
        self._conns[str(user_id)].add(q)
        return q

    def unsubscribe(self, user_id: UUID | str, q: asyncio.Queue) -> None:
        conns = self._conns.get(str(user_id))
        if conns:
            conns.discard(q)
            if not conns:
                del self._conns[str(user_id)]

    def connections(self) -> int:
        return sum(len(c) for c in self._conns.values())

    def dispatch(self, message: UiMessage) -> int:
        """Раздаёт сообщение соединениям пользователя; переполненной очереди роняем старое."""
        self._seq += 1
        item = (self._seq, message.event, message.data)
        delivered = 0
        for q in self._conns.get(str(message.user_id), ()):
            if q.full():
                q.get_nowait()
            q.put_nowait(item)
            delivered += 1
        return delivered

    async def start(self) -> None:
        if not self._url:
            return
        broker = make_broker(self._url)

        async def on_ui(body: Any) -> None:
            try:
                message = UiMessage.model_validate(body)
            except Exception:
                log.warning("ui_message_invalid")
                return
            self.dispatch(message)

        broker.subscriber(
            RabbitQueue(
                self.queue_name,
                exclusive=True,
                auto_delete=True,
                durable=False,
                routing_key="ui.user.*",
            ),
            UI_EXCHANGE,
        )(on_ui)
        await broker.start()
        self._broker = broker
        log.info("ui_hub_started", queue=self.queue_name)

    async def stop(self) -> None:
        if self._broker is not None:
            await self._broker.stop()
            self._broker = None


def _token_from_request(request: Request) -> str | None:
    if token := request.query_params.get("access_token"):
        return token
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(ACCESS_COOKIE)


def current_user_id(request: Request) -> UUID:
    token = _token_from_request(request)
    if not token:
        raise ProblemError(401, "unauthorized", "Нужна авторизация")
    try:
        return UUID(decode_token(request.app.state.settings.jwt_secret, token)["sub"])
    except (TokenError, ValueError, KeyError) as exc:
        raise ProblemError(401, "unauthorized", "Токен недействителен") from exc


def sse_frame(event: str, data: dict, seq: int) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"id: {seq}\nevent: {event}\ndata: {payload}\n\n"


async def event_stream(
    hub: UiHub, user_id: UUID, request: Request | None, heartbeat: float
) -> AsyncIterator[str]:
    q = hub.subscribe(user_id)
    try:
        yield f"retry: {RETRY_MS}\n: connected\n\n"
        while True:
            if request is not None and await request.is_disconnected():
                return
            try:
                seq, event, data = await asyncio.wait_for(q.get(), timeout=heartbeat)
            except TimeoutError:
                yield ": heartbeat\n\n"
                continue
            yield sse_frame(event, data, seq)
    finally:
        hub.unsubscribe(user_id, q)


router = APIRouter(tags=["events"])


@router.get("/events/stream")
async def events_stream(request: Request) -> StreamingResponse:
    user_id = current_user_id(request)
    hub: UiHub = request.app.state.ui_hub
    return StreamingResponse(
        event_stream(hub, user_id, request, request.app.state.settings.sse_heartbeat_seconds),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


__all__ = ["UiHub", "router"]
