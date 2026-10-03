"""Uplift кандидата: какой навык подтвердить, чтобы подойти под больше вакансий (matching.md §6).

Чистая часть (без БД): релевантные вакансии, симуляция «навык поднят до 0.65», жадная
комбинация до 3 навыков, медиана вилок. Параметры — `data/scoring.yaml` (`limits.uplift_*`).
Прирост детерминирован: число подходящих вакансий считает тот же `score_candidate`, что и подбор.
"""

from __future__ import annotations

import statistics
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from app.graph.trust import SkillTrust, TrustConfig, inherit, level_for
from app.matching.scoring import (
    DEFAULT_SCORING_PATH,
    Adjacency,
    CandidateView,
    HeldSkill,
    MatchConfig,
    VacancyView,
    cover,
    grade_distance,
    score_candidate,
)

ParentsOf = Callable[[uuid.UUID], Iterable[tuple[uuid.UUID, float]]]


@dataclass(frozen=True, slots=True)
class UpliftConfig:
    score_threshold: float = 0.6
    target_confidence: float = 0.65
    salary_threshold: float = 0.90
    grade_margin: int = 1
    top_skills: int = 30
    combo_max: int = 3
    items_max: int = 10
    test_minutes: int = 10
    competition_days: int = 120
    competition_min_weight: float = 0.5

    @classmethod
    def load(cls, path: Path | str | None = None) -> UpliftConfig:
        data = yaml.safe_load(Path(path or DEFAULT_SCORING_PATH).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> UpliftConfig:
        lim = data.get("limits", {})
        rel = lim.get("uplift_relevant_vacancies", {})
        b = cls()
        return cls(
            score_threshold=float(lim.get("uplift_score_threshold", b.score_threshold)),
            target_confidence=float(lim.get("uplift_target_confidence", b.target_confidence)),
            salary_threshold=float(rel.get("salary_threshold", b.salary_threshold)),
            grade_margin=int(rel.get("grade_margin", b.grade_margin)),
            top_skills=int(lim.get("uplift_top_skills", b.top_skills)),
            combo_max=int(lim.get("uplift_combinations_max", b.combo_max)),
            items_max=int(lim.get("uplift_items_max", b.items_max)),
            test_minutes=int(lim.get("uplift_test_minutes", b.test_minutes)),
            competition_days=int(lim.get("uplift_competition_days", b.competition_days)),
            competition_min_weight=float(
                lim.get("uplift_competition_min_weight", b.competition_min_weight)
            ),
        )


@dataclass(frozen=True, slots=True)
class SkillGain:
    skill_id: uuid.UUID
    extra: int
    pct: float
    median_salary_delta: int


@dataclass(frozen=True, slots=True)
class UpliftResult:
    relevant_total: int
    base: int
    items: list[SkillGain]
    combo_ids: list[uuid.UUID]
    combo_extra: int
    combo_pct: float


def top_roles(roles: Sequence[Mapping[str, Any]] | None, primary: str | None) -> set[str]:
    """Две главные роли кандидата по весу; нет меток — основная роль."""
    ranked = sorted(roles or (), key=lambda r: -float(r.get("weight", 0)))
    out = {str(r["role"]) for r in ranked[:2] if r.get("role")}
    return out or ({primary} if primary else set())


def is_relevant(
    v: VacancyView,
    role: str,
    cand_roles: set[str],
    cand: CandidateView,
    cfg: UpliftConfig,
) -> bool:
    """Шаг 1 алгоритма: формат, вилка, роль в топ-2, грейд в пределах ±margin."""
    if cand_roles and role not in cand_roles:
        return False
    if not set(cand.formats) & set(v.formats):
        return False
    if cand.salary_min is not None and v.salary_to < cfg.salary_threshold * cand.salary_min:
        return False
    d = grade_distance(cand.grade, v.grade_min, v.grade_max)
    return d is None or d <= cfg.grade_margin


def raise_skills(
    cand: CandidateView,
    skill_id: uuid.UUID,
    names: Mapping[uuid.UUID, str],
    parents_of: ParentsOf,
    trust: TrustConfig,
    target: float,
) -> tuple[CandidateView, set[uuid.UUID]]:
    """Копия профиля с `conf(s) = max(conf(s), target)` и наследованием вверх по иерархии."""
    level = level_for(target, trust)
    raised = {skill_id: target}
    direct = {skill_id: SkillTrust(target, level, ["simulated"], [], False)}
    for parent, (t, _) in inherit(direct, parents_of, trust).items():
        raised[parent] = t.confidence
    skills = dict(cand.skills)
    changed: set[uuid.UUID] = set()
    for sid, conf in raised.items():
        cur = skills.get(sid)
        if cur is not None and cur.confidence >= conf:
            continue
        skills[sid] = HeldSkill(
            name=cur.name if cur else names.get(sid, str(sid)),
            confidence=conf,
            level=level_for(conf, trust),
            sources=cur.sources if cur else ("simulated",),
            evidence_ids=cur.evidence_ids if cur else (),
            claimed_only=False,
        )
        changed.add(sid)
    return replace(cand, skills=skills), changed


def _affected(v: VacancyView, changed: set[uuid.UUID], adj: Adjacency) -> bool:
    """Меняет ли поднятие этих навыков покрытие требований вакансии (само или через смежные)."""
    for r in v.skills:
        if r.skill_id in changed or any(a in changed for a, _ in adj.get(r.skill_id, ())):
            return True
    return False


def _median(vals: list[int]) -> int:
    return int(statistics.median(vals)) if vals else 0


def simulate(
    vacancies: Sequence[VacancyView],
    cand: CandidateView,
    adj: Adjacency,
    names: Mapping[uuid.UUID, str],
    parents_of: ParentsOf,
    match_cfg: MatchConfig,
    trust: TrustConfig,
    cfg: UpliftConfig,
) -> UpliftResult:
    """Шаги 2–6 алгоритма matching.md §6 по уже отобранным релевантным вакансиям."""

    def fits(v: VacancyView, c: CandidateView) -> bool:
        r = score_candidate(v, c, adj, match_cfg)
        return r is not None and r.score >= cfg.score_threshold

    base_fit = {v.id: fits(v, cand) for v in vacancies}
    base = sum(base_fit.values())
    salary = {v.id: v.salary_to for v in vacancies}

    # кандидатные навыки: уровень ниже требуемого хотя бы в одной вакансии; топ-N по спросу
    demand: dict[uuid.UUID, int] = {}
    for v in vacancies:
        for r in v.skills:
            if not cover(r, cand, adj, match_cfg).met:
                demand[r.skill_id] = demand.get(r.skill_id, 0) + 1
    ranked = sorted(demand, key=lambda s: (-demand[s], names.get(s, ""), str(s)))
    candidates = ranked[: cfg.top_skills]

    def trial(
        state: CandidateView, fit: Mapping[uuid.UUID, bool], sid: uuid.UUID
    ) -> tuple[CandidateView, dict[uuid.UUID, bool]]:
        new, changed = raise_skills(state, sid, names, parents_of, trust, cfg.target_confidence)
        out = dict(fit)
        if changed:
            for v in vacancies:
                if _affected(v, changed, adj):
                    out[v.id] = fits(v, new)
        return new, out

    def stats(fit: Mapping[uuid.UUID, bool]) -> tuple[int, int]:
        extra = sum(fit.values()) - base
        delta = _median([salary[i] for i, ok in fit.items() if ok]) - _median(
            [salary[i] for i, ok in base_fit.items() if ok]
        )
        return extra, delta if base and sum(fit.values()) else 0

    items: list[SkillGain] = []
    for sid in candidates:
        _, fit = trial(cand, base_fit, sid)
        extra, delta = stats(fit)
        if extra > 0:
            items.append(SkillGain(sid, extra, round(extra / max(base, 1), 4), delta))
    items.sort(key=lambda g: (-g.extra, names.get(g.skill_id, ""), str(g.skill_id)))

    # комбинация: жадно до N навыков, каждый раз лучший прирост
    state, fit, chosen = cand, dict(base_fit), []
    pool = candidates
    for _ in range(cfg.combo_max):
        best: tuple[int, uuid.UUID, CandidateView, dict[uuid.UUID, bool]] | None = None
        for sid in pool:
            if sid in chosen:
                continue
            new, nfit = trial(state, fit, sid)
            gain = sum(nfit.values()) - sum(fit.values())
            if gain > 0 and (best is None or gain > best[0]):
                best = (gain, sid, new, nfit)
        if best is None:
            break
        _, sid, state, fit = best
        chosen.append(sid)
    combo_extra = sum(fit.values()) - base if chosen else 0
    return UpliftResult(
        relevant_total=len(vacancies),
        base=base,
        items=items[: cfg.items_max],
        combo_ids=chosen,
        combo_extra=combo_extra,
        combo_pct=round(combo_extra / max(base, 1), 4),
    )
