"""HTTP-клиент core → fsp-connector (api.md §2.9, `Authorization: Service <SERVICE_TOKEN_CORE>`).

Ошибки connector (Problem Details) пробрасываются как есть: статус и машинный `code` сохраняются.
Тела запросов с ПДн (email, коды) не логируются.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from fsp_platform.app import ProblemError


class ConnectorClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Service {token}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _call(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        try:
            r = await self._client.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise ProblemError(503, "fsp_unavailable", "ФСП временно недоступна") from exc
        if r.status_code >= 400:
            try:
                body = r.json()
            except ValueError:
                body = {}
            raise ProblemError(
                r.status_code if r.status_code < 600 else 502,
                str(body.get("code") or "fsp_error"),
                str(body.get("title") or "Ошибка ФСП"),
            )
        return r.json()

    async def authorize_url(self, state: str, code_challenge: str) -> str:
        data = await self._call(
            "GET",
            "/internal/oauth/authorize-url",
            params={"state": state, "code_challenge": code_challenge},
        )
        return str(data["url"])

    async def exchange(self, candidate_id: UUID, code: str, code_verifier: str) -> dict[str, Any]:
        return await self._call(
            "POST",
            "/internal/oauth/exchange",
            json={"candidate_id": str(candidate_id), "code": code, "code_verifier": code_verifier},
        )

    async def link(
        self,
        candidate_id: UUID,
        *,
        participant_id: str | None = None,
        email: str | None = None,
        manual: bool = False,
    ) -> dict[str, Any]:
        return await self._call(
            "POST",
            "/internal/links",
            json={
                "candidate_id": str(candidate_id),
                "participant_id": participant_id,
                "email": email,
                "manual": manual,
            },
        )

    async def verify(self, candidate_id: UUID, code: str) -> dict[str, Any]:
        return await self._call(
            "POST", "/internal/links/verify", json={"candidate_id": str(candidate_id), "code": code}
        )

    async def demo_create_result(self) -> dict[str, Any]:
        return await self._call("POST", "/internal/demo/fsp/results")

    async def demo_reset(self) -> dict[str, Any]:
        return await self._call("POST", "/internal/demo/fsp/reset")
