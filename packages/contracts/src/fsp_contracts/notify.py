"""Команда `notify.telegram` → очередь `bot.telegram` (messaging.md §2.2, telegram.md §5).

Шаблоны и клавиатуры рендерит бот (`bot/templates/*.py`); core передаёт только данные.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

CALLBACK_DATA_MAX_BYTES = 64


class TgTemplate(StrEnum):
    offer_new = "offer_new"
    offer_accepted = "offer_accepted"  # кандидату после принятия (редактирует offer_new)
    offer_updated = "offer_updated"  # смена статуса: работодателю и кандидату
    offer_message = "offer_message"
    profile_updated = "profile_updated"
    resume_progress = "resume_progress"  # одно сообщение, редактируется по этапам
    resume_parsed = "resume_parsed"  # «вот что я понял»
    code_progress = "code_progress"
    fsp_imported = "fsp_imported"
    regular_task_published = "regular_task_published"
    test_result = "test_result"
    uplift = "uplift"


class TgButton(BaseModel):
    text: str
    callback_data: str | None = None  # api.md §5, ≤ 64 байт
    url: str | None = None

    @model_validator(mode="after")
    def _one_action(self) -> TgButton:
        if (self.callback_data is None) == (self.url is None):
            raise ValueError("нужно ровно одно из callback_data и url")
        if (
            self.callback_data is not None
            and len(self.callback_data.encode()) > CALLBACK_DATA_MAX_BYTES
        ):
            raise ValueError("callback_data длиннее 64 байт")
        return self


class NotifyTelegram(BaseModel):
    chat_id: int
    template: TgTemplate
    data: dict[str, Any] = Field(default_factory=dict)
    buttons: list[list[TgButton]] = Field(default_factory=list)  # ряды клавиатуры
    # Ключ сообщения для редактирования (например, `resume:<id>`, `offer:<id>`):
    # бот хранит соответствие ключ → message_id. Нет такого сообщения — шлёт новое.
    edit_of: str | None = None
