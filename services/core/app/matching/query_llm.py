"""LLM-уточнение разбора запроса и слияние с правилами (ml.md §7 п. 2-3, E7-6).

Правила (`query_parser`) остаются источником правды: деньги, форматы, города, грейд, занятость и
флаги берём из них, если они что-то нашли; LLM (`ml-api /v1/query/parse`) добавляет роли, навыки
и смысловую часть. Ответ LLM проверяется по справочнику, неизвестные навыки отбрасываются,
расхождения с правилами показываем чипсом со знаком `?` (источник `llm`, низкая уверенность).
Недоступный или невалидный ответ LLM — деградация до правилового результата, не ошибка.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx
from fsp_contracts.enums import RoleSlug
from fsp_contracts.ml import (
    FilterChip,
    ParsedQuery,
    QueryParseRequest,
    SkillRequirement,
)
from pydantic import ValidationError

from app.matching import query_parser as qp

log = logging.getLogger(__name__)

CACHE_TTL = 24 * 3600  # messaging.md: c:qparse:{tax_v}:{sha}, 24 ч
_CONFLICT_CONF = 0.3

# поля, где правила главнее: непустое значение правил не перекрывается
_SCALARS = ("grade_min", "grade_max", "salary_max", "relocation_ok", "active_only", "fsp_only")
_LISTS = ("formats", "employment_types", "cities")
_ROLE_VALUES = {r.value for r in RoleSlug}


class QueryLlmClient:
    """Клиент `POST /v1/query/parse` с кешем в Redis. Ошибки наружу не пробрасывает."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 5.0,
        redis: Any = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.redis = redis
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def parse(
        self, text: str, rule: ParsedQuery, taxonomy_version: int
    ) -> ParsedQuery | None:
        """Ответ LLM для текста или `None`, если LLM недоступна / ответила невалидно."""
        sha = hashlib.sha256(qp._norm(text).encode()).hexdigest()
        key = f"c:qparse:{taxonomy_version}:{sha}"
        if self.redis is not None:
            try:
                raw = await self.redis.get(key)
                if raw:
                    return ParsedQuery.model_validate_json(raw)
            except Exception:  # кеш не критичен
                log.warning("qparse_cache_read_failed")
        req = QueryParseRequest(
            text=text, rule_hint=rule.filters, taxonomy_version=taxonomy_version
        )
        try:
            resp = await self._client.post("/v1/query/parse", json=req.model_dump(mode="json"))
            resp.raise_for_status()
            result = ParsedQuery.model_validate(resp.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            log.warning("qparse_llm_unavailable", extra={"error": type(exc).__name__})
            return None
        if self.redis is not None:
            try:
                await self.redis.set(key, result.model_dump_json(), ex=CACHE_TTL)
            except Exception:
                log.warning("qparse_cache_write_failed")
        return result


def _chip(key: str, value: Any, label: str, conf: float) -> FilterChip:
    return FilterChip(key=key, value=value, label=label, source="llm", confidence=conf)


def _val(x: Any) -> Any:
    return getattr(x, "value", x)


def _label(name: str, value: Any) -> str:
    v = _val(value)
    match name:
        case "grade_min":
            return f"Грейд от {qp.GRADE_LABELS[v]}"
        case "grade_max":
            return f"Грейд до {qp.GRADE_LABELS[v]}"
        case "salary_max":
            return f"Бюджет: до {v:,} ₽".replace(",", " ")
        case "formats":
            return f"Формат: {qp.FORMAT_LABELS[v]}"
        case "employment_types":
            return f"Занятость: {qp.EMPLOYMENT_LABELS[v]}"
        case "cities":
            return f"Город: {v}"
        case _:
            return qp.FLAG_LABELS.get(name, name)


def merge(
    rule: ParsedQuery, llm: ParsedQuery | None, forms: dict[str, str], names: dict[str, str]
) -> ParsedQuery:
    """Слияние: правила главнее, LLM дополняет; без LLM возвращает `rule` как есть."""
    if llm is None:
        return rule
    rf, lf = rule.filters, llm.filters
    out = rf.model_copy(deep=True)
    chips = [c for c in rule.chips if c.key != "semantic_text"]

    # скаляры и списки: правила, иначе LLM; расхождение — чипс «?»
    for name in _SCALARS:
        rv, lv = getattr(rf, name), getattr(lf, name)
        if lv is None:
            continue
        if rv is None:
            setattr(out, name, lv)
            chips.append(_chip(name, _val(lv), _label(name, lv), 0.6))
        elif rv != lv:
            chips.append(_chip(name, _val(lv), f"{_label(name, lv)}?", _CONFLICT_CONF))
    for name in _LISTS:
        rv, lv = getattr(rf, name), getattr(lf, name)
        if not lv:
            continue
        if not rv:
            setattr(out, name, list(lv))
            chips += [_chip(name, _val(x), _label(name, x), 0.6) for x in lv]
        else:
            have = {_val(y) for y in rv}
            chips += [
                _chip(name, _val(x), f"{_label(name, x)}?", _CONFLICT_CONF)
                for x in lv
                if _val(x) not in have
            ]

    # роли: правила, иначе LLM; другие роли LLM — конфликт
    if lf.roles:
        have = {r.value for r in rf.roles or []}
        if not have:
            out.roles = list(lf.roles)
        for r in lf.roles:
            if r.value in have:
                continue
            label = f"Роль: {qp.ROLE_LABELS[r.value]}"
            chips.append(
                _chip("roles", r.value, label, 0.7)
                if not have
                else _chip("roles", r.value, f"{label}?", _CONFLICT_CONF)
            )

    # навыки: только из справочника, добавляем к найденным правилами
    def live(slug: str) -> str | None:
        if slug in names and slug not in _ROLE_VALUES:
            return slug
        found = forms.get(qp._norm(slug))
        return found if found in names else None

    must = list(out.skills_must or [])
    seen = {s.slug for s in must} | set(out.skills_nice or [])
    for req in lf.skills_must or []:
        slug = live(req.slug)
        if slug is None or slug in seen:
            continue
        seen.add(slug)
        must.append(SkillRequirement(slug=slug, min_level=req.min_level))
        chips.append(_chip("skills_must", {"slug": slug}, f"Навык: {names[slug]}", 0.7))
    nice = list(out.skills_nice or [])
    for raw in lf.skills_nice or []:
        slug = live(raw)
        if slug is None or slug in seen:
            continue
        seen.add(slug)
        nice.append(slug)
        chips.append(_chip("skills_nice", slug, f"Желательно: {names[slug]}", 0.65))
    out.skills_must = must or None
    out.skills_nice = nice or None

    # смысловая часть — у LLM (правила кладут туда непонятый остаток)
    text = (lf.semantic_text or "").strip() or rf.semantic_text
    out.semantic_text = text[: qp.MAX_TEXT] if text else None
    if out.semantic_text:
        chips.append(_chip("semantic_text", out.semantic_text, f"Смысл: {out.semantic_text}", 0.5))
    return ParsedQuery(filters=out, chips=chips, unparsed=list(rule.unparsed), refining=True)


async def refine(
    client: QueryLlmClient | None,
    text: str,
    rule: ParsedQuery,
    *,
    taxonomy_version: int,
    forms: dict[str, str],
    names: dict[str, str],
) -> ParsedQuery:
    """Правиловый разбор + LLM-уточнение; без клиента или при сбое — правила."""
    if client is None:
        return rule
    llm = await client.parse(text, rule, taxonomy_version)
    return merge(rule, llm, forms, names)
