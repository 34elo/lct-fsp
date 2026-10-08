from fastapi.testclient import TestClient
from fsp_connector.main import app


def test_healthz():
    assert TestClient(app).get("/healthz").json() == {"status": "ok"}
