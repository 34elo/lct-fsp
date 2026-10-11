"""Черновик ключа задания конструктора через ml-api.

В LLM core напрямую не ходит: только `POST /v1/families/key-draft` ml-api (правило 7).
`LLM_ENABLED=false`, пустой `ML_API_URL` или любая ошибка ml-api → `None`: конструктор работает
без модели, ключ тогда обязан дать автор. Ответ ещё раз проверяется по границам задания.
"""

from __future__ import annotations

from random import Random

import httpx
import structlog
from fsp_contracts.ml import FamilyKeyDraft, FamilyKeyDraftRequest
from pydantic import ValidationError

from app.assessment.families.base import Kind
from app.assessment.families.spec import FamilySpec, SpecError, render, variables
from app.assessment.world import World
from app.config import Settings

log = structlog.get_logger()
EXAMPLE_SEED = 0


def example_request(spec: FamilySpec) -> FamilyKeyDraftRequest:
    """Пример варианта (сид 0) в порядке автора — без ключа, без перемешивания."""
    world = World.from_seed(EXAMPLE_SEED)
    env = variables(spec, Random(EXAMPLE_SEED), world)

    def r(xs: list[str]) -> list[str]:
        return [render(x, env) for x in xs]

    return FamilyKeyDraftRequest(
        kind=spec.kind.value,
        stem=render(spec.stem, env),
        options=r(spec.options or []),
        lines=r(spec.lines or []),
        actions=r([a.text for a in spec.actions or []]),
        steps=r(spec.steps or []),
        rubric=list(spec.rubric or []),
    )


def fits(spec: FamilySpec, d: FamilyKeyDraft) -> bool:
    """Черновик покрывает недостающий ключ и не выходит за границы задания."""
    match spec.kind:
        case Kind.choice:
            return d.correct is not None and 0 <= d.correct < len(spec.options or [])
        case Kind.find_bug:
            n = len(spec.lines or [])
            return bool(d.bug_lines) and all(1 <= x <= n for x in d.bug_lines or [])
        case Kind.sjt:
            sc = d.scores or []
            return len(sc) == len(spec.actions or []) and len(set(sc)) == len(sc)
        case Kind.open:
            return bool(d.rubric) and all(p.strip() for p in d.rubric or [])
    return True


def apply(spec: FamilySpec, d: FamilyKeyDraft) -> FamilySpec:
    """Спецификация, в которой недостающие части ключа взяты из черновика."""
    upd: dict = {}
    if spec.kind == Kind.choice and spec.correct is None:
        upd["correct"] = d.correct
    elif spec.kind == Kind.find_bug and spec.bug_lines is None:
        upd["bug_lines"] = d.bug_lines
    elif spec.kind == Kind.sjt:
        acts = spec.actions or []
        if any(a.score is None for a in acts):
            upd["actions"] = [
                {"text": a.text, "score": s} for a, s in zip(acts, d.scores or [], strict=True)
            ]
    elif spec.kind == Kind.open and not spec.rubric:
        upd["rubric"] = d.rubric
    return FamilySpec.model_validate({**spec.model_dump(), **upd})


async def request_draft(
    settings: Settings, spec: FamilySpec, *, transport: httpx.AsyncBaseTransport | None = None
) -> FamilyKeyDraft | None:
    if not settings.llm_enabled or not settings.ml_api_url:
        return None
    try:
        body = example_request(spec)
    except SpecError:
        return None  # пример не собирается — это покажет автопроверка
    try:
        async with httpx.AsyncClient(
            base_url=settings.ml_api_url,
            timeout=settings.assessment_key_draft_timeout_seconds,
            transport=transport,
        ) as c:
            resp = await c.post("/v1/families/key-draft", json=body.model_dump(mode="json"))
        resp.raise_for_status()
        draft = FamilyKeyDraft.model_validate(resp.json())
    except (httpx.HTTPError, ValueError, ValidationError) as e:
        log.warning("family_key_draft_unavailable", error=type(e).__name__, kind=spec.kind.value)
        return None
    if not fits(spec, draft):
        log.warning("family_key_draft_rejected", kind=spec.kind.value)
        return None
    return draft
