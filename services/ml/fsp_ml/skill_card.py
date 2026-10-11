"""`POST /v1/skills/card-draft`: черновик карточки нового навыка.

Новый (`provisional`) навык получает карточку формата `data/skills/cards/*.yaml`, чтобы авторы
заданий могли им заняться. Это только черновик: в каталог карточек он попадает после проверки
человеком (core проверяет его схемой `taxonomy/cards.py`). `ML_FAKE=true` и `LLM_ENABLED=false`
дают шаблонный черновик без LLM (`model=rules-template`), заметно отличимый от настоящего.
"""

from __future__ import annotations

from fsp_contracts.ml import (
    SkillCardConcept,
    SkillCardDraft,
    SkillCardDraftRequest,
    SkillCardMisconception,
)
from pydantic import BaseModel, Field, ValidationError

from fsp_ml.llm import LlmClient, LlmError
from fsp_ml.skill_pipeline import _messages

CARD_PROMPT_VERSION = "v1"
TEMPLATE_MODEL = "rules-template"
_KIND_TO_TYPE = {"hard": "hard", "soft": "soft", "domain": "business"}


class _LlmLevels(BaseModel):
    junior: list[str] = Field(min_length=2, max_length=5)
    middle: list[str] = Field(min_length=2, max_length=5)
    senior: list[str] = Field(min_length=2, max_length=5)


class LlmCard(BaseModel):
    """Схема ответа LLM; в `SkillCardDraft` превращается после проверки."""

    summary: str = Field(min_length=10, max_length=400)
    levels: _LlmLevels
    concepts: list[SkillCardConcept] = Field(min_length=3, max_length=6)
    misconceptions: list[SkillCardMisconception] = Field(min_length=2, max_length=4)


def card_type(req: SkillCardDraftRequest) -> str:
    return req.skill_type or _KIND_TO_TYPE[req.kind]


def template_draft(req: SkillCardDraftRequest) -> SkillCardDraft:
    """Шаблонный черновик: структура верна, содержание общее и ждёт правки человеком."""
    n = req.name
    return SkillCardDraft(
        skill=req.slug,
        type=card_type(req),  # type: ignore[arg-type]
        summary=f"Использует «{n}» для решения рабочих задач и объясняет свои решения.",
        levels={
            "junior": [
                f"Объясняет, для чего нужен «{n}», и применяет его в простой типовой задаче",
                f"Находит в документации по «{n}» нужный раздел и повторяет пример",
            ],
            "middle": [
                f"Самостоятельно решает с помощью «{n}» задачу средней сложности",
                f"Объясняет типичные ошибки при работе с «{n}» и как их находить",
            ],
            "senior": [
                f"Выбирает, где «{n}» уместен, а где лучше другой подход, и обосновывает выбор",
                f"Учит других работе с «{n}» и проверяет чужие решения",
            ],
        },
        concepts=[
            SkillCardConcept(term=n, note="основной предмет навыка, формулировку уточняет автор"),
            SkillCardConcept(term="Область применения", note="где навык нужен на практике"),
            SkillCardConcept(term="Типичные ошибки", note="что делают неправильно чаще всего"),
        ],
        misconceptions=[
            SkillCardMisconception(
                claim=f"«{n}» подходит для любой задачи",
                truth="у каждого инструмента есть границы применимости",
            ),
            SkillCardMisconception(
                claim=f"Достаточно один раз прочитать про «{n}»",
                truth="уверенность появляется только с практикой на реальных задачах",
            ),
        ],
        model=TEMPLATE_MODEL,
    )


async def draft_card(
    llm: LlmClient | None, req: SkillCardDraftRequest, model: str
) -> SkillCardDraft:
    """С LLM: ответ по схеме; при любой ошибке модели — шаблон, не 5xx (черновик не критичен)."""
    if llm is None:
        return template_draft(req)
    try:
        data = await llm.complete_json(
            _messages("skill_card", CARD_PROMPT_VERSION, r=req),
            LlmCard.model_json_schema(),
            schema_name="skill_card",
        )
        c = LlmCard.model_validate(data)
        texts = [t for ls in (c.levels.junior, c.levels.middle, c.levels.senior) for t in ls]
        if any(not 3 <= len(t.strip()) <= 300 for t in texts) or len(set(texts)) != len(texts):
            raise LlmError("llm_invalid", "утверждения вне границ или повторяются")
        return SkillCardDraft(
            skill=req.slug,
            type=card_type(req),  # type: ignore[arg-type]
            summary=c.summary,
            levels=c.levels.model_dump(),  # type: ignore[arg-type]
            concepts=c.concepts,
            misconceptions=c.misconceptions,
            model=model,
        )
    except (LlmError, ValidationError):
        return template_draft(req)
