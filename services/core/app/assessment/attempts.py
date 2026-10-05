"""Попытка теста: банк семейств, выдача заданий, приём ответов (assessment.md §3–5, E22-1).

Каркас без психометрии: порядок заданий фиксируется при создании попытки (навыки профессии,
уровень около заявленного грейда, чередование типов навыков), попытка — `items.min` заданий,
итог — средняя доля ≥ `simple_pass_share`. Rasch/EAP/SPRT и выбор по дефициту — E22-2/E22-3,
грейды и события — E22-4.

Ключ на клиент не уходит: в `responses` лежат только `(family_id, seed)`, задание пересобирается
на сервере при выдаче и при проверке.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from random import Random
from typing import Any

from fsp_contracts.assessment import SkillType, TestGrade
from fsp_platform.app import ProblemError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import families as registry
from app.assessment.config import AssessmentConfig
from app.assessment.families.base import Family, Item
from app.assessment.models import Attempt, FamilyRow, Response
from app.assessment.world import DOMAINS, World
from app.taxonomy import service as taxonomy

_NS = uuid.UUID("3f0c7d2e-6a1b-4c55-9f0e-5b2a7f9d1c33")
# Уровень семейства, ближайший к порогу грейда: b(level) = cut (junior −1 → 2, middle 0 → 3, …)
_GRADE_LEVEL = {TestGrade.junior: 2, TestGrade.middle: 3, TestGrade.senior: 4}
_PROFESSION_DOMAIN = {"ai_engineer": "rag_service"}


def family_id(slug: str) -> uuid.UUID:
    """Стабильный id кодового семейства: одинаков в любой среде."""
    return uuid.uuid5(_NS, f"family:{slug}")


def item_seed(candidate_id: uuid.UUID, attempt_id: uuid.UUID, fam_id: uuid.UUID) -> int:
    """seed = hash(candidate_id, attempt_id, family_id) (assessment.md §3), 63 бита."""
    h = hashlib.sha256(f"{candidate_id}:{attempt_id}:{fam_id}".encode()).digest()
    return int.from_bytes(h[:8], "big") & (2**63 - 1)


def build_item(fam: Family, seed: int, domain: str | None) -> Item:
    """Пересборка варианта: тот же `(семейство, сид, домен)` → то же задание и тот же ключ."""
    return fam.generate(Random(seed), World.from_seed(seed, domain))


async def sync_code_families(session: AsyncSession, cfg: AssessmentConfig) -> None:
    """Реестр кодовых семейств → таблица `families` (идемпотентно).

    Новое семейство: статус `active`, `b` — априорная по уровню. У существующего обновляются
    только описательные поля; `b`, `n`, `status`, `stats` принадлежат калибровке и админу.
    """
    rows = {
        r.slug: r
        for r in await session.scalars(select(FamilyRow).where(FamilyRow.source == "code"))
    }
    for fam in registry.REGISTRY.values():
        row = rows.get(fam.slug)
        if row is None:
            row = FamilyRow(
                id=family_id(fam.slug),
                slug=fam.slug,
                source="code",
                status="active",
                b=cfg.prior_b(fam.level),
                key_status="approved",
            )
            session.add(row)
        row.kind = fam.kind.value
        row.skill_id = taxonomy.skill_id(fam.skill)
        row.skill_type = SkillType(fam.skill_type).value
        row.level = fam.level
    await session.flush()


def _not_found() -> ProblemError:
    return ProblemError(404, "not_found", "Попытка не найдена")


async def _own_attempt(
    session: AsyncSession, candidate_id: uuid.UUID, attempt_id: uuid.UUID
) -> Attempt:
    att = await session.get(Attempt, attempt_id)
    if att is None or att.candidate_id != candidate_id:
        raise _not_found()  # чужой ресурс → 404
    return att


def _order(rows: list[FamilyRow], skill_ids: set[uuid.UUID], grade: TestGrade, rng: Random):
    """Простой порядок: навыки профессии, уровень ±1 от грейда, чередование типов навыков."""
    target = _GRADE_LEVEL[grade]
    pool = [r for r in rows if r.skill_id in skill_ids and abs(r.level - target) <= 1]
    if not pool:  # маленький банк каркаса: не нашли под профессию — берём всё активное
        pool = list(rows)
    pool.sort(key=lambda r: r.slug)
    rng.shuffle(pool)
    by_type: dict[str, list[FamilyRow]] = {}
    for r in pool:
        by_type.setdefault(r.skill_type, []).append(r)
    types = [t.value for t in SkillType if t.value in by_type]
    out: list[FamilyRow] = []
    while any(by_type.values()):
        for t in types:
            if by_type[t]:
                out.append(by_type[t].pop(0))
    return out


async def create_attempt(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    profession: str,
    declared_grade: TestGrade,
    cfg: AssessmentConfig,
) -> Attempt:
    profs = {p.slug: p for p in await taxonomy.list_professions(session)}
    prof = profs.get(profession)
    if prof is None:
        raise ProblemError(
            422,
            "unknown_profession",
            "Неизвестная профессия",
            errors=[{"field": "profession", "message": profession}],
        )
    active = await session.scalar(
        select(Attempt.id).where(
            Attempt.candidate_id == candidate_id,
            Attempt.profession == profession,
            Attempt.status == "active",
        )
    )
    if active is not None:
        raise ProblemError(409, "attempt_active", "Есть незавершённая попытка", str(active))

    await sync_code_families(session, cfg)
    att = Attempt(
        id=uuid.uuid4(),
        candidate_id=candidate_id,
        profession=profession,
        declared_grade=declared_grade.value,
        stage="main",
        status="active",
    )
    rng = Random(item_seed(candidate_id, att.id, uuid.UUID(int=0)))
    rows = list(await session.scalars(select(FamilyRow).where(FamilyRow.status == "active")))
    skill_ids = {taxonomy.skill_id(s) for s in prof.skill_weights}
    order = _order(rows, skill_ids, declared_grade, rng)
    att.plan = {
        "domain": _PROFESSION_DOMAIN.get(profession) or rng.choice(DOMAINS),
        "order": [str(r.id) for r in order],
        "target": min(cfg.min_items, len(order)),
    }
    session.add(att)
    await session.flush()
    return att


async def _issued(session: AsyncSession, attempt_id: uuid.UUID) -> list[Response]:
    return list(
        await session.scalars(
            select(Response).where(Response.attempt_id == attempt_id).order_by(Response.seq)
        )
    )


async def _family(session: AsyncSession, fam_id: uuid.UUID) -> Family:
    row = await session.get(FamilyRow, fam_id)
    fam = registry.get(row.slug) if row is not None and row.source == "code" else None
    if fam is None:  # spec-семейства (конструктор) появятся позже
        raise ProblemError(503, "family_unavailable", "Семейство заданий недоступно")
    return fam


async def _finish(session: AsyncSession, att: Attempt, cfg: AssessmentConfig) -> None:
    mean = await session.scalar(
        select(func.avg(Response.score)).where(
            Response.attempt_id == att.id,
            Response.answered_at.is_not(None),
            Response.is_pilot.is_(False),
        )
    )
    att.status = "passed" if (mean or 0.0) >= cfg.simple_pass_share else "failed"
    att.finished_at = datetime.now(UTC)
    await session.flush()


async def _present(session: AsyncSession, att: Attempt, resp: Response) -> dict[str, Any]:
    item = build_item(await _family(session, resp.family_id), resp.seed, att.plan.get("domain"))
    return {"response_id": resp.id, "seq": resp.seq, **item.public()}


async def next_item(
    session: AsyncSession, candidate_id: uuid.UUID, attempt_id: uuid.UUID, cfg: AssessmentConfig
) -> dict[str, Any]:
    """Текущее неотвеченное задание или новое; `{done: true}`, если попытка завершена."""
    att = await _own_attempt(session, candidate_id, attempt_id)
    if att.status != "active":
        return {"done": True}
    issued = await _issued(session, att.id)
    pending = next((r for r in issued if r.answered_at is None), None)
    if pending is not None:  # повторный GET не выдаёт новое задание
        return await _present(session, att, pending)
    used = {str(r.family_id) for r in issued}
    rest = [f for f in att.plan.get("order", []) if f not in used]
    if len(issued) >= att.plan.get("target", 0) or not rest:
        await _finish(session, att, cfg)
        return {"done": True}
    fam_id = uuid.UUID(rest[0])
    resp = Response(
        attempt_id=att.id,
        seq=len(issued) + 1,
        family_id=fam_id,
        seed=item_seed(candidate_id, att.id, fam_id),
        is_pilot=False,
    )
    session.add(resp)
    await session.flush()
    return await _present(session, att, resp)


async def submit_answer(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    attempt_id: uuid.UUID,
    response_id: uuid.UUID,
    answer: Any,
    rt_ms: int | None,
    telemetry: dict | None,
    cfg: AssessmentConfig,
) -> dict[str, Any]:
    """Проверка на сервере пересборкой. Повтор с тем же `response_id` ничего не меняет."""
    att = await _own_attempt(session, candidate_id, attempt_id)
    resp = await session.get(Response, response_id)
    if resp is None or resp.attempt_id != att.id:
        raise ProblemError(404, "not_found", "Задание не найдено")
    if resp.answered_at is None:
        if att.status != "active":
            raise ProblemError(409, "attempt_finished", "Попытка уже завершена")
        fam = await _family(session, resp.family_id)
        item = build_item(fam, resp.seed, att.plan.get("domain"))
        resp.answer = answer
        resp.score = max(0.0, min(1.0, float(fam.score(item, answer))))
        resp.rt_ms = rt_ms
        resp.telemetry = telemetry
        resp.answered_at = datetime.now(UTC)
        await session.flush()
        answered = sum(1 for r in await _issued(session, att.id) if r.answered_at is not None)
        if answered >= att.plan.get("target", 0):
            await _finish(session, att, cfg)
    return {"response_id": resp.id, "accepted": True, "done": att.status != "active"}


async def attempt_summary(
    session: AsyncSession, candidate_id: uuid.UUID, attempt_id: uuid.UUID
) -> dict[str, Any]:
    """Состояние попытки. Итог с грейдом, θ по типам и разбором — E22-4."""
    att = await _own_attempt(session, candidate_id, attempt_id)
    answered = [r for r in await _issued(session, att.id) if r.answered_at is not None]
    return {
        "id": att.id,
        "profession": att.profession,
        "declared_grade": TestGrade(att.declared_grade),
        "stage": att.stage,
        "status": att.status,
        "answered": len(answered),
        "target": att.plan.get("target", 0),
        "started_at": att.started_at,
        "finished_at": att.finished_at,
    }
