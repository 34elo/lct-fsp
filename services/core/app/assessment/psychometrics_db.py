"""Психометрия попытки поверх БД: θ/SE/θ по типам и калибровка `b`.

Вызывается при завершении попытки (один раз — при смене статуса с `active`):
1. θ и SE — EAP по оцениваемым ответам (пилотные не влияют на θ);
2. θ по типам навыков → `attempts.plan["theta_by_type"]` (в `grades` переносит
`grading.on_finished`);
3. калибровка `b` всех отвеченных семейств, включая пилотные, по **финальному** θ; `n += 1`.
   Якорные семейства (`anchor`) держат шкалу: `b` не меняется, `n` растёт.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.config import AssessmentConfig
from app.assessment.models import Attempt, FamilyRow, Response
from app.assessment.psychometrics import Estimate, Observation, calibrate_b, eap, theta_by_type


async def _answered(session: AsyncSession, attempt_id) -> list[tuple[Response, FamilyRow]]:
    rows = await session.execute(
        select(Response, FamilyRow)
        .join(FamilyRow, FamilyRow.id == Response.family_id)
        .where(Response.attempt_id == attempt_id, Response.answered_at.is_not(None))
        .order_by(FamilyRow.id)  # единый порядок блокировок
        .with_for_update(of=FamilyRow)
    )
    return [(r, f) for r, f in rows.all()]


async def finalize_attempt(session: AsyncSession, att: Attempt, cfg: AssessmentConfig) -> Estimate:
    """Финальная оценка попытки и калибровка банка. Записывает `theta`, `se` в попытку."""
    answered = await _answered(session, att.id)
    obs = [
        Observation(b=f.b, score=r.score or 0.0, skill_type=f.skill_type)
        for r, f in answered
        if not r.is_pilot
    ]
    est = eap(obs, cfg)
    att.theta = est.theta
    att.se = est.se
    att.plan = {**(att.plan or {}), "theta_by_type": theta_by_type(obs, cfg)}
    fsp_known: bool | None = None  # у кандидата есть доказательства ФСП (считаем лениво)
    for r, f in answered:
        if f.source == "fsp":
            # Шкала задач ФСП задаётся остальной аудиторией: ответы тех, у кого есть
            # ФСП, на `b` не влияют — иначе «решаемость среди олимпиадников» занизила бы b.
            if fsp_known is None:
                from app.graph import service as graph

                fsp_known = await graph.has_source(session, att.candidate_id, "fsp")
            if fsp_known:
                continue
        f.b = calibrate_b(f.b, f.n, est.theta, r.score or 0.0, cfg, anchor=f.anchor)
        f.n += 1
    await session.flush()
    return est
