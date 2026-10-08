"""Навигатор кандидата: путь к следующему грейду (matching.md §6, api.md `Navigator`).

Грейды берём из `assessment.service` (blocks.md §4.3), профессии и веса — из `taxonomy.service`.
Пробелы по навыкам профессии, соревнования ФСП и uplift — детерминированно, без LLM.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fsp_contracts.assessment import TEST_GRADE_ORDER, CandidateGrade
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import service as assessment
from app.candidates.models import Candidate
from app.graph import service as graph
from app.matching.uplift import UpliftConfig
from app.taxonomy import service as taxonomy

GAPS_MAX = 8  # сколько навыков профессии показываем как «поднять»
COMPETITIONS_MAX = 5
UPLIFT_TOP = 3  # api.md: топ-3 uplift в навигаторе


def pick_current(grades: list[CandidateGrade], primary_role: str | None) -> CandidateGrade | None:
    """Основная профессия, если по ней есть грейд, иначе самый высокий грейд."""
    if not grades:
        return None
    for g in grades:
        if g.profession == primary_role:
            return g
    return max(grades, key=lambda g: (TEST_GRADE_ORDER.index(g.grade), g.theta))


def next_test_grade(current: str | None) -> str | None:
    """Следующий грейд теста: нет грейда — первый; у старшего следующего нет."""
    order = [g.value for g in TEST_GRADE_ORDER]
    if current is None:
        return order[0]
    i = order.index(current)
    return order[i + 1] if i + 1 < len(order) else None


def pick_gaps(
    weights: dict[str, float], held: dict[str, float], threshold: float, limit: int = GAPS_MAX
) -> list[tuple[str, float, float]]:
    """Навыки профессии с уверенностью ниже порога: (slug, вес, текущая уверенность).

    Сначала самые типичные для профессии (вес), при равенстве — слабее подтверждённые.
    """
    rows = [(s, w, held.get(s, 0.0)) for s, w in weights.items() if held.get(s, 0.0) < threshold]
    rows.sort(key=lambda r: (-r[1], r[2], r[0]))
    return rows[:limit]


def assessment_path(profession: str, grade: str) -> str:
    """Ссылка на тест в блок 1 (blocks.md §4.8)."""
    return f"/me/assessment?profession={profession}&grade={grade}"


async def compute(
    session: AsyncSession,
    cand: Candidate,
    uplift_items: list[dict[str, Any]],
    ucfg: UpliftConfig,
    today: date | None = None,
) -> dict[str, Any]:
    day = today or datetime.now(UTC).date()
    grades = await assessment.get_grades(session, cand.user_id)
    cur = pick_current(grades, cand.primary_role)
    profession = cur.profession if cur else cand.primary_role
    nxt = next_test_grade(cur.grade.value if cur else None)

    out: dict[str, Any] = {
        "target": {"role": profession, "grade": nxt} if profession and nxt else None,
        "current_grade": (
            {
                "profession": cur.profession,
                "grade": cur.grade.value,
                "valid_until": cur.valid_until,
                "needs_confirmation": cur.needs_confirmation,
            }
            if cur
            else None
        ),  # fmt: skip
        "next_grade": None,
        "test": None,
        "skill_gaps": [],
        "competitions": [],
        "uplift": uplift_items[:UPLIFT_TOP],
    }
    if cand.grade_next:  # v1: баллы и подсказки из graph/grade.py (ml.md §5)
        out["next_grade"] = {
            "points_needed": cand.grade_next.get("points_needed", 0),
            "hints": [
                h if isinstance(h, str) else h.get("text", "")
                for h in cand.grade_next.get("hints", [])
            ],
        }
    if not profession or not nxt:
        return out
    # тест предлагаем только по активной профессии (ADR-027 п.1): скрытой нет в опросе
    info = next((p for p in await taxonomy.list_professions(session) if p.slug == profession), None)
    if info is None:
        return out
    out["test"] = {"profession": profession, "grade": nxt, "path": assessment_path(profession, nxt)}
    if not info.skill_weights:
        return out
    ids = await taxonomy.resolve_slugs(session, list(info.skill_weights))
    owned = await graph.skills_of_candidates(session, [cand.user_id], list(ids.values()))
    conf = {r.skill_id: r.confidence for r in owned}
    held = {slug: conf.get(sid, 0.0) for slug, sid in ids.items()}
    gaps = pick_gaps(info.skill_weights, held, ucfg.target_confidence)
    names = await taxonomy.skill_names(session, [ids[s] for s, _, _ in gaps if s in ids])
    testable = await taxonomy.testable_ids(session, [ids[s] for s, _, _ in gaps if s in ids])
    out["skill_gaps"] = [
        {"skill": s, "name": names.get(ids[s], s), "weight": w, "confidence": c,
         "testable": ids[s] in testable}
        for s, w, c in gaps if s in ids
    ]  # fmt: skip

    gap_slugs = {s for s, _, _ in gaps}
    comps = await graph.upcoming_competitions(session, day, ucfg.competition_days)
    rules = await taxonomy.discipline_rules(session) if comps else {}
    for c in comps:  # skill ← rule ← discipline ← competition
        hit = sorted(
            {
                r.slug for r in rules.get(c.discipline or "", ())
                if r.slug in gap_slugs and r.weight >= ucfg.competition_min_weight
            }
        )  # fmt: skip
        if hit and c.start_date is not None:
            out["competitions"].append(
                {"id": c.id, "title": c.title or c.id, "start_date": c.start_date.isoformat(),
                 "registration_url": c.registration_url, "skills": hit}
            )  # fmt: skip
        if len(out["competitions"]) >= COMPETITIONS_MAX:
            break
    return out


__all__ = ["compute", "next_test_grade", "pick_current", "pick_gaps", "assessment_path"]
