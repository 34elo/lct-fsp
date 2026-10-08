"""Офлайн-конвейер LLM-заданий (E26-4, ADR-024): генератор и решатель для core.

- `POST /v1/families/generate` — генератор: черновики форм конструктора (`FamilySpec`) для навыка,
  `kind` и уровня. Ключ в них — тоже черновик: core прогоняет автопроверку и кладёт семейство в
  `draft`, в оценку оно идёт только после админа и пилота.
- `POST /v1/families/solve` — решатель: LLM отвечает на вариант так, как его видит кандидат
  (без ключа). Core считает балл своим `score` → `ai_solvable` и сверку с ключом.

`ML_FAKE=true` — детерминированные заглушки, `LLM_ENABLED=false` — 503 `llm_disabled` (банк растёт
без модели: генераторы, майнинг, конструктор). Вызывает их только офлайн-конвейер core по одному
запросу за раз (одна GPU). Ответ LLM проверяется по JSON-схеме и по границам варианта.
"""

from __future__ import annotations

import hashlib
import random
import re
from functools import cache
from pathlib import Path
from typing import Any

import jinja2
import structlog
from fastapi import APIRouter
from fsp_contracts.ml import (
    FamilyGenerateRequest,
    FamilyGenerateResponse,
    FamilySolveAnswer,
    FamilySolveRequest,
)
from fsp_platform.app import ProblemError
from pydantic import BaseModel, Field, ValidationError

from fsp_ml.config import Settings
from fsp_ml.llm import LlmClient, LlmError, OpenAiLlm

log = structlog.get_logger()
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
GEN_PROMPT_VERSION = "v1"
SOLVE_PROMPT_VERSION = "v1"
FAKE_MODEL = "fake-family-bank"
GEN_TEMPERATURE = 0.7  # разнообразие предложений; ключ всё равно проверяет автопроверка
_LINE = re.compile(r"^\s*(\d+) \|", re.MULTILINE)


# --- схемы ответа LLM -------------------------------------------------------------------------


class LlmParam(BaseModel):
    min: float | None = None
    max: float | None = None
    step: float | None = None
    values: list[float | str] | None = Field(default=None, max_length=50)


class LlmAction(BaseModel):
    text: str = Field(max_length=500)
    score: float | None = None


class LlmSpec(BaseModel):
    """Форма конструктора в упрощённой схеме; строгая проверка — `FamilySpec` в core."""

    title: str = Field(max_length=120)
    stem: str = Field(max_length=4000)
    time_limit_s: int = 120
    params: dict[str, LlmParam] = Field(default_factory=dict)
    derived: dict[str, str] = Field(default_factory=dict)
    answer: str | None = None
    precision: int = 2
    options: list[str] | None = Field(default=None, max_length=8)
    correct: int | None = None
    lines: list[str] | None = Field(default=None, max_length=60)
    bug_lines: list[int] | None = Field(default=None, max_length=10)
    steps: list[str] | None = Field(default=None, max_length=10)
    actions: list[LlmAction] | None = Field(default=None, max_length=8)
    rubric: list[str] | None = Field(default=None, max_length=10)


class LlmSpecs(BaseModel):
    specs: list[LlmSpec] = Field(max_length=5)


class LlmSolve(BaseModel):
    answer: int | float | str | list[int] | None = None


# --- заглушки ML_FAKE -------------------------------------------------------------------------


def _rng(payload: str) -> random.Random:
    return random.Random(int.from_bytes(hashlib.sha256(payload.encode()).digest()[:8], "big"))


def _fake_spec(req: FamilyGenerateRequest, i: int) -> dict[str, Any]:
    """Шаблон задания по `kind`: валидная форма конструктора с ключом (для разработки без GPU)."""
    base = {"title": f"{req.skill}: {req.kind} #{i + 1}", "time_limit_s": 60 + 30 * req.level}
    step = 10 * (i + 1)
    match req.kind:
        case "exact":
            return {
                **base,
                "stem": "Сервис {{service}} компании {{company}} получает {{rps}} запросов в "
                "секунду. Сколько запросов он обработает за {{minutes}} мин?",
                "params": {
                    "rps": {"min": step, "max": step * 20, "step": step},
                    "minutes": {"values": [5, 10, 15]},
                },
                "answer": "rps * 60 * minutes",
                "precision": 0,
            }
        case "estimate":
            return {
                **base,
                "stem": "Таблица {{table}} растёт на {{rows}} строк в день, строка — {{size}} "
                "байт. Оцените объём за год в мегабайтах.",
                "params": {
                    "rows": {"min": 1000 * (i + 1), "max": 100000, "step": 1000},
                    "size": {"values": [200, 500, 1000]},
                },
                "answer": "rows * size * 365 / 1000000",
            }
        case "choice":
            return {
                **base,
                "stem": "Сколько в худшем случае сравнений нужно бинарному поиску в "
                "отсортированном массиве из {{n}} элементов (по порядку величины)?",
                "params": {"n": {"values": [1000, 10000, 100000]}},
                "options": ["O(log n)", "O(n)", "O(1)", "O(n log n)"],
                "correct": 0,
            }
        case "find_bug":
            return {
                **base,
                "stem": "Функция должна вернуть сумму всех элементов списка. Где ошибка?",
                "lines": [
                    "def total(items):",
                    "    s = 0",
                    "    for i in range(1, len(items)):",
                    "        s += items[i]",
                    "    return s",
                ],
                "bug_lines": [3],
            }
        case "order":
            return {
                **base,
                "stem": "Расставьте шаги выкатки сервиса {{service}} в правильном порядке.",
                "steps": [
                    "Собрать образ",
                    "Прогнать тесты",
                    "Выкатить на стенд",
                    "Выкатить в прод",
                ],
            }
        case "sjt":
            return {
                **base,
                "stem": "Коллега прислал на ревью PR в {{service}} на 3000 строк без описания. "
                "Расставьте действия от лучшего к худшему.",
                "actions": [
                    {"text": "Попросить разбить PR и добавить описание", "score": 5},
                    {"text": "Обсудить с автором, что меняется, и ревьюить по частям", "score": 4},
                    {"text": "Посмотреть только тесты", "score": 2},
                    {"text": "Одобрить не глядя", "score": 1},
                ],
            }
    return {
        **base,
        "stem": "Сервис {{service}} отвечает медленно после релиза. Опишите план разбора.",
        "rubric": [
            "Сравнить метрики до и после релиза",
            "Проверить логи и трассировки",
            "Предложить откат или исправление",
        ],
    }


