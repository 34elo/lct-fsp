"""`POST /v1/assessment/explain`: текст объяснения ошибки.

Причину считает core по правилам; здесь LLM только формулирует текст по JSON-схеме.
`ML_FAKE=true` — шаблон, `LLM_ENABLED=false` — 503 `llm_disabled` (core тогда берёт свой шаблон).
Текст ответов кандидата сюда не попадает.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import jinja2
import structlog
from fastapi import APIRouter
from fsp_contracts.ml import AnswerExplain, AnswerExplainRequest
from fsp_platform.app import ProblemError
from pydantic import BaseModel, Field, ValidationError

from fsp_ml.config import Settings
from fsp_ml.llm import LlmClient, LlmError, OpenAiLlm

log = structlog.get_logger()
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
PROMPT_VERSION = "v1"
FAKE_MODEL = "fake-answer-explain"


class LlmExplain(BaseModel):
    text: str = Field(min_length=10, max_length=800)


def fake_explain(req: AnswerExplainRequest) -> AnswerExplain:
    text = f"Вероятная причина: {req.reason_label.lower()}."
    if req.misconception and req.truth:
        text += f" Частое заблуждение: {req.misconception} На деле: {req.truth}"
    return AnswerExplain(text=text[:800], model=FAKE_MODEL)


@cache
def _template() -> jinja2.Template:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(PROMPTS_DIR), autoescape=False, keep_trailing_newline=False
    )
    return env.get_template(f"answer_explain/{PROMPT_VERSION}.j2")


def build_messages(req: AnswerExplainRequest) -> list[dict[str, Any]]:
    t = _template()
    return [
        {"role": "system", "content": t.render(part="system").strip()},
        {"role": "user", "content": t.render(part="user", r=req).strip()},
    ]


async def explain_llm(llm: LlmClient, req: AnswerExplainRequest, model: str) -> AnswerExplain:
    data = await llm.complete_json(
        build_messages(req), LlmExplain.model_json_schema(), schema_name="answer_explain"
    )
    try:
        d = LlmExplain.model_validate(data)
    except ValidationError as e:
        raise LlmError("llm_invalid", "ответ не по схеме") from e
    return AnswerExplain(text=d.text.strip(), model=model)


def build_router(settings: Settings, llm: LlmClient | None = None) -> APIRouter:
    router = APIRouter()
    client: LlmClient | None = llm
    if client is None and not settings.ml_fake and settings.llm_enabled and settings.llm_base_url:
        client = OpenAiLlm(
            settings.llm_base_url,
            settings.llm_api_key,
            settings.llm_model,
            timeout=settings.llm_timeout,
            max_tokens=settings.llm_max_tokens,
        )

    @router.post("/v1/assessment/explain")
    async def explain(req: AnswerExplainRequest) -> AnswerExplain:
        if settings.ml_fake:
            return fake_explain(req)
        if not settings.llm_enabled:
            raise ProblemError(503, "llm_disabled", "LLM выключен: используется шаблон")
        if client is None:
            raise ProblemError(503, "ml_unavailable", "LLM не подключён (LLM_BASE_URL)")
        try:
            return await explain_llm(client, req, settings.llm_model)
        except LlmError as e:
            log.warning("answer_explain_failed", code=e.code, kind=req.kind)
            raise ProblemError(503, e.code, "Объяснение не получено") from e

    return router
