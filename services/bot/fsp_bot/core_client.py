"""Клиент core `/internal/tg/*` (api.md §2.10). Бизнес-логики в боте нет: только вызовы."""

from __future__ import annotations

from typing import Any

import httpx


class CoreError(Exception):
    """Ответ core не 2xx: `code` — машинный код Problem Details."""

    def __init__(self, status: int, code: str, detail: str = ""):
        super().__init__(f"{status} {code}: {detail}")
        self.status, self.code, self.detail = status, code, detail


class CoreClient:
    def __init__(
        self,
        base_url: str,
        service_token: str,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Service {service_token}"},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = await self._http.request(method, path, **kwargs)
        if resp.is_success:
            return resp.json() if resp.content else None
        try:
            body = resp.json()
        except ValueError:
            body = {}
        raise CoreError(resp.status_code, body.get("code", "core_error"), body.get("detail", ""))

    async def start(
        self, tg_user_id: int, chat_id: int, username: str | None, start_param: str | None
    ) -> dict:
        body = {
            "tg_user_id": tg_user_id,
            "chat_id": chat_id,
            "username": username,
            "start_param": start_param,
        }
        return await self.request("POST", "/internal/tg/start", json=body)

    async def consents(self, tg_user_id: int, types: list[str]) -> None:
        await self.request(
            "POST", "/internal/tg/consents", json={"tg_user_id": tg_user_id, "types": types}
        )

    async def link(self, tg_user_id: int, token: str) -> dict:
        return await self.request(
            "POST", "/internal/tg/link", json={"tg_user_id": tg_user_id, "token": token}
        )

    async def magic_link(self, tg_user_id: int, redirect: str = "/") -> str:
        """Одноразовая ссылка для входа на сайт (кнопка «Открыть на сайте»)."""
        body = {"tg_user_id": tg_user_id, "redirect": redirect}
        return (await self.request("POST", "/internal/auth/magic-link", json=body))["url"]

    async def profile(self, tg_user_id: int) -> dict:
        return await self.request("GET", "/internal/tg/profile", params={"tg_user_id": tg_user_id})

    async def set_status(self, tg_user_id: int, status: str) -> None:
        await self.request(
            "PATCH", "/internal/tg/status", json={"tg_user_id": tg_user_id, "status": status}
        )

    async def upload_resume(self, tg_user_id: int, filename: str, data: bytes) -> dict:
        """Файл не сохраняется в боте: байты уходят в core как multipart и забываются."""
        return await self.request(
            "POST",
            "/internal/tg/resumes",
            data={"tg_user_id": str(tg_user_id)},
            files={"file": (filename, data)},
        )

    async def resume_status(self, tg_user_id: int, resume_id: str) -> dict:
        return await self.request(
            "GET", f"/internal/tg/resumes/{resume_id}", params={"tg_user_id": tg_user_id}
        )

    async def confirm_resume(self, tg_user_id: int, resume_id: str) -> dict:
        return await self.request(
            "POST", f"/internal/tg/resumes/{resume_id}/confirm", json={"tg_user_id": tg_user_id}
        )
