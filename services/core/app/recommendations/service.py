"""Сервис для логирования показов и реакций.

Каждая выдача в поиске/подборке должна логировать impressions.
Работодатель может отправить rec_feedback на любую impression.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.recommendations import tuning
from app.recommendations.models import Impression, RecFeedback


async def record_impression(
    session: AsyncSession,
    company_id: UUID,
    user_id: UUID,
    session_id: str,
    context_type: str,  # vacancy | search | similar
    context_id: str,
    candidate_id: UUID,
    position: int,
    score: float,
    features: dict[str, Any] | None = None,
    model_version: str | None = None,
) -> Impression:
    """Записать показ кандидата в выдаче."""
    impression = Impression(
        company_id=company_id,
        user_id=user_id,
        session_id=session_id,
        context_type=context_type,
        context_id=context_id,
        candidate_id=candidate_id,
        position=position,
        score=score,
        features=features,
        model_version=model_version,
    )
    session.add(impression)
    await session.flush()
    return impression


async def record_feedback(
    session: AsyncSession,
    impression_id: int,
    company_id: UUID,
    user_id: UUID,
    session_id: str,
    candidate_id: UUID,
    event: str,  # open | dwell | shortlist | dismiss
    reason: str | None = None,
) -> RecFeedback:
    """Записать реакцию на показ."""
    feedback = RecFeedback(
        impression_id=impression_id,
        company_id=company_id,
        user_id=user_id,
        session_id=session_id,
        candidate_id=candidate_id,
        event=event,
        reason=reason,
    )
    session.add(feedback)
    await session.flush()
    return feedback


async def find_last_impression(
    session: AsyncSession, company_id: UUID, session_id: str, candidate_id: UUID
) -> Impression | None:
    """Последний показ кандидата в сессии для компании."""
    return await session.scalar(
        select(Impression)
        .where(
            Impression.company_id == company_id,
            Impression.session_id == session_id,
            Impression.candidate_id == candidate_id,
        )
        .order_by(Impression.id.desc())
        .limit(1)
    )


async def shown_without_action(
    session: AsyncSession, company_id: UUID, candidate_ids: list[UUID]
) -> dict[UUID, int]:
    """Сколько раз кандидат показан компании без единой реакции (rec_feedback) на него."""
    if not candidate_ids:
        return {}
    acted = (
        select(RecFeedback.id)
        .where(
            RecFeedback.company_id == Impression.company_id,
            RecFeedback.candidate_id == Impression.candidate_id,
        )
        .exists()
    )
    q = (
        select(Impression.candidate_id, func.count())
        .where(
            Impression.company_id == company_id,
            Impression.candidate_id.in_(candidate_ids),
            ~acted,
        )
        .group_by(Impression.candidate_id)
    )
    return {cid: n for cid, n in (await session.execute(q)).all()}


# --- подстройка в сессии -------------------------------------------

RESET_KEY = "s:rec:{user}:{session}"


async def session_owned(session: AsyncSession, user_id: UUID, session_id: str) -> bool:
    """Сессия принадлежит пользователю работодателя: в ней есть его показы."""
    hit = await session.scalar(
        select(Impression.id)
        .where(Impression.user_id == user_id, Impression.session_id == session_id)
        .limit(1)
    )
    return hit is not None


async def _reset_after(redis: Any, user_id: UUID, session_id: str) -> int:
    if redis is None:
        return 0
    try:
        raw = await redis.get(RESET_KEY.format(user=user_id, session=session_id))
    except Exception:  # noqa: BLE001 — без Redis сброса просто нет
        return 0
    return int(raw) if raw else 0


async def session_signals(
    session: AsyncSession,
    redis: Any,
    user_id: UUID,
    session_id: str,
    cfg: tuning.TuningConfig,
    now: datetime | None = None,
) -> tuple[list[tuning.Signal], dict[str, dict[str, float]]]:
    """Сигналы сессии (за `session_ttl_hours`, после сброса) и снимки признаков показов.

    Ключ кандидата — `str(candidate_id)`. Снимок — последний показ кандидата в сессии.
    """
    since = (now or datetime.now(UTC)) - timedelta(hours=cfg.session_ttl_hours)
    after = await _reset_after(redis, user_id, session_id)
    rows = (
        await session.scalars(
            select(RecFeedback)
            .where(
                RecFeedback.user_id == user_id,
                RecFeedback.session_id == session_id,
                RecFeedback.id > after,
            )
            .order_by(RecFeedback.id)
        )
    ).all()
    signals = [
        tuning.Signal(str(f.candidate_id), f.event, f.reason)
        for f in rows
        if _utc(f.created_at) >= since
    ]
    imps = (
        await session.scalars(
            select(Impression)
            .where(Impression.user_id == user_id, Impression.session_id == session_id)
            .order_by(Impression.id)
        )
    ).all()
    features: dict[str, dict[str, float]] = {}
    for imp in imps:
        x = (imp.features or {}).get("x")
        if isinstance(x, dict):
            features[str(imp.candidate_id)] = {k: float(v) for k, v in x.items()}
    return signals, features


async def reset_session(session: AsyncSession, redis: Any, user_id: UUID, session_id: str) -> None:
    """Сброс подстройки: учитываются только реакции после текущей последней."""
    last = await session.scalar(
        select(func.max(RecFeedback.id)).where(
            RecFeedback.user_id == user_id, RecFeedback.session_id == session_id
        )
    )
    cfg_ttl = tuning.TuningConfig.load().session_ttl_hours
    await redis.set(
        RESET_KEY.format(user=user_id, session=session_id), str(last or 0), ex=cfg_ttl * 3600
    )


def summary(
    signals: list[tuning.Signal], features: dict[str, dict[str, float]], cfg: tuning.TuningConfig
) -> dict[str, Any]:
    """Состояние подстройки для чипсов «Учли: …» (без вектора Роккио — он считается в выдаче)."""
    t = tuning.build(signals, features, cfg)
    return {
        "active": t.active,
        "signals": t.signals,
        "min_signals": cfg.min_signals,
        "weights": [
            {
                "feature": k,
                "start": cfg.w0[k],
                "current": t.weights[k],
                "change": round(t.weights[k] / cfg.w0[k] - 1, 4) if cfg.w0[k] else 0.0,
            }
            for k in tuning.FEATURES
        ],  # fmt: skip
        "chips": tuning.chips(t.weights, cfg) if t.active else [],
        "hints": t.hints,
    }


def _utc(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=UTC)
