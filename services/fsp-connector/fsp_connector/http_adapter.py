"""HttpFspAdapter: REST-источник ФСП (наш мок, вероятно и мок организаторов)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any
from urllib.parse import urlencode

import httpx
from fsp_contracts.fsp import (
    FspCompetition,
    FspOAuthIdentity,
    FspParticipant,
    FspParticipantBrief,
    FspRank,
    FspResult,
    FspStandingRow,
    FspTeam,
    MaskedContact,
)
from pydantic import ValidationError

from fsp_connector.errors import FspAuthError, FspBadResponse, FspNotFound
from fsp_connector.mappings import MOCK, Mapping
from fsp_connector.resilience import CircuitBreaker, Transient, call_with_retry


class HttpFspAdapter:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        mapping: Mapping = MOCK,
        *,
        client: httpx.AsyncClient | None = None,
        public_url: str | None = None,
        oauth_client_id: str = "fsp-career",
        oauth_redirect_uri: str = "",
        timeout: float = 10.0,
        retries: int = 3,
        retry_base: float = 0.2,
        breaker: CircuitBreaker | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.public_url = (public_url or base_url).rstrip("/")
        self.api_key = api_key
        self.mapping = mapping
        self.oauth_client_id = oauth_client_id
        self.oauth_redirect_uri = oauth_redirect_uri
        self.retries = retries
        self.retry_base = retry_base
        self.breaker = breaker or CircuitBreaker()
        self._sleep = sleep
        self._client = client or httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------ транспорт
    async def _once(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None,
        json: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> Any:
        try:
            resp = await self._client.request(
                method, path, params=params, json=json, headers=headers
            )
        except httpx.TransportError as exc:  # таймауты, обрыв, DNS
            raise Transient(type(exc).__name__) from exc
        if resp.status_code >= 500 or resp.status_code == 429:
            raise Transient(f"http {resp.status_code}")
        if resp.status_code == 404:
            raise FspNotFound(path)
        if resp.status_code in (401, 403):
            raise FspAuthError(f"http {resp.status_code}")
        if resp.status_code >= 400:
            raise FspBadResponse(f"http {resp.status_code}")
        try:
            return resp.json()
        except ValueError as exc:
            raise FspBadResponse("не JSON") from exc

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        hdrs = headers if headers is not None else {"X-Api-Key": self.api_key}
        real_path = self.mapping.paths.get(path, path)
        clean = {
            k: v.isoformat() if isinstance(v, date) else v
            for k, v in (params or {}).items()
            if v is not None
        }
        extra: dict[str, Any] = {"sleep": self._sleep} if self._sleep else {}
        return await call_with_retry(
            lambda: self._once(method, real_path, clean or None, json, hdrs),
            breaker=self.breaker,
            retries=self.retries,
            base_delay=self.retry_base,
            **extra,
        )

    @staticmethod
    def _norm(fn: Callable[[Any], Any], raw: Any) -> Any:
        try:
            return fn(raw)
        except (ValidationError, KeyError, TypeError, AttributeError) as exc:
            raise FspBadResponse(type(exc).__name__) from exc

    # ------------------------------------------------------------ данные
    async def get_participant(self, participant_id: str) -> FspParticipant:
        raw = await self._request("GET", f"/api/v1/participants/{participant_id}")
        return self._norm(self.mapping.participant, raw)

    async def find_participant(
        self,
        *,
        email: str | None = None,
        last_name: str | None = None,
        birth_date: date | None = None,
    ) -> list[FspParticipantBrief]:
        raw = await self._request(
            "GET", "/api/v1/participants", params={"email": email, "last_name": last_name}
        )
        found = [self._norm(self.mapping.brief, r) for r in raw]
        if birth_date is not None:  # мок не фильтрует по дате: сверяем по году
            found = [f for f in found if f.birth_year in (None, birth_date.year)]
        return found

    async def get_results(self, participant_id: str, since: date | None = None) -> list[FspResult]:
        raw = await self._request(
            "GET", f"/api/v1/participants/{participant_id}/results", params={"since": since}
        )
        return [self._norm(self.mapping.result, r) for r in raw]

    async def get_ranks(self, participant_id: str) -> list[FspRank]:
        return (await self.get_participant(participant_id)).ranks

    async def get_competitions(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        discipline: str | None = None,
    ) -> list[FspCompetition]:
        raw = await self._request(
            "GET",
            "/api/v1/competitions",
            params={"from": date_from, "to": date_to, "discipline": discipline},
        )
        return [self._norm(self.mapping.competition, r) for r in raw]

    async def get_standings(self, competition_id: str) -> list[FspStandingRow]:
        raw = await self._request("GET", f"/api/v1/competitions/{competition_id}/standings")
        return [self._norm(self.mapping.standing, r) for r in raw]

    async def get_team(self, team_id: str) -> FspTeam:
        raw = await self._request("GET", f"/api/v1/teams/{team_id}")
        return self._norm(self.mapping.team, raw)

    # ------------------------------------------------------------ верификация
    async def send_verification_code(self, participant_id: str) -> MaskedContact:
        raw = await self._request(
            "POST", "/api/v1/verification/send", json={"participant_id": participant_id}
        )
        return self._norm(MaskedContact.model_validate, raw)

    async def check_verification_code(self, participant_id: str, code: str) -> bool:
        raw = await self._request(
            "POST",
            "/api/v1/verification/check",
            json={"participant_id": participant_id, "code": code},
        )
        return bool(raw.get("ok"))

    # ------------------------------------------------------------ OAuth (PKCE S256)
    def authorize_url(self, state: str, code_challenge: str) -> str:
        query = urlencode(
            {
                "client_id": self.oauth_client_id,
                "redirect_uri": self.oauth_redirect_uri,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{self.public_url}/oauth/authorize?{query}"

    async def exchange_code(self, code: str, code_verifier: str) -> FspOAuthIdentity:
        try:
            token = await self._request(
                "POST",
                "/oauth/token",
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": code_verifier,
                    "redirect_uri": self.oauth_redirect_uri,
                    "client_id": self.oauth_client_id,
                },
                headers={},
            )
        except FspBadResponse as exc:  # 400 invalid_grant: код просрочен или уже использован
            raise FspAuthError("invalid_grant") from exc
        access = token.get("access_token") if isinstance(token, dict) else None
        if not access:
            raise FspBadResponse("нет access_token")
        raw = await self._request(
            "GET", "/oauth/userinfo", headers={"Authorization": f"Bearer {access}"}
        )
        return self._norm(self.mapping.identity, raw)
