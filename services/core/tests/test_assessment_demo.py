"""Вау-экраны питча — `/admin/demo/two-worlds` и `/admin/demo/llm-exam`."""

import json
import sqlite3
import uuid

import pytest
from core_helpers import PASSWORD, register

HDR = "Authorization"


def _admin(api) -> dict[str, str]:
    email = f"root-{uuid.uuid4().hex[:6]}@example.test"
    r = api.post("/auth/register", json={"email": email, "password": PASSWORD, "role": "candidate"})
    with sqlite3.connect(api.db_path) as con:
        con.execute("update users set role='fsp_admin' where email=?", (email,))
    return {HDR: f"Bearer {r.json()['access_token']}"}


@pytest.mark.parametrize("path", ["/admin/demo/two-worlds", "/admin/demo/llm-exam"])
def test_demo_requires_admin(api, path):
    assert api.get(path).status_code == 401
    assert api.get(path, headers=register(api, "candidate")).status_code == 403
    assert api.get(path, headers=register(api, "employer")).status_code == 403


def test_two_worlds_same_shape_different_domains(api):
    adm = _admin(api)
    r = api.get("/admin/demo/two-worlds", headers=adm)
    assert r.status_code == 200, r.text
    body = r.json()
    a, b = body["worlds"]
    assert body["same_shape"] is True and a["scale"] == b["scale"]
    assert a["domain"] != b["domain"] and a["company"] != b["company"] and a["stem"] != b["stem"]
    assert "key" not in json.dumps(body) and body["family"] in body["choices"]
    assert api.get("/admin/demo/two-worlds", headers=adm).json() == body  # детерминировано


def test_two_worlds_other_family_and_errors(api):
    adm = _admin(api)
    q = "?family=kpi_anomaly_day&seed=3&domains=edtech&domains=rag_service"
    body = api.get("/admin/demo/two-worlds" + q, headers=adm).json()
    assert [w["domain"] for w in body["worlds"]] == ["edtech", "rag_service"]
    assert all(w["options"] and len(w["options"]) == 4 for w in body["worlds"])
    assert api.get("/admin/demo/two-worlds?family=nope", headers=adm).status_code == 404
    assert api.get("/admin/demo/two-worlds?domains=edtech", headers=adm).status_code == 422
    same = "?domains=edtech&domains=edtech"
    assert api.get("/admin/demo/two-worlds" + same, headers=adm).status_code == 422


def test_llm_exam_without_report_is_honest(api, monkeypatch, tmp_path):
    monkeypatch.setenv("EVAL_ASSESSMENT_REPORT", str(tmp_path / "none.json"))
    body = api.get("/admin/demo/llm-exam", headers=_admin(api)).json()
    assert body["report"] is None and body["bank"]["families"] == 0 and body["bank"]["top"] == []


def test_llm_exam_reads_eval_report(api, monkeypatch, tmp_path):
    rep = tmp_path / "report.json"
    rep.write_text(
        json.dumps(
            {
                "seed": 42,
                "bank": {"families": 300, "anchors": 30},
                "metrics": {"ai_solvable_share": 0.4633},
                "llm": {"middle": {"flagged_share": 0.9, "granted": {"junior": 13, "middle": 11}}},
            }
        )
    )
    monkeypatch.setenv("EVAL_ASSESSMENT_REPORT", str(rep))
    r = api.get("/admin/demo/llm-exam", headers=_admin(api)).json()["report"]
    assert r["simulation"] is True and r["seed"] == 42 and r["ai_solvable_share"] == 0.4633
    assert r["rows"] == [
        {"declared": "middle", "flagged_share": 0.9, "granted": {"junior": 13, "middle": 11}}
    ]


def test_llm_exam_bad_report_is_ignored(api, monkeypatch, tmp_path):
    rep = tmp_path / "report.json"
    rep.write_text("{не json")
    monkeypatch.setenv("EVAL_ASSESSMENT_REPORT", str(rep))
    assert api.get("/admin/demo/llm-exam", headers=_admin(api)).json()["report"] is None
