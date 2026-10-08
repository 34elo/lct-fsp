"""Контрактные тесты HttpFspAdapter на наш fsp-mock (in-process, без сети)."""

import base64
import hashlib
from datetime import date
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fsp_connector.errors import FspAuthError, FspNotFound
from fsp_connector.http_adapter import HttpFspAdapter
from fsp_connector.port import FspPort


def test_adapter_satisfies_port(adapter):
    port: FspPort = adapter
    assert port is adapter


async def test_participant_and_ranks(adapter):
    p = await adapter.get_participant("p-anya")
    assert p.last_name == "Волкова" and p.email_masked.startswith("a***@")
    assert [r.rank.value for r in await adapter.get_ranks("p-anya")] == ["rank_2"]


async def test_not_found(adapter):
    with pytest.raises(FspNotFound):
        await adapter.get_participant("nope")


async def test_wrong_api_key(mock_app):
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=mock_app), base_url="http://m")
    bad = HttpFspAdapter("http://m", "wrong", client=client)
    with pytest.raises(FspAuthError):
        await bad.get_participant("p-anya")


async def test_find_participant(adapter):
    found = await adapter.find_participant(last_name="волкова")
    assert [f.id for f in found] == ["p-anya"]
    assert await adapter.find_participant(last_name="волкова", birth_date=date(1900, 1, 1)) == []


async def test_results_since(adapter):
    allr = await adapter.get_results("p-anya")
    assert allr and all(r.date for r in allr)
    newest = max(r.date for r in allr)
    assert [r.date for r in await adapter.get_results("p-anya", since=newest)] == [newest]
    assert await adapter.get_results("p-anya", since=date(2100, 1, 1)) == []


async def test_competitions_filter(adapter):
    allc = await adapter.get_competitions()
    assert len(allc) >= 10
    prod = await adapter.get_competitions(discipline="product")
    assert prod and all(c.discipline.value == "product" for c in prod)
    narrow = await adapter.get_competitions(date_from=date(2100, 1, 1))
    assert narrow == []


async def test_team_and_standings(adapter):
    team_id = next(r.team_id for r in await adapter.get_results("p-anya") if r.team_id)
    team = await adapter.get_team(team_id)
    assert any(m.participant_id == "p-anya" for m in team.members)
    cid = (await adapter.get_results("p-anya"))[0].competition_id
    assert isinstance(await adapter.get_standings(cid), list)
    with pytest.raises(FspNotFound):
        await adapter.get_team("nope")


async def test_verification_roundtrip(adapter, mock_store):
    masked = await adapter.send_verification_code("p-anya")
    assert masked.channel == "email" and "***" in masked.masked
    assert await adapter.check_verification_code("p-anya", "not-a-code") is False
    assert await adapter.check_verification_code("p-anya", mock_store.codes[-1]["code"]) is True


async def test_oauth_pkce_flow(adapter, mock_app):
    verifier = "v" * 50
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    url = adapter.authorize_url("st1", challenge)
    assert url.startswith("https://mock.example/oauth/authorize?")
    q = parse_qs(urlparse(url).query)
    assert q["state"] == ["st1"] and q["code_challenge_method"] == ["S256"]
    # пользователь выбирает участника на странице мока
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mock_app), base_url="http://mock"
    ) as browser:
        r = await browser.post(
            "/oauth/authorize",
            data={
                "participant_id": "p-anya",
                "redirect_uri": q["redirect_uri"][0],
                "code_challenge": challenge,
                "state": "st1",
            },
        )
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    ident = await adapter.exchange_code(code, verifier)
    assert ident.participant_id == "p-anya" and "Волкова" in (ident.full_name or "")
    with pytest.raises(FspAuthError):  # код одноразовый
        await adapter.exchange_code(code, verifier)
