from fastapi import HTTPException
from fastapi.testclient import TestClient
from faststream.rabbit import TestRabbitBroker
from fsp_contracts import new_envelope
from fsp_platform.app import ProblemError, create_app
from fsp_platform.messaging import make_broker, publish_envelope


def test_healthz_problem_details_and_request_id():
    app = create_app("t")

    @app.get("/x")
    async def x():
        raise ProblemError(404, "candidate_not_found", "Не найдено")

    @app.get("/y")
    async def y():
        raise HTTPException(404)

    c = TestClient(app)
    assert c.get("/healthz").json() == {"status": "ok"}
    r = c.get("/x", headers={"x-request-id": "rid1"})
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "candidate_not_found" and r.headers["x-request-id"] == "rid1"
    assert c.get("/y").json()["code"] == "not_found"


async def test_publish_envelope_reaches_subscriber():
    from fsp_platform.messaging import EVENTS_EXCHANGE, durable_queue

    broker = make_broker("amqp://guest:guest@localhost:5672/")
    got = []

    @broker.subscriber(durable_queue("q", "offer.sent"), EVENTS_EXCHANGE)
    async def h(msg: dict):
        got.append(msg)

    async with TestRabbitBroker(broker):
        await publish_envelope(broker, new_envelope("offer.sent", "core", {"k": 1}))
    assert got and got[0]["payload"] == {"k": 1}


def test_validation_and_unhandled_are_problem_details():
    from pydantic import BaseModel

    app = create_app("t")

    class Body(BaseModel):
        n: int

    @app.post("/v")
    async def v(b: Body):
        return b

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret pii")

    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/v", json={"n": "x"})
    assert r.status_code == 422 and r.json()["code"] == "validation_error"
    assert r.json()["errors"][0]["field"] == "n"
    r = c.get("/boom")
    assert r.status_code == 500 and r.json()["code"] == "internal_error"
    assert "secret" not in r.text
