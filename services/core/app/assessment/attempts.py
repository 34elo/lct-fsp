"""Попытка теста: банк семейств, выдача заданий, приём ответов (assessment.md §3–6).

- Выбор задания (E22-3, §6): секция с наибольшим дефицитом → фильтры банка → топ-3 по счёту
  у порога грейда этапа (`engine.py`, `selection.py`); пилотные слоты — скрытые позиции.
- Остановка (E22-3, §5): SPRT после каждого оцениваемого ответа (`sprt.py`); прошёл быстро и
  близко к следующему грейду → бонусный этап в той же попытке (`stage = bonus`).
- Завершение: θ/SE по EAP и калибровка `b` (E22-2, `psychometrics_db`). Грейды и события — E22-4.

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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import engine, grading, sprt, telemetry
from app.assessment import families as registry
from app.assessment import selection as sel
from app.assessment.config import AssessmentConfig
from app.assessment.families.base import Family, Item
from app.assessment.models import Attempt, FamilyRow, Grade, Response
from app.assessment.psychometrics_db import finalize_attempt
from app.assessment.world import DOMAINS, World, domain_for_profession
from app.taxonomy import service as taxonomy

_NS = uuid.UUID("3f0c7d2e-6a1b-4c55-9f0e-5b2a7f9d1c33")


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

    Новое семейство: `b` — априорная по уровню; статус `active` только у стартового банка (в таблице
    ещё нет кодовых семейств), позже добавленные идут в `pilot` и ждут допуска админом (E22-9).
    У существующего обновляются только описательные поля; `b`, `n`, `status`, `stats` принадлежат
    калибровке и админу.
    """
    rows = {
        r.slug: r
        for r in await session.scalars(select(FamilyRow).where(FamilyRow.source == "code"))
    }
    initial = "active" if not rows else "pilot"
    for fam in registry.REGISTRY.values():
        row = rows.get(fam.slug)
        if row is None:
            row = FamilyRow(
                id=family_id(fam.slug),
                slug=fam.slug,
                source="code",
                status=initial,
                b=cfg.prior_b(fam.level),
                anchor=bool(getattr(fam, "anchor", False)),
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


def _skills_of(prof) -> tuple[dict[str, float], dict[str, str]]:
    return dict(prof.skill_weights), {k: SkillType(v).value for k, v in prof.skill_types.items()}


async def _profession(session: AsyncSession, profession: str):
    profs = {p.slug: p for p in await taxonomy.list_professions(session)}
    return profs.get(profession)


async def create_attempt(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    profession: str,
    declared_grade: TestGrade,
    cfg: AssessmentConfig,
) -> Attempt:
    prof = await _profession(session, profession)
    if prof is None:
        raise ProblemError(
            422,
            "unknown_profession",
            "Неизвестная профессия",
            errors=[{"field": "profession", "message": profession}],
        )
    await grading.check_cooldown(session, candidate_id, profession, declared_grade, cfg)
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
    weights, types = _skills_of(prof)
    sections = await engine.stage_plan(session, candidate_id, weights, types, declared_grade, cfg)
    if not sections:
        raise ProblemError(503, "no_items", "Для профессии и грейда пока нет заданий")
    att = Attempt(
        id=uuid.uuid4(),
        candidate_id=candidate_id,
        profession=profession,
        declared_grade=declared_grade.value,
        stage="main",
        status="active",
        llr=0.0,
    )
    rng = Random(item_seed(candidate_id, att.id, uuid.UUID(int=0)))
    att.plan = {
        "domain": domain_for_profession(profession) or rng.choice(DOMAINS),
        "sections": engine.sections_json(sections),
        "pilot_seqs": sel.pilot_positions(rng, cfg),
        "target": cfg.min_items,
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


def _stage_grade(att: Attempt) -> TestGrade:
    if att.stage == "bonus":
        return TestGrade(att.plan["bonus"]["grade"])
    return TestGrade(att.declared_grade)


def _stage_from(att: Attempt) -> int:
    """Последний `seq` до начала этапа: задания этапа — с `seq` больше этого."""
    return int(att.plan["bonus"]["from_seq"]) if att.stage == "bonus" else 0


def _stage_scored(att: Attempt, issued: list[Response]) -> list[Response]:
    start = _stage_from(att)
    return [r for r in issued if not r.is_pilot and r.seq > start]


async def _finish(session: AsyncSession, att: Attempt, status: str, cfg: AssessmentConfig) -> None:
    att.status = status
    att.finished_at = datetime.now(UTC)
    await telemetry.assess_attempt(session, att, cfg)  # E24-1: до калибровки `b`
    await finalize_attempt(session, att, cfg)
    await grading.on_finished(session, att, cfg)


async def _conclude(
    session: AsyncSession,
    att: Attempt,
    decision: sprt.Decision,
    n_scored: int,
    issued: list[Response],
    cfg: AssessmentConfig,
) -> None:
    """Итог этапа. Основной этап → бонус (если положен и есть задания) или завершение."""
    summary = {
        "result": decision.result,
        "low_confidence": decision.low_confidence,
        "items": n_scored,
        "llr": att.llr,
    }
    if att.stage == "bonus":
        bonus = {**att.plan["bonus"], **summary}
        offer = bonus["grade"] if decision.result == "passed" else None
        att.plan = {**att.plan, "bonus": bonus, "upgrade_offer": offer}
        await _finish(session, att, "passed", cfg)  # основной этап уже пройден
        return
    att.plan = {**att.plan, "main": summary}
    grade = TestGrade(att.declared_grade)
    theta = (await engine.current_estimate(session, att.id, cfg)).theta
    nxt = sprt.bonus_eligible(grade, decision, n_scored, theta, cfg)
    if nxt is not None:
        prof = await _profession(session, att.profession)
        weights, types = _skills_of(prof) if prof else ({}, {})
        sections = await engine.stage_plan(session, att.candidate_id, weights, types, nxt, cfg)
        if sections:
            att.stage = "bonus"
            att.llr = 0.0
            bonus = {
                "grade": nxt.value,
                "from_seq": len(issued),
                "sections": engine.sections_json(sections),
            }
            att.plan = {**att.plan, "bonus": bonus}
            await session.flush()
            return
    await _finish(session, att, decision.result, cfg)


async def _exhausted(
    session: AsyncSession, att: Attempt, issued: list[Response], cfg: AssessmentConfig
) -> None:
    """Банк этапа кончился: решение по EAP с пометкой «низкая уверенность»."""
    n = len(_stage_scored(att, issued))
    if att.stage == "bonus" and n == 0:  # бонус без заданий повышения не даёт
        decision = sprt.Decision("failed", True)
    else:
        theta = (await engine.current_estimate(session, att.id, cfg)).theta
        cut = cfg.cuts[_stage_grade(att).value]
        decision = sprt.Decision("passed" if theta >= cut else "failed", True)
    await _conclude(session, att, decision, n, issued, cfg)


async def _present(session: AsyncSession, att: Attempt, resp: Response) -> dict[str, Any]:
    item = build_item(await _family(session, resp.family_id), resp.seed, att.plan.get("domain"))
    out = {"response_id": resp.id, "seq": resp.seq, **item.public()}
    out["time_limit_s"] = await telemetry.time_limit_for(session, resp.family_id, item.time_limit_s)
    return out


async def _skill_counts(
    session: AsyncSession, sections: list[sel.Section], scored: list[Response]
) -> dict[str, int]:
    """Сколько оцениваемых заданий этапа уже выдано в каждой секции (навыке)."""
    slugs = {taxonomy.skill_id(s.skill): s.skill for s in sections}
    out: dict[str, int] = {}
    if not scored:
        return out
    rows = await session.execute(
        select(FamilyRow.id, FamilyRow.skill_id).where(
            FamilyRow.id.in_({r.family_id for r in scored})
        )
    )
    skill_of = dict(rows.all())
    for r in scored:
        slug = slugs.get(skill_of.get(r.family_id))
        if slug is not None:
            out[slug] = out.get(slug, 0) + 1
    return out


async def _pick(
    session: AsyncSession, att: Attempt, issued: list[Response], cfg: AssessmentConfig
) -> tuple[uuid.UUID, bool] | None:
    """Следующее семейство этапа и признак пилота; `None` — банк этапа исчерпан."""
    seq = len(issued) + 1
    rng = Random(item_seed(att.candidate_id, att.id, uuid.UUID(int=seq)))
    stage_sections = engine.sections_of(
        att.plan["bonus"]["sections"] if att.stage == "bonus" else att.plan["sections"]
    )
    if att.stage == "main" and seq in att.plan.get("pilot_seqs", []):
        skills = [s["skill"] for s in att.plan["sections"]]
        pilot = await engine.pick_pilot(session, att.candidate_id, skills, rng, cfg)
        if pilot is not None:
            return pilot, True
    scored = _stage_scored(att, issued)
    counts = await _skill_counts(session, stage_sections, scored)
    fam = await engine.pick_regular(
        session, att.candidate_id, stage_sections, _stage_grade(att), counts, len(scored), rng, cfg
    )
    return (fam, False) if fam is not None else None


async def next_item(
    session: AsyncSession, candidate_id: uuid.UUID, attempt_id: uuid.UUID, cfg: AssessmentConfig
) -> dict[str, Any]:
    """Текущее неотвеченное задание или новое; `{done: true}`, если попытка завершена."""
    att = await _own_attempt(session, candidate_id, attempt_id)
    for _ in range(2):  # второй проход — первое задание бонусного этапа
        if att.status != "active":
            return {"done": True}
        issued = await _issued(session, att.id)
        pending = next((r for r in issued if r.answered_at is None), None)
        if pending is not None:  # повторный GET не выдаёт новое задание
            return await _present(session, att, pending)
        picked = await _pick(session, att, issued, cfg)
        if picked is None:
            await _exhausted(session, att, issued, cfg)
            continue
        fam_id, is_pilot = picked
        resp = Response(
            attempt_id=att.id,
            seq=len(issued) + 1,
            family_id=fam_id,
            seed=item_seed(candidate_id, att.id, fam_id),
            is_pilot=is_pilot,
        )
        session.add(resp)
        await session.flush()
        return await _present(session, att, resp)
    return {"done": att.status != "active"}  # pragma: no cover - бонус без заданий не стартует


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
    """Проверка на сервере пересборкой; SPRT после оцениваемого ответа. Повтор ничего не меняет."""
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
        if not resp.is_pilot:  # пилот не влияет на θ и LLR
            await _after_scored(session, att, resp, cfg)
    return {"response_id": resp.id, "accepted": True, "done": att.status != "active"}


async def _after_scored(
    session: AsyncSession, att: Attempt, resp: Response, cfg: AssessmentConfig
) -> None:
    row = await session.get(FamilyRow, resp.family_id)
    cut = cfg.cuts[_stage_grade(att).value]
    att.llr = (att.llr or 0.0) + sprt.llr_increment(cut, row.b, resp.score or 0.0, cfg)
    issued = await _issued(session, att.id)
    n = len(_stage_scored(att, issued))
    bonus = att.stage == "bonus"
    max_items = cfg.bonus_max_items if bonus else cfg.max_items
    theta = None
    if n >= max_items:
        theta = (await engine.current_estimate(session, att.id, cfg)).theta
    decision = sprt.decide(
        att.llr,
        n,
        min_items=0 if bonus else cfg.min_items,
        max_items=max_items,
        exhausted=False,
        theta=theta,
        cut=cut,
        cfg=cfg,
    )
    if decision is not None:
        await _conclude(session, att, decision, n, issued, cfg)
    else:
        await session.flush()


async def _by_skill(session: AsyncSession, attempt_id: uuid.UUID) -> list[dict[str, Any]]:
    """Разбор по навыкам: сколько оцениваемых заданий и какая доля набрана (без ключей)."""
    rows = (
        await session.execute(
            select(Response.score, FamilyRow.slug)
            .join(FamilyRow, FamilyRow.id == Response.family_id)
            .where(
                Response.attempt_id == attempt_id,
                Response.answered_at.is_not(None),
                Response.is_pilot.is_(False),
            )
        )
    ).all()
    acc: dict[str, list[float]] = {}
    for score, fam_slug in rows:
        fam = registry.get(fam_slug)
        if fam is not None:
            acc.setdefault(fam.skill, []).append(score or 0.0)
    return [
        {"skill": k, "items": len(v), "share": round(sum(v) / len(v), 4)}
        for k, v in sorted(acc.items())
    ]


async def attempt_summary(
    session: AsyncSession, candidate_id: uuid.UUID, attempt_id: uuid.UUID
) -> dict[str, Any]:
    """Состояние попытки; у завершённой — итог: грейд, θ, честность, разбор по навыкам."""
    att = await _own_attempt(session, candidate_id, attempt_id)
    answered = [r for r in await _issued(session, att.id) if r.answered_at is not None]
    main = att.plan.get("main") or {}
    bonus = att.plan.get("bonus") or {}
    offer = att.plan.get("upgrade_offer")
    out: dict[str, Any] = {
        "id": att.id,
        "profession": att.profession,
        "declared_grade": TestGrade(att.declared_grade),
        "stage": att.stage,
        "status": att.status,
        "answered": len(answered),
        "target": att.plan.get("target", 0),
        "started_at": att.started_at,
        "finished_at": att.finished_at,
        "low_confidence": bool(main.get("low_confidence") or bonus.get("low_confidence")),
        "upgrade_offer": TestGrade(offer) if offer else None,
        "upgrade_accepted": bool(att.plan.get("upgrade_accepted_at")),
    }
    if att.status != "active":
        grade_row = await session.get(Grade, (att.candidate_id, att.profession))
        confirmed = grade_row is not None and grade_row.attempt_id == att.id
        integrity = att.integrity if att.integrity is not None else 1.0
        out["result"] = {
            "grade": TestGrade(grade_row.grade) if confirmed else None,
            "theta": att.theta,
            "se": att.se,
            "theta_by_type": att.plan.get("theta_by_type") or {},
            "integrity": integrity,
            "needs_confirmation": confirmed and bool(grade_row.needs_confirmation),
            "by_skill": await _by_skill(session, att.id),
        }
    return out
