"""Seed-грейды: таблица `grades` для демо-кандидатов без прохождения теста.

Грейды пишет `app.assessment.service.seed_grade` (source="seed", событие
`candidate.category.changed`).
Распределение детерминировано по SEED плана: junior 40 %, middle 40 %, senior 20 %, у 5 %
`needs_confirmation`. Профессии — 6 существующих; каждая из 18 категорий (6 × 3) непуста.
Герои получают грейды по своей истории: Аня — backend/junior, Дима — backend/middle
(Ольга — работодатель, грейда у неё нет).
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime
from typing import Any

from app.assessment import service as assessment
from app.consents import service as consents
from fsp_contracts.assessment import TEST_GRADE_ORDER
from fsp_contracts.enums import ConsentType
from fsp_platform.db import session_scope
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

PROFESSIONS = ("backend", "frontend", "mobile", "ml", "devops", "qa")
GRADE_SHARES = (("junior", 0.40), ("middle", 0.40), ("senior", 0.20))
NEEDS_CONFIRMATION_SHARE = 0.05
DUAL_EVERY = 8  # каждый N-й кандидат с двумя направлениями
# Роли синтетики, которых нет среди 6 профессий, → ближайшая профессия.
ROLE_TO_PROFESSION = {
    "fullstack": "backend",
    "data_engineer": "ml",
    "analyst": "ml",
    "embedded": "backend",
    "security": "devops",
    "gamedev": "backend",
    "product": "qa",
    "designer": "frontend",
}
# θ внутри полосы грейда (cut: junior −1.0, middle 0.0, senior 1.0).
_THETA_RANGE = {"junior": (-0.95, -0.05), "middle": (0.05, 0.95), "senior": (1.05, 2.0)}
HERO_GRADES = {
    "anya": ("backend", "junior", -0.45, False),
    "dima": ("backend", "middle", 0.35, False),
}


def profession_of(role: str) -> str:
    return role if role in PROFESSIONS else ROLE_TO_PROFESSION.get(role, "backend")


def plan_grades(plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Чистый план: ключ кандидата → список `{profession, grade, theta, needs_confirmation}`."""
    rng = random.Random(f"grades:{plan['seed']}")
    cands = [c for c in plan["candidates"] if not c["hero"]]
    n = len(cands)

    # Квоты по доле, остаток — в middle; порядок перемешан по seed.
    grades: list[str] = []
    for name, share in GRADE_SHARES[:-1]:
        grades += [name] * round(n * share)
    grades += ["senior"] * (n - len(grades))
    rng.shuffle(grades)
    flags = [i < round(n * NEEDS_CONFIRMATION_SHARE) for i in range(n)]
    rng.shuffle(flags)

    def entry(profession: str, grade: str, flag: bool) -> dict[str, Any]:
        lo, hi = _THETA_RANGE[grade]
        return {
            "profession": profession,
            "grade": grade,
            "theta": round(rng.uniform(lo, hi), 3),
            "needs_confirmation": flag,
        }

    out: dict[str, list[dict[str, Any]]] = {}
    for c, g, f in zip(cands, grades, flags, strict=True):
        out[c["key"]] = [entry(profession_of(c["role"]), g, f)]
    for c in plan["candidates"]:
        if c["hero"] in HERO_GRADES:
            prof, grade, theta, flag = HERO_GRADES[c["hero"]]
            out[c["key"]] = [
                {"profession": prof, "grade": grade, "theta": theta, "needs_confirmation": flag}
            ]

    # Покрытие: каждая из 6 × 3 категорий непуста — недостающие добавляем вторым грейдом
    # кандидатам (по кругу), у которых такой профессии ещё нет.
    present = {(e["profession"], e["grade"]) for es in out.values() for e in es}
    keys = [c["key"] for c in cands]
    j = 0
    for prof in PROFESSIONS:
        for grade in (g.value for g in TEST_GRADE_ORDER):
            if (prof, grade) in present or not keys:
                continue
            for _ in range(len(keys)):
                key = keys[j % len(keys)]
                j += 1
                if all(e["profession"] != prof for e in out[key]):
                    out[key].append(entry(prof, grade, False))
                    break

    # каждый 8-й кандидат прошёл тесты по двум направлениям (одна карточка, две категории).
    for i, key in enumerate(keys):
        if i % DUAL_EVERY or len(out[key]) > 1:
            continue
        taken = {e["profession"] for e in out[key]}
        other = [p for p in PROFESSIONS if p not in taken]
        out[key].append(entry(rng.choice(other), rng.choice([g for g, _ in GRADE_SHARES]), False))
    return out


async def seed_grades(
    factory: async_sessionmaker[AsyncSession],
    plan: dict[str, Any],
    user_ids: dict[str, uuid.UUID],
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Записать грейды через `seed_grade`. Кандидаты, у которых уже есть действующие грейды,
    пропускаются — повторный запуск ничего не меняет и не шлёт событий."""
    now = now or datetime.now(UTC)
    wanted = plan_grades(plan)
    stats = {"grades": 0, "grades_candidates": 0}
    async with session_scope(factory) as s:
        have = await assessment.get_grades_many(s, [user_ids[k] for k in wanted if k in user_ids])
        for key, entries in wanted.items():
            uid = user_ids.get(key)
            if uid is None:
                continue
            # демо-кандидаты согласны на публикацию: без `profile_publication` их не видно в выдаче
            await consents.set_consents(s, uid, [(ConsentType.profile_publication, True, None)])
            if uid in have:
                continue
            for e in entries:
                await assessment.seed_grade(
                    s,
                    uid,
                    e["profession"],
                    e["grade"],
                    e["theta"],
                    needs_confirmation=e["needs_confirmation"],
                    integrity=0.5 if e["needs_confirmation"] else 1.0,
                    now=now,
                )
                stats["grades"] += 1
            stats["grades_candidates"] += 1
    return stats


__all__ = ["PROFESSIONS", "plan_grades", "profession_of", "seed_grades"]
