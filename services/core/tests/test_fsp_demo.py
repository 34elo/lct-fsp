"""Демо-кнопки ФСП: только fsp_admin и только при DEMO_MODE."""

import sqlite3

from core_helpers import register


class FakeConnector:
    def __init__(self):
        self.calls = []

    async def demo_create_result(self):
        self.calls.append("create")

    async def demo_reset(self):
        self.calls.append("reset")


def admin(api):
    h = register(api, "employer")
    with sqlite3.connect(api.db_path) as con:
        con.execute("update users set role='fsp_admin'")
    return h


def test_demo_requires_fsp_admin(api):
    for path in ("/admin/demo/fsp-result", "/admin/demo/reset"):
        assert api.post(path).status_code == 401
        cand = register(api, "candidate")
        assert api.post(path, headers=cand).status_code == 403


def test_demo_disabled_by_default(api):
    api.app.state.fsp_client = FakeConnector()
    h = admin(api)
    for path in ("/admin/demo/fsp-result", "/admin/demo/reset"):
        r = api.post(path, headers=h)
        assert r.status_code == 400
        assert r.json()["code"] == "demo_disabled"
    assert api.app.state.fsp_client.calls == []


def test_demo_enabled_calls_connector(api):
    fake = api.app.state.fsp_client = FakeConnector()
    api.app.state.settings.demo_mode = True
    h = admin(api)
    assert api.post("/admin/demo/fsp-result", headers=h).status_code == 202
    assert api.post("/admin/demo/reset", headers=h).status_code == 202
    assert fake.calls == ["create", "reset"]
