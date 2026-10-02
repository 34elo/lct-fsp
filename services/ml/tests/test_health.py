from fastapi.testclient import TestClient
from fsp_ml.config import Settings
from fsp_ml.main import build_app


def test_healthz_fake():
    body = TestClient(build_app(Settings(ml_fake=True))).get("/healthz").json()
    assert body["llm"] == "up" and body["embedder"] == "up" and body["queue_depth"] == 0


def test_healthz_down_without_fake():
    body = TestClient(build_app(Settings(ml_fake=False))).get("/healthz").json()
    assert body["llm"] == "down"
