"""Задача в приглашении (E33-3, ADR-026): работодатель прикладывает задание, кандидат решает.

Задание берётся из банка блока 1 (конструктор E30-1 или банк семейств) через порт `TaskBank`.
Блок 2 хранит только привязку к офферу (`OfferTask`): срок, ответ и балл. Решение идёт
доказательством `task` в профиль (пишет блок 1 внутри `submit`), а результат виден только
компании этого оффера: `OfferTask` привязана к офферу, наружу уходит лишь в `OfferForCompany`.
Принять приглашение можно и без решения. Функции не делают `commit`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from fsp_contracts.enums import OfferStatus
from fsp_platform.app import ProblemError
from sqlalchemy.ext.asyncio import AsyncSession

from app.offers.models import Offer, OfferTask

MAX_MINUTES = 15
DEFAULT_DEADLINE_DAYS = 3
MAX_DEADLINE_DAYS = 14
MAX_ANSWER_CHARS = 20_000
# решать можно, пока приглашение живо: после принятия тоже (контакты от решения не зависят)
_OPEN = {OfferStatus.sent.value, OfferStatus.viewed.value, OfferStatus.accepted.value}


@dataclass(frozen=True)
class TaskInfo:
    """Что порт сообщает о семействе: название, тип, оценка времени в минутах."""

    title: str
    kind: str
    minutes: int


class TaskBank(Protocol):
    """Порт к банку заданий блока 1 (заявка З-2-02, функции `assessment.service.invite_task_*`)."""

    async def describe(
        self, session: AsyncSession, family_id: uuid.UUID, *, company_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> TaskInfo:  # fmt: skip
        """Семейство компании или из банка (`pilot`/`active`); чужое → 404. Время в минутах."""

    async def item(
        self, session: AsyncSession, family_id: uuid.UUID, *, candidate_id: uuid.UUID,
        offer_id: uuid.UUID,
    ) -> dict[str, Any]:  # fmt: skip
        """Вариант для кандидата без ключа и рубрики; сид — от пары (кандидат, оффер)."""

    async def submit(
        self, session: AsyncSession, family_id: uuid.UUID, *, candidate_id: uuid.UUID,
        offer_id: uuid.UUID, answer: Any,
    ) -> float | None:  # fmt: skip
        """Оценить ответ (0..1; `None` — ждёт проверки) и записать доказательство `task`.

        Идемпотентно по `offer_id` (`fact_id`): повтор не плодит доказательств.
        """


class _Unavailable:
    """Пока блок 1 не отдал функции (заявка З-2-02): задача не доставляется, оффер работает."""

    @staticmethod
    def _fn(name: str):
        from app.assessment import service as assessment  # noqa: PLC0415

        fn = getattr(assessment, name, None)
        if fn is None:
            raise ProblemError(503, "task_bank_unavailable", "Банк заданий временно недоступен")
        return fn

    async def describe(self, session, family_id, *, company_id, user_id) -> TaskInfo:
        r = await self._fn("invite_task_describe")(
            session, family_id, company_id=company_id, user_id=user_id
        )
        return TaskInfo(title=r.title, kind=r.kind, minutes=r.minutes)

    async def item(self, session, family_id, *, candidate_id, offer_id) -> dict[str, Any]:
        return await self._fn("invite_task_item")(
            session, family_id, candidate_id=candidate_id, offer_id=offer_id
        )

    async def submit(self, session, family_id, *, candidate_id, offer_id, answer):
        return await self._fn("invite_task_submit")(
            session, family_id, candidate_id=candidate_id, offer_id=offer_id, answer=answer
        )


_bank: TaskBank = _Unavailable()


def get_bank() -> TaskBank:
    return _bank


def set_bank(bank: TaskBank) -> None:
    """Подмена порта (тесты)."""
    global _bank
    _bank = bank


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def not_found() -> ProblemError:
    return ProblemError(404, "task_not_found", "В приглашении нет задачи")


async def check(
    session: AsyncSession, family_id: uuid.UUID, *, company_id: uuid.UUID, user_id: uuid.UUID,
    deadline_days: int,
) -> TaskInfo:  # fmt: skip
    """Проверка до создания оффера: семейство доступно компании, решается за ≤ 15 минут."""
    if not 1 <= deadline_days <= MAX_DEADLINE_DAYS:
        raise ProblemError(
            422, "invalid_task_deadline", "Срок задачи — от 1 до 14 дней",
            errors=[{"field": "task.deadline_days", "message": "от 1 до 14"}],
        )  # fmt: skip
    info = await get_bank().describe(session, family_id, company_id=company_id, user_id=user_id)
    if info.minutes > MAX_MINUTES:
        raise ProblemError(
            422, "task_too_long", "Задача не должна занимать больше 15 минут",
            errors=[{"field": "task.family_id", "message": f"{info.minutes} мин > {MAX_MINUTES}"}],
        )  # fmt: skip
    return info


async def attach(
    session: AsyncSession, offer: Offer, family_id: uuid.UUID, info: TaskInfo, *,
    deadline_days: int, now: datetime | None = None,
) -> OfferTask:  # fmt: skip
    """Привязать задачу к только что отправленному приглашению. Срок — от момента отправки."""
    now = now or datetime.now(UTC)
    task = OfferTask(
        offer_id=offer.id, company_id=offer.company_id, family_id=family_id,
        title=info.title, kind=info.kind, minutes=info.minutes,
        deadline_at=now + timedelta(days=deadline_days), created_at=now,
    )  # fmt: skip
    session.add(task)
    await session.flush()
    return task


async def get(session: AsyncSession, offer_id: uuid.UUID) -> OfferTask | None:
    return await session.get(OfferTask, offer_id)


def visible_to_candidate(offer: Offer) -> bool:
    """Задача видна кандидату, только когда приглашение отправлено (не интерес)."""
    return not offer.status.startswith("interest")


async def get_for_candidate(session: AsyncSession, offer: Offer) -> OfferTask:
    task = await get(session, offer.id)
    if task is None or not visible_to_candidate(offer):
        raise not_found()
    return task


def can_answer(offer: Offer, task: OfferTask, now: datetime) -> bool:
    return task.answered_at is None and offer.status in _OPEN and now <= _aware(task.deadline_at)


async def item(session: AsyncSession, offer: Offer, task: OfferTask) -> dict[str, Any]:
    assert offer.candidate_id is not None
    return await get_bank().item(
        session, task.family_id, candidate_id=offer.candidate_id, offer_id=offer.id
    )


async def submit(
    session: AsyncSession, offer: Offer, task: OfferTask, answer: Any, now: datetime | None = None
) -> tuple[OfferTask, bool]:
    """Ответ кандидата: `(задача, replay)`, повтор отдаёт принятый ответ без изменений."""
    now = now or datetime.now(UTC)
    if task.answered_at is not None:
        return task, True
    if offer.status not in _OPEN:
        raise ProblemError(409, "offer_closed", "Приглашение закрыто, ответ не принимается")
    if now > _aware(task.deadline_at):
        raise ProblemError(409, "task_deadline_passed", "Срок решения задачи истёк")
    if len(str(answer)) > MAX_ANSWER_CHARS:
        raise ProblemError(422, "answer_too_long", "Ответ слишком длинный")
    assert offer.candidate_id is not None
    score = await get_bank().submit(
        session, task.family_id, candidate_id=offer.candidate_id, offer_id=offer.id,
        answer=answer,
    )  # fmt: skip
    task.answer = {"value": answer}
    task.score = None if score is None else max(0.0, min(1.0, float(score)))
    task.answered_at = now
    await session.flush()
    return task, False
