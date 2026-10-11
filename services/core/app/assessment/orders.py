"""Заказ LLM-заданий из админки: форма → очередь `ml.llm` → `draft`.

`POST /admin/assessment/generate` пишет строку `family_orders` (`queued`) и команду
`ml.families.generate` в outbox одной транзакцией. Команда идёт в `ml.llm` с низшим приоритетом
(0): разбор резюме и остальное, чего ждут люди, её обгоняют. ml-worker-llm отвечает событиями
`ml.families.started` (`running`) и `ml.families.generated` (`done`/`failed`); формы проходят тот
же путь, что в офлайн-конвейере `llm_bank` (схема, навык, дубли, автопроверка) и ложатся в
`families` со `status = draft`, `source = llm`. Дальше админ решает штатно (ключ, пилот).

Защиты: дневной лимит заказов (`family_orders_per_day`, сутки UTC) и повторный клик — такой же
заказ в работе за последние `DEDUP_MINUTES` возвращается вместо нового.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import structlog
from fsp_contracts import Envelope
from fsp_contracts.assessment import FamilyOrderGenerated, FamilyOrderStarted
from fsp_contracts.commands import MlFamiliesGenerate
from fsp_contracts.registry import new_command
from fsp_platform.app import ProblemError
from fsp_platform.messaging import Consumer, idempotent
from fsp_platform.outbox import add_to_outbox
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.assessment import llm_bank
from app.assessment.config import AssessmentConfig
from app.assessment.models import FamilyOrder
from app.taxonomy import service as taxonomy

log = structlog.get_logger()

PRODUCER = "core"
MAX_COUNT = 10
DEDUP_MINUTES = 10
ACTIVE = ("queued", "running")
FINAL = ("done", "failed")


def day_start(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


async def used_today(session: AsyncSession, now: datetime) -> int:
    q = select(func.count()).where(FamilyOrder.created_at >= day_start(now))
    return int(await session.scalar(q) or 0)


async def create(
    session: AsyncSession,
    *,
    skill: str,
    kind: str,
    level: int,
    count: int,
    user_id: uuid.UUID | None,
    per_day: int,
    now: datetime | None = None,
    correlation_id: str | None = None,
) -> tuple[FamilyOrder, bool]:
    """Новый заказ или тот же, что уже в работе (`True` — повторный клик). Без `commit`."""
    now = now or datetime.now(UTC)
    types = await taxonomy.skill_types_of(session, [skill])
    if skill not in types:
        raise ProblemError(422, "unknown_skill", "Такого навыка нет в справочнике")
    same = await session.scalar(
        select(FamilyOrder)
        .where(
            FamilyOrder.skill == skill,
            FamilyOrder.kind == kind,
            FamilyOrder.level == level,
            FamilyOrder.count == count,
            FamilyOrder.status.in_(ACTIVE),
            FamilyOrder.created_at >= now - timedelta(minutes=DEDUP_MINUTES),
        )
        .order_by(FamilyOrder.created_at.desc())
        .limit(1)
    )
    if same is not None:
        return same, True
    if await used_today(session, now) >= per_day:
        raise ProblemError(
            429,
            "daily_limit",
            "Дневной лимит заказов исчерпан",
            f"Не больше {per_day} заказов в сутки; новые — завтра",
        )
    order = FamilyOrder(
        id=uuid.uuid4(),
        skill=skill,
        kind=kind,
        level=level,
        count=count,
        status="queued",
        rejected={},
        slugs=[],
        requested_by=user_id,
        created_at=now,
        updated_at=now,
    )
    session.add(order)
    payload = MlFamiliesGenerate(
        order_id=order.id,
        skill=skill,
        skill_type=types[skill].value,
        kind=kind,  # type: ignore[arg-type]
        level=level,
        n=count,
    )
    env, _ = new_command("ml.families.generate", PRODUCER, payload, correlation_id=correlation_id)
    await add_to_outbox(session, env, order.id)
    log.info("family_order_created", order_id=str(order.id), kind=kind, level=level, n=count)
    return order, False


async def recent(session: AsyncSession, limit: int = 20) -> list[FamilyOrder]:
    q = select(FamilyOrder).order_by(FamilyOrder.created_at.desc()).limit(limit)
    return list(await session.scalars(q))


async def on_started(session: AsyncSession, p: FamilyOrderStarted) -> None:
    order = await session.get(FamilyOrder, p.order_id)
    if order is not None and order.status == "queued":
        order.status = "running"


async def on_generated(
    session: AsyncSession, p: FamilyOrderGenerated, cfg: AssessmentConfig
) -> FamilyOrder | None:
    """Формы генератора → черновики. Заказ в финальном статусе не трогается (версия заказа)."""
    order = await session.get(FamilyOrder, p.order_id)
    if order is None or order.status in FINAL:
        return order
    order.model = p.model or None
    if p.error is not None or not p.specs:
        order.status, order.error = "failed", p.error or "empty"
        return order
    target = llm_bank.Target(
        skill=order.skill,
        kind=order.kind,  # type: ignore[arg-type]
        level=order.level,
        n=order.count,
        order=str(order.id),
    )
    report = await llm_bank.accept(
        session, llm_bank.GeneratedOnly(), cfg, target, p.specs[: order.count], p.model
    )
    order.created = report.passed
    order.slugs = list(report.created)
    order.rejected = dict(report.rejected)
    order.status, order.error = "done", None
    log.info(
        "family_order_done",
        order_id=str(order.id),
        proposed=report.proposed,
        created=report.passed,
        rejected=dict(report.rejected),
    )
    return order


def register(
    consumers: Mapping[str, Consumer],
    session_factory: async_sessionmaker[AsyncSession],
    cfg: AssessmentConfig,
) -> None:
    @consumers["core.ingest"].on("ml.families.started")
    @idempotent(session_factory, "assessment.family_order_started")
    async def started(envelope: Envelope, session: AsyncSession) -> None:
        await on_started(session, FamilyOrderStarted.model_validate(envelope.payload))

    @consumers["core.ingest"].on("ml.families.generated")
    @idempotent(session_factory, "assessment.family_order_generated")
    async def generated(envelope: Envelope, session: AsyncSession) -> None:
        await on_generated(session, FamilyOrderGenerated.model_validate(envelope.payload), cfg)
