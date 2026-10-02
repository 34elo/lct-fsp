import json
from datetime import timedelta
from uuid import uuid4

import fakeredis
import pytest
from app.config import Settings
from app.events_stream import UiHub, event_stream, sse_frame
from app.main import build_app
from fastapi.testclient import TestClient
from fsp_contracts.ui import JobProgress, UiMessage, new_ui_message
from fsp_platform.jwt import encode_token

SECRET = Settings().jwt_secret


def _msg(user_id, pct=10):
    return new_ui_message(
        user_id,
        "job.progress",
        JobProgress(job_id=uuid4(), kind="resume", stage="parse", pct=pct, message="разбираю"),
    )


def test_dispatch_only_to_owner_and_unsubscribe():
    hub = UiHub()
    a, b = uuid4(), uuid4()
    qa1, qa2, qb = hub.subscribe(a), hub.subscribe(a), hub.subscribe(b)
    assert hub.dispatch(_msg(a)) == 2
    assert qa1.qsize() == qa2.qsize() == 1 and qb.empty()
    hub.unsubscribe(a, qa1)
    hub.unsubscribe(a, qa2)
    assert hub.dispatch(_msg(a)) == 0
    assert hub.connections() == 1


def test_overflow_drops_oldest():
    hub = UiHub()
    u = uuid4()
    q = hub.subscribe(u)
    for i in range(101):
        hub.dispatch(_msg(u, pct=min(i, 100)))
    assert q.qsize() == 100
    assert q.get_nowait()[0] == 2  # первое сообщение вытеснено


def test_sse_frame_format():
    frame = sse_frame("job.progress", {"message": "привет"}, 7)
    assert frame == 'id: 7\nevent: job.progress\ndata: {"message":"привет"}\n\n'


async def test_stream_event_heartbeat_and_cleanup():
    hub = UiHub()
    u = uuid4()
    gen = event_stream(hub, u, None, heartbeat=0.05)
    assert (await gen.__anext__()).startswith("retry:")
    assert await gen.__anext__() == ": heartbeat\n\n"
    hub.dispatch(_msg(u))
    frame = await gen.__anext__()
    assert frame.startswith("id: 1\nevent: job.progress\ndata: ")
    assert json.loads(frame.split("data: ")[1])["pct"] == 10
    assert hub.connections() == 1
    await gen.aclose()
    assert hub.connections() == 0


@pytest.fixture
def client(tmp_path):
    app = build_app(
        Settings(database_url=f"sqlite+aiosqlite:///{tmp_path}/c.db", ui_bus_enabled=False)
    )
    with TestClient(app) as c:
        app.state.redis = fakeredis.FakeAsyncRedis()
        yield c


def test_stream_requires_valid_token(client):
    r = client.get("/events/stream")
    assert r.status_code == 401 and r.json()["code"] == "unauthorized"
    r = client.get("/events/stream", params={"access_token": "garbage"})
    assert r.status_code == 401
    expired = encode_token(SECRET, str(uuid4()), "candidate", ttl=timedelta(seconds=-5))
    assert client.get("/events/stream", params={"access_token": expired}).status_code == 401
    not_uuid = encode_token(SECRET, "abc", "candidate")
    assert client.get("/events/stream", params={"access_token": not_uuid}).status_code == 401


def test_stream_endpoint_delivers_event(tmp_path):
    """Настоящий uvicorn: httpx.ASGITransport не стримит, поэтому идём по сокету."""
    import socket
    import threading
    import time

    import httpx
    import uvicorn

    app = build_app(
        Settings(database_url=f"sqlite+aiosqlite:///{tmp_path}/c.db", ui_bus_enabled=False)
    )
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)
    user, other = uuid4(), uuid4()
    token = encode_token(SECRET, str(user), "candidate")
    try:
        with httpx.stream(
            "GET",
            f"http://127.0.0.1:{port}/events/stream",
            params={"access_token": token},
            timeout=5,
        ) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            assert r.headers["cache-control"].startswith("no-cache")
            lines = r.iter_lines()
            assert next(lines) == "retry: 3000"
            hub: UiHub = app.state.ui_hub
            deadline = time.time() + 3
            while hub.connections() < 1 and time.time() < deadline:
                time.sleep(0.02)
            hub.dispatch(_msg(other))
            hub.dispatch(_msg(user, pct=42))
            data = next(line for line in lines if line.startswith("data:"))
            assert json.loads(data[5:])["pct"] == 42
    finally:
        server.should_exit = True
        thread.join(5)
    assert isinstance(_msg(user), UiMessage)
