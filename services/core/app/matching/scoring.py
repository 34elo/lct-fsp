"""Подбор вакансия ↔ кандидат: жёсткие фильтры, скоринг и объяснения шаблонами (ml.md §6), без БД.

Формулы детерминированные, веса — из `data/scoring.yaml` (`matching_weights`, `hard_filters`,
`grade_fit_scoring`, `skills_coverage`, `team_signal_*`). Командные сигналы — через `k_soft`
(skills.md §8.3): только повышают скор. Каждый пункт объяснения об опыте кандидата (навык, ФСП,
грейд, командный сигнал) несёт `evidence_ids`; пункт без доказательства не показывается.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from fsp_contracts.ml import ExplanationItem

from app.graph.team_signals import KINDS, TeamConfig, k_soft, strength_label

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SCORING_PATH = ROOT / "data" / "scoring.yaml"

GRADES = ("intern", "junior", "junior_plus", "middle", "middle_plus", "senior", "lead")
GRADE_LABELS = {
    "intern": "Intern", "junior": "Junior", "junior_plus": "Junior+", "middle": "Middle",
    "middle_plus": "Middle+", "senior": "Senior", "lead": "Lead",
}  # fmt: skip
SOURCE_WORDS = {
    "github": "кодом", "test": "тестом", "fsp": "на соревнованиях ФСП",
    "ai_interview": "интервью", "codeforces": "Codeforces", "resume": "резюме",
    "self": "самооценкой",
}  # fmt: skip
TEAM_LABELS = {
    "leadership": "Лидерство", "teamwork": "Командная работа",
    "results": "Результативность", "growth": "Рост",
}  # fmt: skip
STRENGTH_WORDS = {"strong": "сильное подтверждение", "present": "есть подтверждение"}
# Пункты об опыте кандидата: без доказательства не показываем (критерий E7-1).
EVIDENCE_REQUIRED = frozenset(
    {"skill_confirmed", "skill_adjacent", "skill_claimed_only", "fsp_achievement",
     "grade_fit", "grade_mismatch", "team_signal"}
)  # fmt: skip
_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class MatchConfig:
    w_skills: float = 0.45
    w_semantic: float = 0.20
    w_grade: float = 0.15
    w_salary: float = 0.10
    w_fsp: float = 0.10
    grade_within: float = 1.0
    grade_adjacent: float = 0.5
    grade_further: float = 0.0
    salary_grace: float = 1.10
    grade_margin: int = 1
    max_failed_required: int = 2  # столько и больше невыполненных обязательных — отсев
    required_mult: float = 2.0
    desired_mult: float = 1.0
    level_min: tuple[float, ...] = (0.0, 0.20, 0.40, 0.60, 0.80)  # target(min_level)
    semantic_floor: float = 0.30
    semantic_span: float = 0.55
    active_bonus: float = 1.03
    top_explanations: int = 3
    candidate_limit: int = 300
    semantic_limit: int = 100
    team: TeamConfig = field(default_factory=TeamConfig)

    @classmethod
    def load(cls, path: Path | str | None = None) -> MatchConfig:
        data = yaml.safe_load(Path(path or DEFAULT_SCORING_PATH).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MatchConfig:
        w = data.get("matching_weights", {})
        hf = data.get("hard_filters", {})
        gf = data.get("grade_fit_scoring", {})
        sc = data.get("skills_coverage", {})
        lim = data.get("limits", {})
        levels = data.get("trust_levels")
        base = cls()
        return cls(
            w_skills=float(w.get("skills_coverage", base.w_skills)),
            w_semantic=float(w.get("semantic_similarity", base.w_semantic)),
            w_grade=float(w.get("grade_fit", base.w_grade)),
            w_salary=float(w.get("salary_fit", base.w_salary)),
            w_fsp=float(w.get("fsp_strength", base.w_fsp)),
            grade_within=float(gf.get("within_range", base.grade_within)),
            grade_adjacent=float(gf.get("one_step_adjacent", base.grade_adjacent)),
            grade_further=float(gf.get("further", base.grade_further)),
            salary_grace=float(hf.get("salary_grace", base.salary_grace)),
            grade_margin=int(hf.get("grade_margin", base.grade_margin)),
            max_failed_required=int(hf.get("max_failed_required_skills", base.max_failed_required)),
            required_mult=float(sc.get("required_weight_multiplier", base.required_mult)),
            desired_mult=float(sc.get("desired_weight_multiplier", base.desired_mult)),
            level_min=(
                tuple(float(levels[i]["min"]) for i in range(5)) if levels else base.level_min
            ),
            top_explanations=int(lim.get("top_explanations", base.top_explanations)),
            candidate_limit=int(lim.get("matching_candidate_limit_sql", base.candidate_limit)),
            team=TeamConfig.from_dict(data),
        )

    def target(self, min_level: int) -> float:
        return self.level_min[max(0, min(min_level, len(self.level_min) - 1))]


# --- входы -------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Requirement:
    skill_id: uuid.UUID
    slug: str
    name: str
    required: bool
    min_level: int = 2
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class VacancyView:
    id: uuid.UUID
    version: int
    company_id: uuid.UUID
    grade_min: str
    grade_max: str
    formats: tuple[str, ...]
    salary_from: int
    salary_to: int
    skills: tuple[Requirement, ...]
    important_qualities: tuple[str, ...] = ()
    embedding: Sequence[float] | None = None


@dataclass(frozen=True, slots=True)
class HeldSkill:
    """Ребро «владеет» (`candidate_skills`)."""

    name: str
    confidence: float
    level: int
    sources: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    claimed_only: bool = False


@dataclass(frozen=True, slots=True)
class FspProof:
    """Лучшее ФСП-доказательство по навыку: сила уже с затуханием."""

    evidence_id: str
    strength: float
    label: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateView:
    id: uuid.UUID
    profile_version: int
    grade: str | None
    formats: tuple[str, ...]
    salary_min: int | None
    status: str  # эффективный: active | open | dnd
    stoplist: frozenset[str] = frozenset()
    deleted: bool = False
    skills: Mapping[uuid.UUID, HeldSkill] = field(default_factory=dict)
    fsp: Mapping[uuid.UUID, FspProof] = field(default_factory=dict)
    team: Mapping[str, float] = field(default_factory=dict)  # L/T/R/G
    team_evidence: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    grade_evidence: tuple[str, ...] = ()
    embedding: Sequence[float] | None = None


Adjacency = Mapping[uuid.UUID, Sequence[tuple[uuid.UUID, float]]]


# --- покрытие навыков ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Cover:
    req: Requirement
    own: HeldSkill | None
    own_conf: float
    adj_id: uuid.UUID | None
    adj_conf: float  # conf(a) · adj(s, a)
    target: float

    @property
    def eff(self) -> float:
        return max(self.own_conf, self.adj_conf)

    @property
    def part(self) -> float:
        return 1.0 if self.target <= 0 else min(1.0, self.eff / self.target)

    @property
    def met(self) -> bool:
        return self.eff + _EPS >= self.target

    @property
    def via_adjacent(self) -> bool:
        return self.met and self.own_conf + _EPS < self.target


def cover(req: Requirement, cand: CandidateView, adjacency: Adjacency, cfg: MatchConfig) -> Cover:
    """`eff_conf_s = max(conf_s, max_a conf_a · adj(s,a))`."""
    own = cand.skills.get(req.skill_id)
    best_id, best = None, 0.0
    for a, w in adjacency.get(req.skill_id, ()):
        h = cand.skills.get(a)
        if h is not None and h.confidence * w > best + _EPS:
            best_id, best = a, h.confidence * w
    return Cover(req, own, own.confidence if own else 0.0, best_id, best, cfg.target(req.min_level))


def skills_component(covers: Sequence[Cover], cfg: MatchConfig) -> float:
    """`Σ_s W_s · min(1, eff_conf_s / target(min_level_s)) / Σ W_s`."""
    ws = [_w(c.req, cfg) for c in covers]
    total = sum(ws)
    return sum(w * c.part for w, c in zip(ws, covers, strict=True)) / total if total else 0.0


def _w(req: Requirement, cfg: MatchConfig) -> float:
    return (cfg.required_mult if req.required else cfg.desired_mult) * req.weight


# --- компоненты ----------------------------------------------------------------------------


def grade_distance(grade: str | None, lo: str, hi: str) -> int | None:
    if grade not in GRADES:
        return None
    g, a, b = GRADES.index(grade), GRADES.index(lo), GRADES.index(hi)
    return 0 if a <= g <= b else min(abs(g - a), abs(g - b))


def grade_component(grade: str | None, lo: str, hi: str, cfg: MatchConfig) -> float:
    d = grade_distance(grade, lo, hi)
    if d is None:
        return 0.0
    if d == 0:
        return cfg.grade_within
    return cfg.grade_adjacent if d == 1 else cfg.grade_further


def salary_component(salary_min: int | None, salary_from: int, salary_to: int) -> float:
    """1 — до середины вилки; линейно до 0 при `salary_min = salary_to`; выше — 0."""
    if salary_min is None:
        return 1.0
    mid = (salary_from + salary_to) / 2
    if salary_min <= mid:
        return 1.0
    if salary_min >= salary_to:
        return 0.0
    return (salary_to - salary_min) / (salary_to - mid)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def semantic_component(
    vac: Sequence[float] | None, cand: Sequence[float] | None, cfg: MatchConfig
) -> float:
    """`clip((cos − 0.30) / 0.55, 0, 1)`; нет вектора — 0."""
    if not vac or not cand:
        return 0.0
    return min(1.0, max(0.0, (cosine(vac, cand) - cfg.semantic_floor) / cfg.semantic_span))


def fsp_component(
    v: VacancyView, cand: CandidateView
) -> tuple[float, Requirement | None, FspProof | None]:
    """Максимум силы ФСП-доказательств по навыкам вакансии."""
    best: tuple[float, Requirement | None, FspProof | None] = (0.0, None, None)
    for r in v.skills:
        p = cand.fsp.get(r.skill_id)
        if p is not None and p.strength > best[0]:
            best = (p.strength, r, p)
    return best


# --- жёсткие фильтры -----------------------------------------------------------------------


def hard_filter(
    v: VacancyView,
    cand: CandidateView,
    covers: Sequence[Cover],
    cfg: MatchConfig,
    *,
    semantic_only: bool = False,
) -> str | None:
    """Причина отсева или None (ml.md §6.1). Отбор по смыслу не проверяет навыки."""
    if cand.deleted:
        return "deleted"
    if cand.status == "dnd":
        return "dnd"
    if str(v.company_id) in cand.stoplist:
        return "stoplist"
    if not set(cand.formats) & set(v.formats):
        return "formats"
    if cand.salary_min is not None and cand.salary_min > v.salary_to * cfg.salary_grace + _EPS:
        return "salary"
    d = grade_distance(cand.grade, v.grade_min, v.grade_max)
    if d is not None and d > cfg.grade_margin:
        return "grade"
    failed = sum(1 for c in covers if c.req.required and not c.met)
    if not semantic_only and failed >= cfg.max_failed_required:
        return "skills"
    return None


# --- результат -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MatchResult:
    candidate_id: uuid.UUID
    profile_version: int
    score: float
    breakdown: dict[str, Any]
    explanation: list[ExplanationItem]
    semantic_only: bool = False


def score_candidate(
    v: VacancyView,
    cand: CandidateView,
    adjacency: Adjacency,
    cfg: MatchConfig,
    *,
    semantic_only: bool = False,
) -> MatchResult | None:
    """None — кандидат не прошёл жёсткие фильтры.

    `base = 0.45·skills + 0.20·semantic + 0.15·grade + 0.10·salary + 0.10·fsp`,
    `score = min(1, base · K_soft · 1.03 [«активно ищу»])`.
    """
    covers = [cover(r, cand, adjacency, cfg) for r in v.skills]
    if hard_filter(v, cand, covers, cfg, semantic_only=semantic_only) is not None:
        return None
    comp = {
        "skills": skills_component(covers, cfg),
        "semantic": semantic_component(v.embedding, cand.embedding, cfg),
        "grade": grade_component(cand.grade, v.grade_min, v.grade_max, cfg),
        "salary": salary_component(cand.salary_min, v.salary_from, v.salary_to),
    }
    comp["fsp"], fsp_req, fsp_proof = fsp_component(v, cand)
    weights = {
        "skills": cfg.w_skills, "semantic": cfg.w_semantic, "grade": cfg.w_grade,
        "salary": cfg.w_salary, "fsp": cfg.w_fsp,
    }  # fmt: skip
    base = sum(weights[k] * comp[k] for k in weights)
    ks = k_soft(cand.team, v.grade_max, cfg.team, v.important_qualities)
    active = cand.status == "active"
    score = min(1.0, base * ks * (cfg.active_bonus if active else 1.0))
    items = _explain(v, cand, covers, comp, weights, base, ks, score, fsp_req, fsp_proof, cfg)
    if semantic_only:
        text = "Совпадение только по смыслу описания: нужные навыки не найдены в справочнике"
        items.append(_item("warn", "semantic_only", text, -cfg.w_skills * (1 - comp["skills"])))
    breakdown = {
        **{k: round(x, 4) for k, x in comp.items()},
        "base": round(base, 4),
        "k_soft": round(ks, 4),
        "active": active,
        "semantic_only": semantic_only,
        "salary_over": cand.salary_min is not None and cand.salary_min > v.salary_to,
        "skills_detail": [
            {
                "skill": c.req.slug,
                "required": c.req.required,
                "eff": round(c.eff, 4),
                "target": c.target,
                "met": c.met,
                "via": "adjacent" if c.via_adjacent else ("own" if c.met else None),
            }
            for c in covers
        ],
    }
    return MatchResult(
        cand.id,
        cand.profile_version,
        round(score, 4),
        breakdown,
        select_explanation(items, cfg.top_explanations),
        semantic_only,
    )


# --- объяснения ----------------------------------------------------------------------------


def dots(level: int) -> str:
    level = max(0, min(4, level))
    return "●" * level + "○" * (4 - level)


def _item(
    kind: str,
    code: str,
    text: str,
    weight: float,
    skill: str | None = None,
    evidence: Sequence[str] = (),
) -> ExplanationItem:
    return ExplanationItem(
        kind=kind, code=code, text=text, skill=skill, evidence_ids=list(dict.fromkeys(evidence)),
        weight=round(weight, 4),
    )  # fmt: skip


def _sources_text(h: HeldSkill) -> str:
    words = [
        SOURCE_WORDS[s] for s in h.sources if s in SOURCE_WORDS and s not in ("resume", "self")
    ]
    return " и ".join(words) if words else "доказательствами"


def _rub(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " ₽"


def _explain(
    v: VacancyView,
    cand: CandidateView,
    covers: Sequence[Cover],
    comp: Mapping[str, float],
    weights: Mapping[str, float],
    base: float,
    ks: float,
    score: float,
    fsp_req: Requirement | None,
    fsp_proof: FspProof | None,
    cfg: MatchConfig,
) -> list[ExplanationItem]:
    items: list[ExplanationItem] = []
    total_w = sum(_w(c.req, cfg) for c in covers) or 1.0
    for c in covers:
        share = cfg.w_skills * _w(c.req, cfg) / total_w
        gain = share * c.part if c.met else -share * (1.0 - c.part)
        name, slug = c.req.name, c.req.slug
        adj = cand.skills.get(c.adj_id) if c.adj_id else None
        if c.via_adjacent and adj is not None:
            text = f"Нет подтверждения {name} (есть смежное: {adj.name} {dots(adj.level)})"
            items.append(_item("warn", "skill_adjacent", text, gain, slug, adj.evidence_ids))
        elif c.own is not None and c.own.claimed_only and c.own_conf >= c.adj_conf:
            text = f"{name} — только заявлено ({dots(c.own.level)}), подтверждения нет"
            items.append(_item("warn", "skill_claimed_only", text, gain, slug, c.own.evidence_ids))
        elif c.met and c.own is not None:
            text = f"{name} — подтверждено {_sources_text(c.own)} ({dots(c.own.level)})"
            items.append(_item("plus", "skill_confirmed", text, gain, slug, c.own.evidence_ids))
        else:
            text, ev = f"Нет подтверждения {name}", ()
            if adj is not None:
                text, ev = text + f" (есть смежное: {adj.name} {dots(adj.level)})", adj.evidence_ids
            elif c.own is not None:
                text, ev = text + f" (сейчас {dots(c.own.level)})", c.own.evidence_ids
            items.append(_item("minus", "skill_missing", text, gain, slug, ev))

    if fsp_proof is not None and fsp_req is not None:
        what = fsp_proof.label or "соревнования ФСП"
        items.append(
            _item(
                "plus",
                "fsp_achievement",
                f"{fsp_req.name} — ФСП: {what}",
                weights["fsp"] * comp["fsp"],
                fsp_req.slug,
                [fsp_proof.evidence_id],
            )
        )

    if cand.grade in GRADES:
        g = GRADE_LABELS[cand.grade]
        rng = GRADE_LABELS[v.grade_min] + (
            "" if v.grade_min == v.grade_max else f"–{GRADE_LABELS[v.grade_max]}"
        )
        if comp["grade"] >= cfg.grade_within - _EPS:
            items.append(
                _item(
                    "plus",
                    "grade_fit",
                    f"Грейд {g} — в диапазоне вакансии ({rng})",
                    weights["grade"] * comp["grade"],
                    evidence=cand.grade_evidence,
                )
            )
        else:
            lower = GRADES.index(cand.grade) < GRADES.index(v.grade_min)
            side = "ниже" if lower else "выше"
            items.append(
                _item(
                    "warn",
                    "grade_mismatch",
                    f"Грейд {g} — на ступень {side} диапазона вакансии ({rng})",
                    -weights["grade"] * (1 - comp["grade"]),
                    evidence=cand.grade_evidence,
                )
            )

    if cand.salary_min is not None:
        if cand.salary_min > v.salary_to:
            over = round((cand.salary_min / v.salary_to - 1) * 100)
            items.append(
                _item(
                    "warn",
                    "salary_below_min",
                    f"Ожидания {_rub(cand.salary_min)} выше вилки на {over}%",
                    -weights["salary"],
                )
            )
        elif comp["salary"] >= 1.0 - _EPS:
            items.append(
                _item(
                    "plus",
                    "salary_fit",
                    f"Ожидания {_rub(cand.salary_min)} — в пределах вилки",
                    weights["salary"] * comp["salary"],
                )
            )
        else:
            items.append(
                _item(
                    "warn",
                    "salary_fit",
                    f"Ожидания {_rub(cand.salary_min)} — у верхней границы вилки",
                    -weights["salary"] * (1 - comp["salary"]),
                )
            )

    if cand.status == "active":
        items.append(
            _item("plus", "active_search", "Активно ищет работу", score - score / cfg.active_bonus)
        )

    items.extend(_team_items(v, cand, base, ks, cfg))
    return items


def _team_items(
    v: VacancyView, cand: CandidateView, base: float, ks: float, cfg: MatchConfig
) -> list[ExplanationItem]:
    """Вклад сигнала `k` — его доля в `K_soft − 1`, умноженная на `base`."""
    if ks <= 1.0:
        return []
    terms = {
        k: k_soft({k: s}, v.grade_max, cfg.team, v.important_qualities) - 1.0
        for k, s in cand.team.items()
        if k in KINDS and s > 0
    }
    total = sum(terms.values())
    out = []
    for k, t in terms.items():
        label = strength_label(cand.team[k])
        if label is None or total <= 0:
            continue
        contrib = base * (ks - 1.0) * t / total
        pct = max(1, round(contrib * 100))
        text = f"{TEAM_LABELS[k]} — {STRENGTH_WORDS[label]} (+{pct}%)"
        out.append(
            _item("plus", "team_signal", text, contrib, evidence=cand.team_evidence.get(k, ()))
        )
    return out


def select_explanation(items: Sequence[ExplanationItem], top: int) -> list[ExplanationItem]:
    """Топ-N плюсов и топ-N минусов/предупреждений по модулю вклада."""
    shown = [i for i in items if i.code not in EVIDENCE_REQUIRED or i.evidence_ids]
    plus = sorted((i for i in shown if i.kind == "plus"), key=lambda i: -abs(i.weight))
    rest = sorted((i for i in shown if i.kind != "plus"), key=lambda i: -abs(i.weight))
    return plus[:top] + rest[:top]
