import json
from datetime import date
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from fsp_contracts.fsp import FspWebhook
from fsp_mock.config import Settings
from fsp_mock.main import build_app, pkce_s256, sign

KEY = {"X-Api-Key": "k"}


def make(webhook_url: str | None = None):
    settings = Settings(fsp_mock_api_key="k", fsp_webhook_url=webhook_url, fsp_webhook_secret="s")
    app = build_app(settings)
    return app, TestClient(app, follow_redirects=False)


def test_api_key_required():
    _, c = make()
    assert c.get("/api/v1/participants/p-anya").status_code == 401
    assert c.get("/api/v1/participants/p-anya", headers={"X-Api-Key": "bad"}).status_code == 401


def test_participant_masked_and_not_found():
    _, c = make()
    r = c.get("/api/v1/participants/p-anya", headers=KEY).json()
    assert r["last_name"] == "Волкова" and "@" in r["email_masked"]
    assert r["email_masked"].startswith("a***@")
    assert r["ranks"][0]["rank"] == "rank_2"
    nf = c.get("/api/v1/participants/nope", headers=KEY)
    assert nf.status_code == 404 and nf.json()["code"] == "not_found"


def test_find_and_results_since():
    _, c = make()
    found = c.get("/api/v1/participants", params={"last_name": "волкова"}, headers=KEY).json()
    assert [f["id"] for f in found] == ["p-anya"]
    assert found[0]["full_name_masked"] == "В*** А."
    assert c.get("/api/v1/participants", headers=KEY).status_code == 422
    res = c.get("/api/v1/participants/p-anya/results", headers=KEY).json()
    assert res[0]["team_role"] == "captain" and res[0]["place"] == 2
    assert (
        c.get(
            "/api/v1/participants/p-anya/results", params={"since": date(2100, 1, 1)}, headers=KEY
        ).json()
        == []
    )


def test_competitions_filters_standings_team():
    _, c = make()
    allc = c.get("/api/v1/competitions", headers=KEY).json()
    up = c.get("/api/v1/competitions", params={"status": "announced"}, headers=KEY).json()
    assert len(allc) == 15 and all(x["status"] == "announced" for x in up)
    prod = c.get("/api/v1/competitions", params={"discipline": "product"}, headers=KEY).json()
    assert prod and all(x["discipline"] == "product" for x in prod)
    st = c.get("/api/v1/competitions/c-002/standings", headers=KEY).json()
    assert st[0]["team_id"] == "t-north-lights" and "p-anya" in st[0]["participant_ids"]
    team = c.get("/api/v1/teams/t-north-lights", headers=KEY).json()
    assert team["members"][0] == {"participant_id": "p-anya", "role": "captain"}


def test_verification_flow_and_attempt_limit():
    _, c = make()
    sent = c.post("/api/v1/verification/send", json={"participant_id": "p-anya"}, headers=KEY)
    assert sent.json()["channel"] == "email"
    code = c.get("/mock/codes", headers=KEY).json()[-1]["code"]
    wrong = {"participant_id": "p-anya", "code": "000000" if code != "000000" else "111111"}
    assert c.post("/api/v1/verification/check", json=wrong, headers=KEY).json() == {"ok": False}
    ok = c.post(
        "/api/v1/verification/check", json={"participant_id": "p-anya", "code": code}, headers=KEY
    )
    assert ok.json() == {"ok": True}
    # код одноразовый
    again = c.post(
        "/api/v1/verification/check", json={"participant_id": "p-anya", "code": code}, headers=KEY
    )
    assert again.json() == {"ok": False}

    c.post("/api/v1/verification/send", json={"participant_id": "p-dima"}, headers=KEY)
    code = c.get("/mock/codes", headers=KEY).json()[-1]["code"]
    bad = {"participant_id": "p-dima", "code": "x"}
    for _ in range(5):
        c.post("/api/v1/verification/check", json=bad, headers=KEY)
    good = {"participant_id": "p-dima", "code": code}
    assert c.post("/api/v1/verification/check", json=good, headers=KEY).json() == {"ok": False}


