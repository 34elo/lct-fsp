"""Выбор следующего задания (assessment.md §6). Чистые функции, без БД.

1. **Секция.** План — доли типов навыков по грейду × навыки профессии внутри типа (пропорционально
   весам). На шаге `k` берётся секция с наибольшим дефицитом `доля·(k + 1) − выдано_в_секции`.
2. **Кандидаты в секции** фильтрует слой БД (`engine.py`): статус, навык, уровень ±1, 90 дней,
   экспозиция.
3. **Счёт** `P·(1 − P)·(1 − 0.3·ai_solvable)`, `P = σ(θ_target − b)`; из топ-3 — равновероятно.

Пилотные слоты: 2 скрытые позиции после 3-го задания; семейство `pilot` с наименьшим `n`.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from random import Random

from fsp_contracts.assessment import SkillType, TestGrade

from app.assessment.config import AssessmentConfig
from app.assessment.psychometrics import p_correct

# Уровень семейства, ближайший к порогу грейда: b(level) = cut (junior −1 → 2, middle 0 → 3, …)
GRADE_LEVEL = {TestGrade.junior: 2, TestGrade.middle: 3, TestGrade.senior: 4}


@dataclass(frozen=True)
class Section:
    skill: str  # slug навыка
    skill_type: str
    share: float


@dataclass(frozen=True)
class Candidate:
    """Семейство-кандидат на выдачу: то, что нужно для счёта и выбора."""

    id: uuid.UUID
    b: float
    ai_solvable: float = 0.0
    n: int = 0


def type_shares(grade: TestGrade, cfg: AssessmentConfig) -> dict[str, float]:
    return dict(cfg.plan_shares.get(grade.value, {}))


def build_plan(
    skill_weights: Mapping[str, float],
    skill_types: Mapping[str, str],
    grade: TestGrade,
    cfg: AssessmentConfig,
    *,
    available: set[str] | None = None,
) -> list[Section]:
    """План теста: доли секций (навыков), сумма 1.

    Доля навыка = доля его типа по грейду × вес навыка / сумма весов навыков этого типа.
    `available` — навыки, по которым есть задания; остальные выпадают, доли типов без навыков
    перераспределяются пропорционально. Порядок — по убыванию доли, затем по slug.
    """
    shares = type_shares(grade, cfg)
    by_type: dict[str, dict[str, float]] = {}
    for skill, w in skill_weights.items():
        t = skill_types.get(skill)
        if t is None or w <= 0 or (available is not None and skill not in available):
            continue
        by_type.setdefault(SkillType(t).value, {})[skill] = float(w)
    total_type = sum(shares.get(t, 0.0) for t in by_type)
    if total_type <= 0:
        return []
    out = []
    for t, skills in by_type.items():
        ts = shares.get(t, 0.0) / total_type
        sw = sum(skills.values())
        out.extend(Section(s, t, ts * w / sw) for s, w in skills.items() if ts > 0)
    out.sort(key=lambda s: (-s.share, s.skill))
    return out


def deficit(section: Section, issued: int, k: int) -> float:
    """Дефицит секции на шаге `k` (0-based): `доля·(k + 1) − выдано`."""
    return section.share * (k + 1) - issued


def sections_by_deficit(
    plan: Sequence[Section], issued: Mapping[str, int], k: int
) -> list[Section]:
    """Секции по убыванию дефицита; при равенстве — порядок плана (большая доля первой)."""
    idx = {s.skill: i for i, s in enumerate(plan)}
    return sorted(plan, key=lambda s: (-deficit(s, issued.get(s.skill, 0), k), idx[s.skill]))


def item_score(theta_target: float, b: float, ai_solvable: float, cfg: AssessmentConfig) -> float:
    """`P·(1 − P)·(1 − ai_penalty·ai_solvable)`, `P = σ(θ_target − b)`."""
    p = p_correct(theta_target, b)
    ai = min(max(ai_solvable, 0.0), 1.0)
    return p * (1.0 - p) * (1.0 - cfg.ai_penalty * ai)


def choose(
    cands: Sequence[Candidate], theta_target: float, rng: Random, cfg: AssessmentConfig
) -> Candidate | None:
    """Равновероятно из топ-K по счёту. Порядок до сортировки не важен (тай-брейк по id)."""
    if not cands:
        return None
    ranked = sorted(
        cands, key=lambda c: (-item_score(theta_target, c.b, c.ai_solvable, cfg), str(c.id))
    )
    return rng.choice(ranked[: max(1, cfg.top_k)])


def pick_pilot(cands: Sequence[Candidate], rng: Random) -> Candidate | None:
    """Пилот: наименьшее `n`, при равенстве — случайно."""
    if not cands:
        return None
    least = min(c.n for c in cands)
    return rng.choice(sorted((c for c in cands if c.n == least), key=lambda c: str(c.id)))


def pilot_positions(rng: Random, cfg: AssessmentConfig) -> list[int]:
    """Номера (`seq`, с 1) скрытых пилотных позиций: случайно после `after`-го задания.

    Последняя позиция — не дальше `min_items + slots − 1`: до неё выдано меньше `min_items`
    оцениваемых, поэтому SPRT не остановит этап раньше пилотов.
    """
    first = cfg.pilot_after + 1
    last = cfg.min_items + cfg.pilot_slots - 1
    pool = list(range(first, last + 1))
    return sorted(rng.sample(pool, min(cfg.pilot_slots, len(pool))))


def level_ok(level: int, grade: TestGrade, cfg: AssessmentConfig) -> bool:
    """Уровень семейства в пределах заявленного (или бонусного) грейда ±level_window."""
    return abs(level - GRADE_LEVEL[grade]) <= cfg.level_window
