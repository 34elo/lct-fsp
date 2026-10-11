"""`POST /v1/families/key-draft`: черновик ключа и рубрики задания конструктора.

Ключ от LLM — всегда черновик: core хранит его отдельно, в оценку он идёт только после решения
админа. `ML_FAKE=true` — детерминированная заглушка, `LLM_ENABLED=false` — 503 `llm_disabled`
(core тогда требует ключ от автора). Ответ LLM проверяется по схеме и по границам индексов.
"""

from __future__ import annotations

import hashlib
import random
from functools import cache
from pathlib import Path
from typing import Any

import jinja2
import structlog
from fastapi import APIRouter
from fsp_contracts.ml import FamilyKeyDraft, FamilyKeyDraftRequest
from fsp_platform.app import ProblemError
from pydantic import BaseModel, Field, ValidationError

from fsp_ml.config import Settings
from fsp_ml.llm import LlmClient, LlmError, OpenAiLlm

log = structlog.get_logger()
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
PROMPT_VERSION = "v1"
FAKE_MODEL = "fake-family-key"


class LlmKeyDraft(BaseModel):
    """Схема ответа LLM (без служебного поля `model`)."""

    correct: int | None = None
    bug_lines: list[int] | None = Field(default=None, max_length=10)
    scores: list[float] | None = Field(default=None, max_length=8)
    answer: float | str | None = None
    rubric: list[str] | None = Field(default=None, max_length=10)
    rationale: str | None = Field(default=None, max_length=1000)


def fits(req: FamilyKeyDraftRequest, d: LlmKeyDraft) -> bool:
    """Черновик относится к заданию: индексы в границах, длины совпадают."""
    if req.kind == "choice":
        return d.correct is not None and 0 <= d.correct < len(req.options)
    if req.kind == "find_bug":
        n = len(req.lines)
        return bool(d.bug_lines) and all(1 <= x <= n for x in d.bug_lines or [])
    if req.kind == "sjt":
        return d.scores is not None and len(d.scores) == len(req.actions)
    if req.kind == "open":
        return bool(d.rubric) and all(r.strip() for r in d.rubric or [])
    return True  # exact, estimate, order: ключ даёт автор, LLM — только примерный ответ


def fake_draft(req: FamilyKeyDraftRequest) -> FamilyKeyDraft:
    """Детерминированный черновик по тексту задания (ML_FAKE=true)."""
    h = hashlib.sha256(req.model_dump_json().encode()).digest()
    rng = random.Random(int.from_bytes(h[:8], "big"))
    out = FamilyKeyDraft(model=FAKE_MODEL, rationale="Черновик-заглушка ML_FAKE")
    if req.kind == "choice" and req.options:
        out.correct = rng.randrange(len(req.options))
    elif req.kind == "find_bug" and req.lines:
        out.bug_lines = [rng.randint(1, len(req.lines))]
    elif req.kind == "sjt" and req.actions:
        ranks = rng.sample(range(1, len(req.actions) + 1), k=len(req.actions))
        out.scores = [float(r) for r in ranks]
    elif req.kind == "open":
        out.rubric = req.rubric or [
            "Названа причина проблемы",
            "Предложено решение с обоснованием",
            "Учтены риски и проверка результата",
        ]
    return out


@cache
def _template() -> jinja2.Template:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(PROMPTS_DIR), autoescape=False, keep_trailing_newline=False
    )
    return env.get_template(f"family_key/{PROMPT_VERSION}.j2")


def build_messages(req: FamilyKeyDraftRequest) -> list[dict[str, Any]]:
    t = _template()
    return [
        {"role": "system", "content": t.render(part="system").strip()},
        {"role": "user", "content": t.render(part="user", r=req).strip()},
    ]


async def draft_llm(llm: LlmClient, req: FamilyKeyDraftRequest, model: str) -> FamilyKeyDraft:
    data = await llm.complete_json(
        build_messages(req), LlmKeyDraft.model_json_schema(), schema_name="family_key"
    )
    try:
        d = LlmKeyDraft.model_validate(data)
    except ValidationError as e:
        raise LlmError("llm_invalid", "ответ не по схеме") from e
    if not fits(req, d):
        raise LlmError("llm_invalid", "ключ вне границ задания")
    return FamilyKeyDraft(**d.model_dump(), model=model)


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

    @router.post("/v1/families/key-draft")
    async def key_draft(req: FamilyKeyDraftRequest) -> FamilyKeyDraft:
        if settings.ml_fake:
            return fake_draft(req)
        if not settings.llm_enabled:
            raise ProblemError(503, "llm_disabled", "LLM выключен: ключ задаёт автор")
        if client is None:
            raise ProblemError(503, "ml_unavailable", "LLM не подключён (LLM_BASE_URL)")
        try:
            return await draft_llm(client, req, settings.llm_model)
        except LlmError as e:
            log.warning("family_key_draft_failed", code=e.code, kind=req.kind)
            raise ProblemError(503, e.code, "Черновик ключа не получен") from e

    return router
