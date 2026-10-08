"""Клиент core `/internal/tg/*` (api.md §2.10). Бизнес-логики в боте нет: только вызовы."""

from __future__ import annotations

import time
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
        self._tokens: dict[int, tuple[str, float]] = {}  # tg_user_id → (access, годен до)
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

    async def set_status(self, tg_user_id: int, status: str) -> dict:
        return await self.request(
            "PATCH", "/internal/tg/status", json={"tg_user_id": tg_user_id, "status": status}
        )

    async def settings(self, tg_user_id: int) -> dict:
        return await self.request("GET", "/internal/tg/settings", params={"tg_user_id": tg_user_id})

    async def update_settings(self, tg_user_id: int, **changes: Any) -> dict:
        """`salary_min` и `formats`; не переданное не меняется, `salary_min=None` очищает."""
        return await self.request(
            "PATCH", "/internal/tg/settings", json={"tg_user_id": tg_user_id, **changes}
        )

    async def category(self, tg_user_id: int) -> dict:
        return await self.request("GET", "/internal/tg/category", params={"tg_user_id": tg_user_id})

    async def fsp(self, tg_user_id: int) -> dict:
        return await self.request("GET", "/internal/tg/fsp", params={"tg_user_id": tg_user_id})

    async def fsp_link(self, tg_user_id: int, value: str) -> dict:
        """Email (есть `@`) или ID участника."""
        key = "email" if "@" in value else "participant_id"
        body = {"tg_user_id": tg_user_id, key: value}
        return await self.request("POST", "/internal/tg/fsp/link", json=body)

    async def fsp_verify(self, tg_user_id: int, code: str) -> dict:
        body = {"tg_user_id": tg_user_id, "code": code}
        return await self.request("POST", "/internal/tg/fsp/verify", json=body)

    async def fsp_sync(self, tg_user_id: int) -> None:
        await self.request("POST", "/internal/tg/fsp/sync", json={"tg_user_id": tg_user_id})

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

    async def offers(self, tg_user_id: int) -> list[dict]:
        return await self.request("GET", "/internal/tg/offers", params={"tg_user_id": tg_user_id})

    async def offer_view(self, tg_user_id: int, offer_id: str) -> dict:
        return await self.request(
            "POST", f"/internal/tg/offers/{offer_id}/view", json={"tg_user_id": tg_user_id}
        )

    async def offer_accept(self, tg_user_id: int, offer_id: str) -> dict:
        return await self.request(
            "POST", f"/internal/tg/offers/{offer_id}/accept", json={"tg_user_id": tg_user_id}
        )

    async def offer_decline(self, tg_user_id: int, offer_id: str, reason: str) -> dict:
        body = {"tg_user_id": tg_user_id, "reason": reason}
        return await self.request("POST", f"/internal/tg/offers/{offer_id}/decline", json=body)

    async def offer_message(self, tg_user_id: int, offer_id: str, text: str) -> dict:
        body = {"tg_user_id": tg_user_id, "text": text}
        return await self.request("POST", f"/internal/tg/offers/{offer_id}/messages", json=body)

    # --- тест и регулярные задания: API блока 1 от имени кандидата (E25-3) ----------------

    async def _user_token(self, tg_user_id: int) -> str:
        cached = self._tokens.get(tg_user_id)
        if cached and cached[1] > time.monotonic():
            return cached[0]
        res = await self.request("POST", "/internal/tg/token", json={"tg_user_id": tg_user_id})
        ttl = max(int(res.get("expires_in", 300)) - 30, 10)
        self._tokens[tg_user_id] = (res["access_token"], time.monotonic() + ttl)
        return res["access_token"]

    async def as_user(self, tg_user_id: int, method: str, path: str, **kwargs: Any) -> Any:
        """Вызов обычного эндпоинта core с коротким токеном кандидата вместо сервисного."""
        token = await self._user_token(tg_user_id)
        return await self.request(
            method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs
        )

    async def test_survey(self, tg_user_id: int) -> dict:
        return await self.as_user(tg_user_id, "GET", "/assessment/survey")

    async def test_professions(self, tg_user_id: int) -> list[dict]:
        return (await self.as_user(tg_user_id, "GET", "/taxonomy/professions"))["professions"]

    async def test_start(self, tg_user_id: int, profession: str, grade: str) -> dict:
        """Короткий тест = экспресс-режим того же движка (6–8 заданий, та же шкала)."""
        body = {"profession": profession, "declared_grade": grade, "mode": "express"}
        return await self.as_user(tg_user_id, "POST", "/assessment/attempts", json=body)

    async def test_next(self, tg_user_id: int, attempt_id: str) -> dict:
        return await self.as_user(tg_user_id, "GET", f"/assessment/attempts/{attempt_id}/next")

    async def test_answer(
        self, tg_user_id: int, attempt_id: str, response_id: str, answer: Any, rt_ms: int
    ) -> dict:
        body = {"response_id": response_id, "answer": answer, "rt_ms": rt_ms}
        return await self.as_user(
            tg_user_id, "POST", f"/assessment/attempts/{attempt_id}/answers", json=body
        )

    async def test_attempt(self, tg_user_id: int, attempt_id: str) -> dict:
        return await self.as_user(tg_user_id, "GET", f"/assessment/attempts/{attempt_id}")

    async def test_upgrade(self, tg_user_id: int, attempt_id: str) -> dict:
        return await self.as_user(tg_user_id, "POST", f"/assessment/attempts/{attempt_id}/upgrade")

    async def tasks(self, tg_user_id: int) -> list[dict]:
        return await self.as_user(tg_user_id, "GET", "/assessment/tasks")

    async def task(self, tg_user_id: int, task_id: str) -> dict:
        return await self.as_user(tg_user_id, "GET", f"/assessment/tasks/{task_id}")

    async def task_answer(self, tg_user_id: int, task_id: str, answer: Any) -> dict:
        return await self.as_user(
            tg_user_id, "POST", f"/assessment/tasks/{task_id}/answer", json={"answer": answer}
        )