def fake_generate(req: FamilyGenerateRequest) -> FamilyGenerateResponse:
    specs = [
        {**_fake_spec(req, i), "kind": req.kind, "skill": req.skill, "level": req.level}
        for i in range(req.n)
    ]
    return FamilyGenerateResponse(specs=specs, model=FAKE_MODEL)


def fake_solve(req: FamilySolveRequest) -> FamilySolveAnswer:
    """Детерминированный «кандидат наугад»: ai_solvable на заглушке ≈ уровень угадывания."""
    rng = _rng(req.model_dump_json())
    n = len(req.options)
    if req.kind == "choice" and n:
        ans: Any = rng.randrange(n)
    elif req.kind in ("order", "sjt") and n:
        ans = rng.sample(range(n), k=n)
    elif req.kind == "find_bug":
        nums = [int(x) for x in _LINE.findall(req.stem)] or [1]
        ans = [rng.randint(1, max(nums))]
    elif req.kind in ("exact", "estimate"):
        ans = rng.randint(1, 1000)
    else:
        ans = None
    return FamilySolveAnswer(answer=ans, model=FAKE_MODEL)


# --- LLM ---------------------------------------------------------------------------------------


@cache
def _template(task: str, version: str) -> jinja2.Template:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(PROMPTS_DIR), autoescape=False, keep_trailing_newline=False
    )
    return env.get_template(f"{task}/{version}.j2")


def _messages(task: str, version: str, **kw: Any) -> list[dict[str, Any]]:
    t = _template(task, version)
    return [
        {"role": "system", "content": t.render(part="system", **kw).strip()},
        {"role": "user", "content": t.render(part="user", **kw).strip()},
    ]


def answer_fits(req: FamilySolveRequest, ans: Any) -> bool:
    """Ответ в формате кандидата и в границах варианта."""
    n = len(req.options)
    if req.kind == "choice":
        return isinstance(ans, int) and not isinstance(ans, bool) and 0 <= ans < n
    if req.kind in ("order", "sjt"):
        return isinstance(ans, list) and sorted(ans) == list(range(n))
    if req.kind == "find_bug":
        return isinstance(ans, list) and bool(ans) and all(isinstance(x, int) for x in ans)
    if req.kind in ("exact", "estimate"):
        return isinstance(ans, int | float | str) and not isinstance(ans, bool)
    return False  # open решатель не оценивает


async def generate_llm(
    llm: LlmClient, req: FamilyGenerateRequest, model: str
) -> FamilyGenerateResponse:
    data = await llm.complete_json(
        _messages("family_gen", GEN_PROMPT_VERSION, r=req),
        LlmSpecs.model_json_schema(),
        schema_name="family_gen",
        temperature=GEN_TEMPERATURE,
    )
    try:
        specs = LlmSpecs.model_validate(data).specs[: req.n]
    except ValidationError as e:
        raise LlmError("llm_invalid", "ответ не по схеме") from e
    out = [
        {
            **s.model_dump(exclude_none=True),
            "kind": req.kind,
            "skill": req.skill,
            "level": req.level,
        }
        for s in specs
    ]
    return FamilyGenerateResponse(specs=out, model=model)


async def solve_llm(llm: LlmClient, req: FamilySolveRequest, model: str) -> FamilySolveAnswer:
    data = await llm.complete_json(
        _messages("family_solve", SOLVE_PROMPT_VERSION, r=req),
        LlmSolve.model_json_schema(),
        schema_name="family_solve",
    )
    try:
        ans = LlmSolve.model_validate(data).answer
    except ValidationError as e:
        raise LlmError("llm_invalid", "ответ не по схеме") from e
    if not answer_fits(req, ans):
        raise LlmError("llm_invalid", "ответ вне границ варианта")
    return FamilySolveAnswer(answer=ans, model=model)


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

    def _ready() -> LlmClient:
        if not settings.llm_enabled:
            raise ProblemError(503, "llm_disabled", "LLM выключен: банк растёт без модели")
        if client is None:
            raise ProblemError(503, "ml_unavailable", "LLM не подключён (LLM_BASE_URL)")
        return client

    @router.post("/v1/families/generate")
    async def generate(req: FamilyGenerateRequest) -> FamilyGenerateResponse:
        if settings.ml_fake:
            return fake_generate(req)
        c = _ready()
        try:
            return await generate_llm(c, req, settings.llm_model)
        except LlmError as e:
            log.warning("family_generate_failed", code=e.code, kind=req.kind)
            raise ProblemError(503, e.code, "Задания не получены") from e

    @router.post("/v1/families/solve")
    async def solve(req: FamilySolveRequest) -> FamilySolveAnswer:
        if settings.ml_fake:
            return fake_solve(req)
        c = _ready()
        try:
            return await solve_llm(c, req, settings.llm_model)
        except LlmError as e:
            log.warning("family_solve_failed", code=e.code, kind=req.kind)
            raise ProblemError(503, e.code, "Ответ не получен") from e

    return router
