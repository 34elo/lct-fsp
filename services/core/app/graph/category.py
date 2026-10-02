"""Категория кандидата: роли, мульти-метки, `primary_stack`, объяснение (ml.md §4).

Чистые формулы без БД: вход — доверие к навыкам (slug → confidence/level/sources) и веса ролей
`role_skills`; параметры — секция `category` из `data/scoring.yaml`.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.models import CandidateSkill
from app.taxonomy.service import SkillGraph

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SCORING_PATH = ROOT / "data" / "scoring.yaml"
FULLSTACK = "fullstack"
FRONTEND = "frontend"
BACKEND = "backend"


@dataclass(frozen=True, slots=True)
class CategoryConfig:
    top_k: int = 8
    label_ratio: float = 0.6
    min_score: float = 0.05
    fullstack_min: float = 0.5
    fullstack_gap: float = 0.15
    stack_size: int = 3
    explain_top: int = 5

    @classmethod
    def load(cls, path: Path | str | None = None) -> CategoryConfig:
        data = yaml.safe_load(Path(path or DEFAULT_SCORING_PATH).read_text(encoding="utf-8"))
        return cls.from_dict(data.get("category"))

    @classmethod
    def from_dict(cls, raw: Mapping[str, float] | None) -> CategoryConfig:
        base = cls()
        return cls(
            **{k: type(getattr(base, k))(v) for k, v in (raw or {}).items() if hasattr(base, k)}
        )


@dataclass(frozen=True, slots=True)
class SkillConf:
    confidence: float
    level: int
    sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RoleLabel:
    role: str
    weight: float  # доля метки среди выбранных, сумма = 1


@dataclass(frozen=True, slots=True)
class ExplainSkill:
    slug: str
    weight: float  # вес навыка в роли
    confidence: float
    level: int
    sources: tuple[str, ...]
    contribution: float  # w · conf


@dataclass(frozen=True, slots=True)
class Category:
    primary_role: str | None
    roles: list[RoleLabel] = field(default_factory=list)
    primary_stack: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    explanation: list[ExplainSkill] = field(default_factory=list)

    def roles_json(self) -> list[dict]:
        return [{"role": r.role, "weight": r.weight} for r in self.roles]


def role_score(
    weights: Mapping[str, float], skills: Mapping[str, SkillConf], top_k: int = 8
) -> float:
    """`Σ w·conf / Σ_{top-k} w`: нормируем на k самых весомых навыков роли."""
    top = sorted(weights.values(), reverse=True)[:top_k]
    denom = sum(top)
    if denom <= 0:
        return 0.0
    num = sum(w * skills[s].confidence for s, w in weights.items() if s in skills)
    return min(1.0, num / denom)


def compute_category(
    skills: Mapping[str, SkillConf],
    roles: Mapping[str, Mapping[str, float]],
    stack_slugs: Collection[str],
    cfg: CategoryConfig,
) -> Category:
    # fullstack не считается по своим весам: это метка backend + frontend по правилу ниже
    scores = {
        r: round(role_score(w, skills, cfg.top_k), 4) for r, w in roles.items() if r != FULLSTACK
    }
    if (b := scores.get(BACKEND)) is not None and (f := scores.get(FRONTEND)) is not None:
        if (
            b >= cfg.fullstack_min
            and f >= cfg.fullstack_min
            and abs(b - f) < cfg.fullstack_gap
            and FULLSTACK in roles
        ):
            scores[FULLSTACK] = round((b + f) / 2, 4)
            fullstack_forced = True
        else:
            fullstack_forced = False
    else:
        fullstack_forced = False
    best = max(scores.values(), default=0.0)
    if best < cfg.min_score:
        return Category(None, scores=scores)

    chosen = {r for r, s in scores.items() if s >= cfg.label_ratio * best}
    if fullstack_forced:
        chosen.add(FULLSTACK)
        primary = FULLSTACK
    else:
        primary = min((r for r in chosen), key=lambda r: (-scores[r], r))
    total = sum(scores[r] for r in chosen)
    labels = [
        RoleLabel(r, round(scores[r] / total, 3))
        for r in sorted(chosen, key=lambda r: (-scores[r], r))
    ]
    pw = roles[primary]
    ranked = sorted(
        (s for s in pw if s in skills and skills[s].confidence > 0),
        key=lambda s: (-pw[s] * skills[s].confidence, s),
    )
    stack_set = set(stack_slugs)
    stack = [s for s in ranked if s in stack_set]
    stack.sort(key=lambda s: (-skills[s].confidence, -pw[s], s))
    explanation = [
        ExplainSkill(
            s,
            pw[s],
            skills[s].confidence,
            skills[s].level,
            skills[s].sources,
            round(pw[s] * skills[s].confidence, 4),
        )
        for s in ranked[: cfg.explain_top]
    ]
    return Category(primary, labels, stack[: cfg.stack_size], scores, explanation)


def category_for(
    skills: Mapping[str, SkillConf], graph: SkillGraph, cfg: CategoryConfig
) -> Category:
    """Категория по графу навыков core (веса ролей и стек берутся из снимка справочника)."""
    roles = {
        r: {graph.slugs[sid]: w for sid, w in ws.items() if sid in graph.slugs}
        for r, ws in graph.roles.items()
    }
    return compute_category(
        skills, roles, {graph.slugs[sid] for sid in graph.stack_ids if sid in graph.slugs}, cfg
    )


async def load_category(
    session: AsyncSession, candidate_id: uuid.UUID, graph: SkillGraph, cfg: CategoryConfig
) -> Category:
    """Категория и объяснение по сохранённым `candidate_skills` (для E4-6)."""
    rows = await session.scalars(
        select(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id)
    )
    skills = {
        graph.slugs[r.skill_id]: SkillConf(r.confidence, r.level, tuple(r.sources))
        for r in rows
        if r.skill_id in graph.slugs
    }
    return category_for(skills, graph, cfg)
