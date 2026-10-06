"""Параметры теста из `data/scoring.yaml`, раздел `assessment` (assessment.md §5–7)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

import yaml

DEFAULT_SCORING_PATH = Path(__file__).resolve().parents[4] / "data" / "scoring.yaml"


@dataclass(frozen=True)
class AssessmentConfig:
    cuts: dict[str, float]
    b_by_level: dict[int, float]
    min_items: int
    max_items: int
    # EAP (§5): сетка θ и априорное N(prior_mean, prior_sd²)
    grid_min: float = -4.0
    grid_max: float = 4.0
    grid_step: float = 0.1
    prior_mean: float = 0.0
    prior_sd: float = 1.0
    # Калибровка (§7): K = max(k_min, k0/√(1 + n))
    k0: float = 0.5
    k_min: float = 0.05
    # SPRT (§5): θ₀/θ₁ = cut ∓ sprt_delta, ошибки α и β
    sprt_delta: float = 0.7
    sprt_alpha: float = 0.1
    sprt_beta: float = 0.1
    # Бонусный этап (§5)
    bonus_max_main_items: int = 10
    bonus_margin: float = 0.0
    bonus_max_items: int = 10
    bonus_enabled: bool = True
    # Экспресс-режим для жюри (ADR-025 п.7, E32-4a): короче, грубее, без бонуса и пилотов
    express_enabled: bool = True
    express_min_items: int = 6
    express_max_items: int = 8
    express_alpha: float = 0.15
    express_beta: float = 0.15
    # Выбор задания (§6): доли типов навыков по грейду
    plan_shares: dict[str, dict[str, float]] = field(default_factory=dict)
    top_k: int = 3
    ai_penalty: float = 0.3
    level_window: int = 1
    repeat_days: int = 90
    exposure_days: int = 7
    exposure_max: float = 0.3
    exposure_min_tests: int = 20
    # Пилотные слоты (§6)
    pilot_slots: int = 2
    pilot_after: int = 3
    # Грейды (§5) и честность (§8)
    validity_days: int = 365
    change_cooldown_days: int = 90
    retry_days: int = 30
    invite_days: int = 30  # приглашение бонусного этапа на тест следующего грейда (ADR-025 п.2)
    integrity_threshold: float = 0.6
    unconfirmed_cap: float = 0.59
    evidence_max_strength: float = 0.8
    # Жизненный цикл семейства (§7): пороги допуска pilot → active и тревоги → quarantine
    admit_min_n: int = 30
    admit_min_rpb: float = 0.2
    admit_max_abs_b: float = 3.0
    admit_max_seed_spread: float = 0.15
    seed_groups: int = 3
    admit_max_dif: float = 0.1
    dif_min_group: int = 5
    alarm_min_n: int = 50
    alarm_min_rpb: float = 0.05
    leak_window: int = 50
    leak_delta: float = 0.2
    alarm_appeals: int = 3

    def prior_b(self, level: int) -> float:
        return self.b_by_level[level]

    def for_mode(self, mode: str | None) -> AssessmentConfig:
        """Параметры попытки режима `mode`: у `express` — длина и α/β свои, без бонуса и пилотов."""
        if mode != "express":
            return self
        return replace(
            self,
            min_items=self.express_min_items,
            max_items=self.express_max_items,
            sprt_alpha=self.express_alpha,
            sprt_beta=self.express_beta,
            bonus_enabled=False,
            pilot_slots=0,
        )


@lru_cache(maxsize=4)
def load_config(path: str | None = None) -> AssessmentConfig:
    doc = yaml.safe_load(Path(path or DEFAULT_SCORING_PATH).read_text(encoding="utf-8")) or {}
    a = doc["assessment"]
    eap = a.get("eap") or {}
    cal = a.get("calibration") or {}
    sprt = a.get("sprt") or {}
    bonus = a.get("bonus") or {}
    sel = a.get("selection") or {}
    pilot = a.get("pilot") or {}
    rules = a.get("rules") or {}
    integ = a.get("integrity") or {}
    express = a.get("express") or {}
    evid = a.get("evidence") or {}
    life = a.get("lifecycle") or {}
    adm = life.get("admit") or {}
    alarm = life.get("alarm") or {}
    return AssessmentConfig(
        cuts={g: float(v["cut"]) for g, v in a["grades"].items()},
        b_by_level={int(k): float(v) for k, v in a["b_by_level"].items()},
        min_items=int(a["items"]["min"]),
        max_items=int(a["items"]["max"]),
        grid_min=float(eap.get("grid_min", -4.0)),
        grid_max=float(eap.get("grid_max", 4.0)),
        grid_step=float(eap.get("step", 0.1)),
        prior_mean=float(eap.get("prior_mean", 0.0)),
        prior_sd=float(eap.get("prior_sd", 1.0)),
        k0=float(cal.get("k0", 0.5)),
        k_min=float(cal.get("k_min", 0.05)),
        sprt_delta=float(sprt.get("delta", 0.7)),
        sprt_alpha=float(sprt.get("alpha", 0.1)),
        sprt_beta=float(sprt.get("beta", 0.1)),
        bonus_max_main_items=int(bonus.get("max_main_items", 10)),
        bonus_margin=float(bonus.get("margin", 0.0)),
        bonus_max_items=int(bonus.get("max_items", 10)),
        express_enabled=bool(express.get("enabled", True)),
        express_min_items=int(express.get("min_items", 6)),
        express_max_items=int(express.get("max_items", 8)),
        express_alpha=float(express.get("alpha", 0.15)),
        express_beta=float(express.get("beta", 0.15)),
        plan_shares={
            g: {t: float(v) for t, v in shares.items()}
            for g, shares in (a.get("plan_shares") or {}).items()
        },
        top_k=int(sel.get("top_k", 3)),
        ai_penalty=float(sel.get("ai_penalty", 0.3)),
        level_window=int(sel.get("level_window", 1)),
        repeat_days=int(sel.get("repeat_days", 90)),
        exposure_days=int(sel.get("exposure_days", 7)),
        exposure_max=float(sel.get("exposure_max", 0.3)),
        exposure_min_tests=int(sel.get("exposure_min_tests", 20)),
        pilot_slots=int(pilot.get("slots", 2)),
        pilot_after=int(pilot.get("after", 3)),
        validity_days=int(rules.get("validity_days", 365)),
        change_cooldown_days=int(rules.get("change_cooldown_days", 90)),
        retry_days=int(rules.get("retry_days", 30)),
        invite_days=int(rules.get("invite_days", 30)),
        integrity_threshold=float(integ.get("threshold", 0.6)),
        unconfirmed_cap=float(integ.get("unconfirmed_cap", 0.59)),
        evidence_max_strength=float(evid.get("max_strength", 0.8)),
        admit_min_n=int(adm.get("min_n", 30)),
        admit_min_rpb=float(adm.get("min_rpb", 0.2)),
        admit_max_abs_b=float(adm.get("max_abs_b", 3.0)),
        admit_max_seed_spread=float(adm.get("max_seed_spread", 0.15)),
        seed_groups=int(adm.get("seed_groups", 3)),
        admit_max_dif=float(adm.get("max_dif", 0.1)),
        dif_min_group=int(adm.get("dif_min_group", 5)),
        alarm_min_n=int(alarm.get("min_n", 50)),
        alarm_min_rpb=float(alarm.get("min_rpb", 0.05)),
        leak_window=int(alarm.get("leak_window", 50)),
        leak_delta=float(alarm.get("leak_delta", 0.2)),
        alarm_appeals=int(alarm.get("appeals", 3)),
    )