def _authorize(c, verifier="v" * 50, redirect="http://app.test/cb"):
    params = {
        "client_id": "x",
        "redirect_uri": redirect,
        "state": "st1",
        "code_challenge": pkce_s256(verifier),
        "code_challenge_method": "S256",
    }
    page = c.get("/oauth/authorize", params=params)
    assert page.status_code == 200 and "Волкова" in page.text
    return c.post("/oauth/authorize", data={**params, "participant_id": "p-anya"})


def test_oauth_pkce_flow():
    _, c = make()
    r = _authorize(c)
    assert r.status_code == 303
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["state"] == ["st1"]
    tok = c.post(
        "/oauth/token",
        data={
            "code": q["code"][0],
            "code_verifier": "v" * 50,
            "redirect_uri": "http://app.test/cb",
        },
    ).json()
    assert tok["token_type"] == "Bearer"
    info = c.get("/oauth/userinfo", headers={"Authorization": f"Bearer {tok['access_token']}"})
    assert info.json()["participant_id"] == "p-anya"
    assert c.get("/oauth/userinfo").status_code == 401


def test_oauth_wrong_verifier_and_code_single_use():
    _, c = make()
    code = parse_qs(urlparse(_authorize(c).headers["location"]).query)["code"][0]
    bad = c.post("/oauth/token", json={"code": code, "code_verifier": "w" * 50})
    assert bad.status_code == 400 and bad.json()["code"] == "invalid_grant"
    # код сгорает даже после неудачной попытки
    again = c.post("/oauth/token", json={"code": code, "code_verifier": "v" * 50})
    assert again.status_code == 400


def test_oauth_requires_pkce():
    _, c = make()
    assert c.get("/oauth/authorize", params={"redirect_uri": "http://a/b"}).status_code == 400


def test_oauth_search_by_last_name():
    _, c = make()
    p = {"redirect_uri": "http://a/b", "code_challenge": "x", "q": "орлов"}
    assert "Орлов" in c.get("/oauth/authorize", params=p).text


@pytest.mark.parametrize("deliver", [True, False])
async def test_mock_results_webhook(deliver):
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200 if deliver else 500)

    app, c = make("http://connector.test/integrations/fsp/webhook")
    app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    body = {
        "participant_id": "p-dima",
        "result": {
            "competition_id": "c-004",
            "discipline": "algorithmic",
            "stage": "final",
            "team_role": "individual",
            "place": 1,
            "participants_total": 50,
            "score": 9.0,
            "date": "2026-09-01",
        },
    }
    r = c.post("/mock/results", json=body, headers=KEY)
    assert r.status_code == 200 and r.json()["webhook_delivered"] is deliver
    req = seen[0]
    assert req.headers["x-signature"] == sign("s", req.content)
    hook = FspWebhook.model_validate(json.loads(req.content))
    assert hook.participant_id == "p-dima" and hook.competition_id == "c-004"
    res = c.get("/api/v1/participants/p-dima/results", headers=KEY).json()
    assert any(x["competition_id"] == "c-004" for x in res)
    # повтор того же (competition, stage) заменяет результат, а не дублирует
    c.post("/mock/results", json=body, headers=KEY)
    res = c.get("/api/v1/participants/p-dima/results", headers=KEY).json()
    assert sum(x["competition_id"] == "c-004" for x in res) == 1


def test_mock_results_requires_key_and_known_ids():
    _, c = make()
    assert c.post("/mock/results", json={}).status_code == 401
    body = {
        "participant_id": "p-dima",
        "result": {
            "competition_id": "zzz",
            "discipline": "uav",
            "team_role": "individual",
            "stage": "final",
            "date": "2026-01-01",
        },
    }
    assert c.post("/mock/results", json=body, headers=KEY).status_code == 404
