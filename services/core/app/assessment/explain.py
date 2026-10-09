"""«Объясни ответ» (E24-2, assessment.md §10): причина ошибки по правилам + текст объяснения.

Причину считают правила (`classify`) по заданию, ответу и времени; LLM (через ml-api) только
формулирует текст по уже найденной причине, без LLM — шаблон. Ключ и правильный ответ не
показываются никогда, пересказ ответов кандидата не пишется ни в логи, ни в аналитику.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx
import structlog
from fsp_contracts.ml import AnswerExplain, AnswerExplainRequest
from fsp_platform.app import ProblemError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import attempts
from app.assessment.families.base import SCORERS, Item, Kind
from app.assessment.models import Response
from app.config import Settings
from app.taxonomy.cards import CARDS_DIR, SkillCard, parse_card

log = structlog.get_logger()

# код причины → подпись для кандидата. Порядок — порядок в выпадающем списке «моя причина».
REASONS: dict[str, str] = {
    "correct": "Ответ верный",
    "skipped": "Ответ не дан",
    "rushed": "Слишком быстрый ответ",
    "misconception": "Ложное представление о теме",
    "calc_error": "Ошибка в вычислении",
    "off_by_one": "Ошибка на единицу",
    "order_of_magnitude": "Ошибка в порядке величины",
    "close_estimate": "Оценка близкая, но неточная",
    "wrong_place": "Дефект искали не там",
    "partial": "Найдена только часть",
    "order_mistake": "Нарушен порядок",
    "suboptimal_action": "Выбрано не лучшее действие",
    "chain_step": "Ошибка на одном из шагов",
    "knowledge_gap": "Пробел в знаниях",
}
_HINTS = {
    "rushed": "Ответ дан слишком быстро: перечитайте условие и проверьте себя до отправки.",
    "skipped": "Ответа нет: если не уверены, лучше выбрать наиболее вероятный вариант.",
    "calc_error": "Идея может быть верной, но вычисление не сошлось: пройдите его по шагам.",
    "off_by_one": "Результат отличается на единицу: проверьте границы и начало отсчёта.",
    "order_of_magnitude": "Ответ отличается на порядок и больше: проверьте единицы и степени.",
    "close_estimate": "Оценка близка к верной; уточните исходные величины.",
    "wrong_place": "Ошибка в другой части кода: проследите, как данные идут по строкам.",
    "partial": "Найдена только часть: проверьте, нет ли ещё одного места с той же проблемой.",
    "order_mistake": "Шаги стоят не в том порядке: подумайте, что от чего зависит.",
    "suboptimal_action": "Есть действие лучше: сравните, какое снижает риск быстрее остальных.",
    "chain_step": "Одно из звеньев цепочки неверно: решите каждый шаг отдельно.",
    "knowledge_gap": "Похоже на пробел в теме: повторите её по материалам навыка.",
    "misconception": "Похоже на распространённое заблуждение по этой теме.",
}


@dataclass(frozen=True)
class Reason:
    code: str
    detail: str | None = None  # без ПДн и без ключа: например, номер шага цепочки


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return f if math.isfinite(f) else None


def classify(item: Item, answer: Any, score: float | None, rt_ms: int | None) -> Reason:
    """Причина ошибки только по правилам. `score` — сохранённый балл ответа."""
    s = score or 0.0
    if s >= 1.0:
        return Reason("correct")
    if answer is None or answer == [] or (isinstance(answer, str) and not answer.strip()):
        return Reason("skipped")
    if rt_ms is not None and s == 0.0 and rt_ms < 0.1 * item.time_limit_s * 1000:
        return Reason("rushed")
    k = item.kind
    if k == Kind.chain:
        return _classify_chain(item, answer)
    if k == Kind.estimate:
        a, key = _num(answer), _num(item.key)
        if a and key and a > 0 and key > 0:
            d = abs(math.log10(a / key))
            if s > 0:
                return Reason("close_estimate")
            if d > 1.0:
                return Reason("order_of_magnitude")
        return Reason("calc_error")
    if k == Kind.exact:
        a, key = _num(answer), _num(item.key)
        if a is None or key is None:
            return Reason("knowledge_gap")
        if abs(a - key) == 1:
            return Reason("off_by_one")
        return Reason("calc_error")
    if k == Kind.choice:
        return Reason("misconception")
    if k == Kind.find_bug:
        return _classify_find_bug(item.key, answer, s)
    if k == Kind.order:
        return Reason("order_mistake")
    if k == Kind.sjt:
        return Reason("suboptimal_action")
    return Reason("knowledge_gap")


def _classify_find_bug(key: Any, answer: Any, s: float) -> Reason:
    want = {x for x in key if isinstance(x, int)} if isinstance(key, list) else set()
    got = {x for x in answer if isinstance(x, int)} if isinstance(answer, list) else set()
    if s > 0 or (got & want):
        return Reason("partial")
    if want and any(abs(g - w) == 1 for g in got for w in want):
        return Reason("off_by_one")
    return Reason("wrong_place")


def _classify_chain(item: Item, answer: Any) -> Reason:
    if not isinstance(answer, list):
        return Reason("knowledge_gap")
    for i, step in enumerate(item.steps):
        a = answer[i] if i < len(answer) else None
        if SCORERS[step.kind](step.key, a) < 1.0:
            return Reason("chain_step", f"шаг {i + 1}")
    return Reason("chain_step")


@lru_cache(maxsize=256)
def _card(skill: str) -> SkillCard | None:
    path = CARDS_DIR / f"{skill}.yaml"
    try:
        return parse_card(path) if path.is_file() else None
    except Exception:  # noqa: BLE001 — битая карточка не должна ломать объяснение
        log.warning("skill_card_unreadable", skill=skill)
        return None


def misconception_for(skill: str, seed: int, reason: Reason) -> dict[str, str] | None:
    """Заблуждение из карточки навыка для ошибки-«заблуждения»; выбор детерминирован сидом."""
    if reason.code not in ("misconception", "knowledge_gap"):
        return None
    card = _card(skill)
    if card is None or not card.misconceptions:
        return None
    m = card.misconceptions[seed % len(card.misconceptions)]
    return {"claim": m.claim, "truth": m.truth}


def template_text(reason: Reason, mis: dict[str, str] | None) -> str:
    """Текст без LLM: подсказка по причине и (если есть) заблуждение с пояснением."""
    parts = [_HINTS.get(reason.code, _HINTS["knowledge_gap"])]
    if reason.detail:
        parts.append(f"Ориентир: {reason.detail}.")
    if mis:
        parts.append(f"Частое заблуждение: {mis['claim']} На деле: {mis['truth']}")
    return " ".join(parts)


async def llm_text(
    settings: Settings,
    item: Item,
    skill: str,
    reason: Reason,
    mis: dict[str, str] | None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AnswerExplain | None:
    """Формулировка от LLM через ml-api; `None` — LLM выключен или недоступен (берём шаблон)."""
    if not settings.llm_enabled or not settings.ml_api_url:
        return None
    req = AnswerExplainRequest(
        kind=item.kind.value,  # type: ignore[arg-type]
        skill=skill,
        stem=item.stem[:6000],
        reason_code=reason.code,
        reason_label=REASONS[reason.code],
        misconception=mis["claim"] if mis else None,
        truth=mis["truth"] if mis else None,
    )
    try:
        async with httpx.AsyncClient(
            base_url=settings.ml_api_url,
            timeout=settings.assessment_key_draft_timeout_seconds,
            transport=transport,
        ) as c:
            resp = await c.post("/v1/assessment/explain", json=req.model_dump(mode="json"))
        resp.raise_for_status()
        return AnswerExplain.model_validate(resp.json())
    except (httpx.HTTPError, ValueError, ValidationError) as e:
        log.warning("answer_explain_unavailable", error=type(e).__name__, kind=item.kind.value)
        return None


async def explain_response(
    session: AsyncSession,
    settings: Settings,
    candidate_id: Any,
    attempt_id: Any,
    response_id: Any,
    self_reason: str | None,
) -> dict[str, Any]:
    """Объяснение одного ответа завершённой попытки своего кандидата (чужое → 404)."""
    att = await attempts._own_attempt(session, candidate_id, attempt_id)
    resp = await session.get(Response, response_id)
    if resp is None or resp.attempt_id != att.id:
        raise ProblemError(404, "not_found", "Задание не найдено")
    if att.status == "active":  # ключ и разбор не раскрываем, пока идёт тест
        raise ProblemError(409, "attempt_active", "Объяснение доступно после завершения попытки")
    if resp.answered_at is None:
        raise ProblemError(409, "not_answered", "На это задание ответа не было")
    fam = await attempts._family(session, resp.family_id)
    item = attempts.build_item(fam, resp.seed, att.plan.get("domain"))
    reason = classify(item, resp.answer, resp.score, resp.rt_ms)
    mis = misconception_for(fam.skill, resp.seed, reason)
    text, source, model = template_text(reason, mis), "template", None
    if reason.code != "correct":
        drafted = await llm_text(settings, item, fam.skill, reason, mis)
        if drafted is not None:
            text, source, model = drafted.text, "llm", drafted.model or None
    else:
        text = "Ответ верный, объяснение не требуется."
    return {
        "response_id": resp.id,
        "seq": resp.seq,
        "skill": fam.skill,
        "score": resp.score or 0.0,
        "reason": {"code": reason.code, "label": REASONS[reason.code], "detail": reason.detail},
        "misconception": mis,
        "text": text,
        "source": source,
        "model": model,
        "self_reason": self_reason,
        "self_reason_matches": (
            None
            if self_reason is None
            else (self_reason == reason.code or (self_reason, reason.code) in _EQUIV)
        ),
    }


def _fmt(item: Item, value: Any) -> str | None:
    """Ответ или ключ человеческим текстом; `None` — ответа нет."""
    if value is None or value == [] or (isinstance(value, str) and not value.strip()):
        return None
    opts = item.options or []

    def opt(i: Any) -> str | None:
        ok = isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(opts)
        return opts[i] if ok else None

    k = item.kind
    if k == Kind.choice:
        return opt(value) or str(value)
    if k in (Kind.order, Kind.sjt) and isinstance(value, list):
        return " → ".join(opt(i) or str(i) for i in value)
    if k == Kind.find_bug and isinstance(value, list):
        return ", ".join(str(i) for i in sorted(x for x in value if isinstance(x, int)))
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)[:500]


def _review_part(item: Item, answer: Any, score: float | None, rt_ms: int | None) -> dict[str, Any]:
    reason = classify(item, answer, score, rt_ms)
    return {
        "kind": item.kind.value,
        "stem": item.stem,
        "options": item.options,
        "yours": _fmt(item, answer),
        "correct": _fmt(item, item.key),
        "reason": {"code": reason.code, "label": REASONS[reason.code], "detail": reason.detail},
    }


async def review_attempt(
    session: AsyncSession, candidate_id: Any, attempt_id: Any
) -> dict[str, Any]:
    """Разбор завершённой попытки (E39-10): условие, ответы, причина по каждому заданию.

    Ключи отдаём только после завершения: у идущей попытки — 409, чужая — 404.
    """
    att = await attempts._own_attempt(session, candidate_id, attempt_id)
    if att.status == "active":
        raise ProblemError(409, "attempt_active", "Разбор доступен после завершения попытки")
    rows = (
        await session.execute(
            select(Response)
            .where(
                Response.attempt_id == att.id,
                Response.answered_at.is_not(None),
                Response.is_pilot.is_(False),
            )
            .order_by(Response.seq)
        )
    ).scalars()
    out: list[dict[str, Any]] = []
    for resp in rows:
        fam = await attempts._family(session, resp.family_id)
        item = attempts.build_item(fam, resp.seed, att.plan.get("domain"))
        part = _review_part(item, resp.answer, resp.score, resp.rt_ms)
        reason = classify(item, resp.answer, resp.score, resp.rt_ms)
        mis = misconception_for(fam.skill, resp.seed, reason)
        steps = None
        if item.kind == Kind.chain:
            got = resp.answer if isinstance(resp.answer, list) else []
            steps = [
                _review_part(
                    st,
                    got[i] if i < len(got) else None,
                    SCORERS[st.kind](st.key, got[i] if i < len(got) else None),
                    resp.rt_ms,
                )
                for i, st in enumerate(item.steps)
            ]
            part["yours"] = part["correct"] = None
        out.append(
            {
                **part,
                "response_id": resp.id,
                "seq": resp.seq,
                "skill": fam.skill,
                "skill_type": fam.skill_type.value,
                "score": resp.score or 0.0,
                "rt_ms": resp.rt_ms,
                "time_limit_s": item.time_limit_s,
                "why": (
                    "Ответ верный." if reason.code == "correct" else template_text(reason, mis)
                ),
                "misconception": mis,
                "steps": steps,
            }
        )
    return {"attempt_id": att.id, "profession": att.profession, "items": out}


# самооценка кандидата совпадает с причиной по правилам
_EQUIV = {
    ("knowledge_gap", "misconception"),
    ("calc_error", "off_by_one"),
    ("calc_error", "order_of_magnitude"),
    ("calc_error", "close_estimate"),
}
