"""План теста «из профессии или вакансии» и примеры заданий (assessment.md §6, E22-5).

Демо «вакансия → тест»: те же `build_plan(...)` и доли типов, что у настоящей попытки, но без
кандидата и БД банка. Секции показываются все (по весам вакансии или профессии); флаг `has_tasks`
говорит, есть ли по навыку кодовые семейства, а примеры берутся только из таких секций.
Примеры — без ключа (`Item.public()`), сид фиксирован от состава плана: повторный запрос даёт то же.
"""

from __future__ import annotations

import hashlib
from random import Random

from fsp_contracts.assessment import TestGrade

from app.assessment import families as registry
from app.assessment import selection as sel
from app.assessment.attempts import build_item
from app.assessment.config import AssessmentConfig
from app.assessment.world import DOMAINS

EXAMPLES = 3
# Старая шкала `enums.Grade` (вакансии, резюме) → грейды теста v2
_OLD_TO_TEST = {
    "intern": TestGrade.junior,
    "junior": TestGrade.junior,
    "junior_plus": TestGrade.junior,
    "middle": TestGrade.middle,
    "middle_plus": TestGrade.middle,
    "senior": TestGrade.senior,
    "lead": TestGrade.senior,
}


def to_test_grade(old: str | None, default: TestGrade = TestGrade.middle) -> TestGrade:
    return _OLD_TO_TEST.get(old or "", default)


def vacancy_weights(rows: list[tuple[float, bool, str]]) -> dict[str, float]:
    """`(вес, обязательный, slug)` → веса навыков плана; необязательный навык весит вдвое меньше."""
    out: dict[str, float] = {}
    for weight, required, slug in rows:
        w = max(float(weight), 0.0) * (1.0 if required else 0.5)
        if w > 0:
            out[slug] = out.get(slug, 0.0) + w
    return out


def _families_of(skill: str, grade: TestGrade, cfg: AssessmentConfig):
    fams = [
        f
        for f in registry.REGISTRY.values()
        if f.skill == skill and sel.level_ok(f.level, grade, cfg)
    ]
    target = sel.GRADE_LEVEL[grade]
    return sorted(fams, key=lambda f: (abs(f.level - target), f.slug))


def examples(sections: list[sel.Section], grade: TestGrade, cfg: AssessmentConfig) -> list[dict]:
    """До трёх примеров из секций с наибольшими долями: по одному на навык."""
    key = "|".join(f"{s.skill}:{s.share:.4f}" for s in sections) + f"|{grade.value}"
    seed = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") & (2**63 - 1)
    domain = DOMAINS[seed % len(DOMAINS)]
    out: list[dict] = []
    for sec in sections:
        fams = _families_of(sec.skill, grade, cfg)
        if not fams:
            continue
        fam = fams[0]
        item = build_item(fam, Random(seed ^ len(out)).getrandbits(62), domain)
        out.append(
            {
                "skill": sec.skill,
                "skill_type": sec.skill_type,
                "family": fam.slug,
                "level": fam.level,
                **item.public(),
            }
        )
        if len(out) == EXAMPLES:
            break
    return out


def preview(
    skill_weights: dict[str, float],
    skill_types: dict[str, str],
    grade: TestGrade,
    cfg: AssessmentConfig,
) -> dict:
    sections = sel.build_plan(skill_weights, skill_types, grade, cfg)
    with_tasks = {f.skill for f in registry.REGISTRY.values()}
    by_type: dict[str, float] = {}
    for s in sections:
        by_type[s.skill_type] = round(by_type.get(s.skill_type, 0.0) + s.share, 6)
    return {
        "grade": grade,
        "items_min": cfg.min_items,
        "type_shares": by_type,
        "sections": [
            {
                "skill": s.skill,
                "skill_type": s.skill_type,
                "share": round(s.share, 6),
                "has_tasks": s.skill in with_tasks,
            }
            for s in sections
        ],
        "examples": examples(sections, grade, cfg),
    }
