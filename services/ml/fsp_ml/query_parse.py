"""`POST /v1/query/parse`: разбор текстового запроса работодателя.

Базой всегда служит правиловый разбор — он работает в любом профиле (`ML_FAKE`, lite, полный) и
никогда не отвечает 503. Если LLM доступен, он только дополняет поля, которые правила не нашли;
ошибка или неверный ответ LLM молча возвращают правиловый результат.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter
from fsp_contracts.enums import Grade, RoleSlug, WorkFormat
from fsp_contracts.ml import FilterChip, ParsedQuery, QueryParseRequest
from pydantic import BaseModel, Field, ValidationError

from fsp_ml import fake
from fsp_ml.config import Settings
from fsp_ml.llm import LlmClient, LlmError

log = structlog.get_logger()

_SCHEMA_NAME = "query_parse"


class LlmQuery(BaseModel):
    """Схема ответа LLM: все поля необязательные, пустое значение = «не указано»."""

    roles: list[RoleSlug] = Field(default_factory=list)
    grade: Grade | None = None
    formats: list[WorkFormat] = Field(default_factory=list)
    salary_max: int | None = Field(default=None, ge=0, le=10_000_000)


def parse_rules(req: QueryParseRequest) -> ParsedQuery:
    """Правиловый разбор: те же фильтры, но чипы помечены источником `rule`."""
    out = fake.parse_query(req)
    out.chips = [c.model_copy(update={"source": "rule"}) for c in out.chips]
    return out


def _messages(text: str) -> list[dict[str, Any]]:
    roles = ", ".join(r.value for r in RoleSlug)
    grades = ", ".join(g.value for g in Grade)
    formats = ", ".join(f.value for f in WorkFormat)
    system = (
        "Ты извлекаешь фильтры поиска IT-кандидата из запроса работодателя. Отвечай только JSON "
        f"по схеме. roles из: {roles}. grade из: {grades}. formats из: {formats}. "
        "salary_max — рубли в месяц. Если поле не названо в запросе, оставь пустым."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]


async def refine_with_llm(llm: LlmClient, req: QueryParseRequest, base: ParsedQuery) -> ParsedQuery:
    """Дополнить пустые поля базового разбора ответом LLM; при сбое вернуть базу."""
    try:
        raw = await llm.complete_json(
            _messages(req.text),
            LlmQuery.model_json_schema(),
            schema_name=_SCHEMA_NAME,
        )
        found = LlmQuery.model_validate(raw)
    except (LlmError, ValidationError) as e:
        log.warning("query_parse_llm_fallback", error=str(e)[:200])
        return base
    f = base.filters
    chips: list[FilterChip] = list(base.chips)

    def add(key: str, value: object, label: str) -> None:
        chips.append(FilterChip(key=key, value=value, label=label, source="llm", confidence=0.7))

    if found.roles and not f.roles:
        f.roles = list(dict.fromkeys(found.roles))
        add("roles", [r.value for r in f.roles], "Роль: " + ", ".join(r.value for r in f.roles))
    if found.grade and f.grade_min is None:
        f.grade_min = f.grade_max = found.grade
        add("grade_min", found.grade.value, f"Грейд: {found.grade.value}")
    if found.formats and not f.formats:
        f.formats = list(dict.fromkeys(found.formats))
        names = [x.value for x in f.formats]
        add("formats", names, "Формат: " + ", ".join(names))
    if found.salary_max and f.salary_max is None:
        f.salary_max = found.salary_max
        add("salary_max", found.salary_max, f"До {found.salary_max} ₽/мес")
    return ParsedQuery(filters=f, chips=chips, unparsed=base.unparsed, refining=base.refining)


async def parse_query(req: QueryParseRequest, llm: LlmClient | None) -> ParsedQuery:
    base = parse_rules(req)
    return await refine_with_llm(llm, req, base) if llm is not None else base


def build_router(settings: Settings, llm: LlmClient | None) -> APIRouter:
    router = APIRouter()
    # LLM поверх правил только при ML_FAKE=false: в фейк-режиме ответ детерминирован
    use = None if settings.ml_fake else llm

    @router.post("/v1/query/parse")
    async def query_parse(req: QueryParseRequest) -> ParsedQuery:
        return await parse_query(req, use)

    return router
