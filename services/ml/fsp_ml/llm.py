"""OpenAI-совместимый клиент LLM: llama-server, ответ строго по JSON-схеме.

`response_format: json_schema` llama-server превращает в грамматику, поэтому JSON синтаксически
валиден. Pydantic-валидацию и бизнес-проверки делает вызывающий код. В тестах вместо
`OpenAiLlm` подставляется любой объект с тем же методом `complete_json` (протокол `LlmClient`).
"""

from __future__ import annotations

import json
from typing import Any, Protocol

import httpx
import structlog

log = structlog.get_logger()


class LlmError(Exception):
    """Машинный код ошибки в `code`: llm_timeout, llm_unavailable, llm_invalid."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


class LlmClient(Protocol):
    async def complete_json(
        self,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        *,
        schema_name: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Вернуть разобранный JSON-объект ответа. Ошибки — `LlmError`."""
        ...


class OpenAiLlm:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout: float = 60.0,
        max_tokens: int = 4096,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.model = model
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._transport = transport

    async def complete_json(
        self,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        *,
        schema_name: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self._max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            },
            # Qwen3: без режима размышлений, иначе латентность растёт в разы
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as c:
                r = await c.post(self._url, json=body, headers=self._headers)
        except httpx.TimeoutException as e:
            raise LlmError("llm_timeout") from e
        except httpx.HTTPError as e:
            raise LlmError("llm_unavailable", type(e).__name__) from e
        if r.status_code >= 400:
            raise LlmError("llm_unavailable", f"HTTP {r.status_code}")
        try:
            choice = r.json()["choices"][0]
            content = choice["message"]["content"]
            data = json.loads(content)
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise LlmError("llm_invalid", "ответ не JSON") from e
        if choice.get("finish_reason") == "length":
            raise LlmError("llm_invalid", "ответ обрезан по max_tokens")
        if not isinstance(data, dict):
            raise LlmError("llm_invalid", "ожидается JSON-объект")
        return data
