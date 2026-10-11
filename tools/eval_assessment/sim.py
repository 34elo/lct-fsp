"""Валидация теста на синтетике.

Симулятор повторяет поток попытки из `app/assessment/attempts.py` на чистых функциях ядра
(`selection`, `sprt`, `psychometrics`, `integrity`, `lifecycle`) без БД. Истину (θ кандидата,
`b` семейства, медиану времени) порождает своя латентная модель; продукт видит только ответы,
время и уходы со вкладки.

Фазы прогона:
1. **main** — честные и «списывающие» кандидаты, каждый проходит путь дважды (разные варианты:
   показанное в первом пути не повторяется, как `repeat_days`). Банк калибруется онлайн, тревоги
   переводят семейства в карантин. Метрики: точность грейда, κ, длина, калибровка, `r_pb`,
   экспозиция, детектор честности.
2. **full** — фиксированная длина (без остановки SPRT): восстановление θ, r(θ̂, θ).
3. **leak** — утекают 20 % активных семейств, 30 % новых кандидатов знают их ответы: ложные
   повышения, ответов до карантина утёкшего семейства.
4. **llm** — LLM-«кандидат» (верно с вероятностью `ai_solvable`, мгновенно); банк не калибрует.

Пилотные слоты не моделируются: они не влияют на θ, LLR и грейд.
Всё детерминировано по `seed`.
"""

from __future__ import annotations

import math
import random
import statistics
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.assessment import selection as sel
from app.assessment import sprt
from app.assessment.config import AssessmentConfig, load_config
from app.assessment.integrity import IntegrityConfig, ItemSignal, assess, load_integrity_config
from app.assessment.lifecycle import Answer, alarm_reasons, compute_stats, pearson
from app.assessment.psychometrics import Observation, calibrate_b, eap, p_correct
from fsp_contracts.assessment import TEST_GRADE_ORDER, TestGrade

GRADES = ("none", *(g.value for g in TEST_GRADE_ORDER))  # none < junior < middle < senior

# Синтетическая профессия: (навык, тип, вес). Покрывает все типы плана теста.
SKILLS: tuple[tuple[str, str, float], ...] = (
    ("algorithms", "fundamental", 1.0),
    ("data_structures", "fundamental", 1.0),
    ("python", "hard", 1.0),
    ("sql", "hard", 0.7),
    ("web", "hard", 0.5),
    ("system_design", "thinking", 1.0),
    ("debugging", "thinking", 0.6),
    ("product", "business", 1.0),
    ("teamwork", "soft", 1.0),
    ("learning", "experience", 1.0),
)
# Насколько ИИ решает задания типа (база; к ней шум ±0.2)
AI_BASE = {
    "fundamental": 0.7,
    "hard": 0.6,
    "thinking": 0.35,
    "business": 0.4,
    "soft": 0.3,
    "experience": 0.3,
}

TARGETS: dict[str, tuple[str, float]] = {
    "grade_accuracy": (">=", 0.90),
    "kappa": (">=", 0.80),
    "mean_items": ("<=", 14),
    "max_share": ("<=", 0.10),
    "theta_r_full": (">=", 0.85),
    "calib_rmse_30": ("<=", 0.40),
    "calib_rmse_100": ("<=", 0.25),
    "median_rpb": (">=", 0.30),
    "leak_false_upgrade": ("<=", 0.05),
    "leak_answers_to_quarantine": ("<=", 100),
    "max_exposure": ("<=", 0.30),
    "integrity_fpr": ("<=", 0.05),
}


@dataclass(frozen=True)
class SimConfig:
    seed: int = 42
    candidates: int = 1000  # фаза main
    full_candidates: int = 300  # фаза full
    full_items: int = 20
    leak_candidates: int = 1000  # фаза leak
    leak_family_share: float = 0.2
    leak_knower_share: float = 0.3
    llm_runs: int = 30  # на каждый заявленный грейд
    families_per_cell: int = 6  # семейств на (навык, уровень)
    b_noise: float = 0.5  # истинная b = априорная по уровню + N(0, b_noise)
    anchor_share: float = 0.1
    cheater_share: float = 0.1
    cheat_item_p: float = 0.5  # доля заданий, где «списывающий» списывает
    honest_away_p: float = 0.03  # честный ушёл со вкладки > 10 с
    rt_sigma: float = 0.35  # лог-разброс времени ответа
    mode: str = "standard"  # standard | express (--mode express)


@dataclass
class Fam:
    idx: int
    skill: str
    skill_type: str
    level: int
    b_true: float
    b: float
    anchor: bool
    ai_solvable: float
    median_ms: float
    uid: uuid.UUID
    status: str = "active"
    n: int = 0
    shown: int = 0  # попыток, где показано
    answers: list[Answer] = field(default_factory=list)
    rts: list[int] = field(default_factory=list)
    b_at: dict[int, float] = field(default_factory=dict)  # b̂ после n ответов
    leaked: bool = False
    leak_n0: int | None = None  # n в момент утечки
    quarantined_after: int | None = None  # ответов после утечки до карантина


@dataclass(frozen=True)
class Person:
    theta: float
    declared: TestGrade
    kind: str = "honest"  # honest | cheater | knower | llm


@dataclass
class Resp:
    fam: Fam
    score: float
    rt_ms: int
    away_ms: tuple[int, ...]


@dataclass
class AttemptOut:
    grade: TestGrade
    passed: bool
    upgrade: TestGrade | None
    theta: float
    items: int  # оцениваемых, оба этапа
    main_items: int
    hit_max: bool
    integrity: float
    responses: list[Resp]


def true_grade(theta: float, cfg: AssessmentConfig) -> str:
    out = "none"
    for g in TEST_GRADE_ORDER:
        if theta >= cfg.cuts[g.value]:
            out = g.value
    return out


def rank(grade: str) -> int:
    return GRADES.index(grade)


class Bank:
    def __init__(self, sc: SimConfig, cfg: AssessmentConfig, rng: random.Random) -> None:
        self.cfg = cfg
        self.fams: list[Fam] = []
        for skill, stype, _w in SKILLS:
            for level in range(1, 6):
                for _ in range(sc.families_per_cell):
                    i = len(self.fams)
                    anchor = rng.random() < sc.anchor_share
                    prior = cfg.prior_b(level)
                    b_true = prior if anchor else prior + rng.gauss(0, sc.b_noise)
                    ai = min(1.0, max(0.0, AI_BASE[stype] + rng.uniform(-0.2, 0.2)))
                    med = (20_000 + 10_000 * level) * math.exp(rng.gauss(0, 0.2))
                    self.fams.append(
                        Fam(
                            i,
                            skill,
                            stype,
                            level,
                            b_true,
                            prior,
                            anchor,
                            ai,
                            med,
                            uuid.UUID(int=i + 1),
                        )
                    )
        self.by_uid = {f.uid: f for f in self.fams}
        self.tests = 0
        self.weights = {s: w for s, _t, w in SKILLS}
        self.types = {s: t for s, t, _w in SKILLS}

    def overexposed(self, f: Fam) -> bool:
        cfg = self.cfg
        return self.tests >= cfg.exposure_min_tests and f.shown / self.tests >= cfg.exposure_max

    def eligible(self, grade: TestGrade, seen: set[int]) -> dict[str, list[Fam]]:
        out: dict[str, list[Fam]] = {}
        for f in self.fams:
            if f.status != "active" or f.idx in seen or self.overexposed(f):
                continue
            if not sel.level_ok(f.level, grade, self.cfg):
                continue
            out.setdefault(f.skill, []).append(f)
        return out

    def plan(self, grade: TestGrade, seen: set[int]) -> list[sel.Section]:
        avail = set(self.eligible(grade, seen))
        return sel.build_plan(self.weights, self.types, grade, self.cfg, available=avail)

    def median_ms(self, f: Fam, icfg: IntegrityConfig) -> float | None:
        rts = f.rts[-icfg.rt_window :]
        return statistics.median(rts) if len(rts) >= icfg.rt_min_n else None


def answer(f: Fam, p: Person, sc: SimConfig, rng: random.Random) -> Resp:
    """Ответ по истинной модели; поведение зависит от типа кандидата."""
    rt = int(f.median_ms * math.exp(rng.gauss(0, sc.rt_sigma)))
    away: tuple[int, ...] = ()
    if p.kind == "llm":
        return Resp(f, float(rng.random() < f.ai_solvable), int(rt * rng.uniform(0.05, 0.15)), ())
    if p.kind == "knower" and f.leaked:
        return Resp(f, 1.0, rt, ())
    if p.kind == "cheater" and rng.random() < sc.cheat_item_p:
        y = float(rng.random() < 0.95)
        if rng.random() < 0.5:  # копирует ответ — быстро
            return Resp(f, y, int(rt * rng.uniform(0.08, 0.25)), ())
        return Resp(f, y, rt, (rng.randint(15_000, 60_000),))  # ищет во вкладке
    if rng.random() < sc.honest_away_p:
        away = (rng.randint(10_500, 30_000),)
    return Resp(f, float(rng.random() < p_correct(p.theta, f.b_true)), rt, away)


def _theta(resps: Sequence[Resp], cfg: AssessmentConfig) -> float:
    return eap([Observation(b=r.fam.b, score=r.score) for r in resps], cfg).theta


def run_attempt(
    bank: Bank,
    p: Person,
    grade: TestGrade,
    seen: set[int],
    sc: SimConfig,
    rng: random.Random,
    icfg: IntegrityConfig,
    *,
    fixed_items: int | None = None,
) -> AttemptOut:
    """Одна попытка: основной этап (SPRT у cut), при праве — бонусный (как `attempts.py`)."""
    cfg = bank.cfg
    bank.tests += 1
    shown_here: set[int] = set()
    resps: list[Resp] = []
    stage_grade, stage_from, llr = grade, 0, 0.0
    bonus = False
    sections = bank.plan(grade, seen)
    main_items, hit_max, passed, upgrade = 0, False, False, None
    while True:
        stage = resps[stage_from:]
        pool = bank.eligible(stage_grade, seen | shown_here)
        counts: dict[str, int] = {}
        for r in stage:
            counts[r.fam.skill] = counts.get(r.fam.skill, 0) + 1
        picked = None
        for section in sel.sections_by_deficit(sections, counts, len(stage)):
            rows = pool.get(section.skill)
            if rows:
                c = sel.choose(
                    [sel.Candidate(f.uid, f.b, f.ai_solvable, f.n) for f in rows],
                    cfg.cuts[stage_grade.value],
                    rng,
                    cfg,
                )
                picked = bank.by_uid[c.id] if c else None
                break
        cut = cfg.cuts[stage_grade.value]
        if picked is None:  # банк этапа исчерпан
            n = len(stage)
            if bonus and n == 0:
                decision = sprt.Decision("failed", True)
            else:
                ok = _theta(resps, cfg) >= cut
                decision = sprt.Decision("passed" if ok else "failed", True)
        else:
            shown_here.add(picked.idx)
            r = answer(picked, p, sc, rng)
            resps.append(r)
            llr += sprt.llr_increment(cut, picked.b, r.score, cfg)
            n = len(resps) - stage_from
            if fixed_items is not None:
                if n < fixed_items:
                    continue
                decision = sprt.Decision("passed" if _theta(resps, cfg) >= cut else "failed", True)
            else:
                max_items = cfg.bonus_max_items if bonus else cfg.max_items
                theta = _theta(resps, cfg) if n >= max_items else None
                decision = sprt.decide(
                    llr,
                    n,
                    min_items=0 if bonus else cfg.min_items,
                    max_items=max_items,
                    exhausted=False,
                    theta=theta,
                    cut=cut,
                    cfg=cfg,
                )
                if decision is None:
                    continue
                if not bonus and n >= max_items:
                    hit_max = True
        if bonus:
            upgrade = stage_grade if decision.result == "passed" else None
            break
        main_items, passed = n, decision.result == "passed"
        nxt = (
            None
            if fixed_items
            else sprt.bonus_eligible(grade, decision, n, _theta(resps, cfg), cfg)
        )
        if nxt is not None:
            sections = bank.plan(nxt, seen | shown_here)
            if sections:
                bonus, stage_grade, stage_from, llr = True, nxt, len(resps), 0.0
                continue
        break
    theta = _theta(resps, cfg)
    signals = [
        ItemSignal(
            b=r.fam.b,
            score=r.score,
            rt_ms=r.rt_ms,
            median_ms=bank.median_ms(r.fam, icfg),
            away_ms=r.away_ms,
        )
        for r in resps
    ]
    integ = assess(signals, 0, cfg, icfg).index
    seen |= shown_here
    for i in shown_here:
        bank.fams[i].shown += 1
    return AttemptOut(grade, passed, upgrade, theta, len(resps), main_items, hit_max, integ, resps)


def finalize(bank: Bank, out: AttemptOut, rng: random.Random, *, calibrate: bool = True) -> None:
    """После попытки: калибровка b по финальному θ, время, статистика и тревоги."""
    cfg = bank.cfg
    for r in out.responses:
        f = r.fam
        f.rts.append(r.rt_ms)
        if not calibrate:
            continue
        f.answers.append(Answer(score=r.score, theta=out.theta, seed=rng.randrange(1 << 30)))
        f.b = calibrate_b(f.b, f.n, out.theta, r.score, cfg, anchor=f.anchor)
        f.n += 1
        if f.n in (30, 100):
            f.b_at[f.n] = f.b
    if not calibrate:
        return
    for f in {r.fam.idx: r.fam for r in out.responses}.values():
        if f.status == "active" and alarm_reasons(compute_stats(f.answers, f.b, cfg), cfg):
            f.status = "quarantine"
            if f.leaked and f.leak_n0 is not None:
                f.quarantined_after = f.n - f.leak_n0


@dataclass
class Journey:
    person: Person
    granted: str
    attempts: list[AttemptOut]
    threshold: float = 0.6  # assessment.integrity.threshold

    @property
    def flagged(self) -> bool:
        return any(a.integrity < self.threshold for a in self.attempts)


def journey(
    bank: Bank,
    p: Person,
    seen: set[int],
    sc: SimConfig,
    rng: random.Random,
    icfg: IntegrityConfig,
    *,
    calibrate: bool = True,
) -> Journey:
    """Путь кандидата: заявленный грейд; при неудаче — сразу грейд ниже (правила грейда)."""
    atts: list[AttemptOut] = []
    grade: TestGrade | None = p.declared
    granted = "none"
    while grade is not None:
        a = run_attempt(bank, p, grade, seen, sc, rng, icfg)
        finalize(bank, a, rng, calibrate=calibrate)
        atts.append(a)
        if a.passed:
            granted = (a.upgrade or grade).value
            break
        i = TEST_GRADE_ORDER.index(grade)
        grade = TEST_GRADE_ORDER[i - 1] if i > 0 and len(atts) == 1 else None
    return Journey(p, granted, atts, bank.cfg.integrity_threshold)


def make_person(rng: random.Random, cfg: AssessmentConfig, kind: str = "honest") -> Person:
    theta = rng.gauss(0, 1)
    tg = max(1, rank(true_grade(theta, cfg)))  # 1..3: junior..senior
    u = rng.random()
    shift = 0 if u < 0.6 else (1 if u < 0.85 else -1)  # приукрашивают чаще, чем скромничают
    declared = TEST_GRADE_ORDER[min(3, max(1, tg + shift)) - 1]
    return Person(theta, declared, kind)


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in GRADES)
    return 1.0 if pe >= 1 else (po - pe) / (1 - pe)


def _rmse(xs: Sequence[float]) -> float | None:
    return math.sqrt(sum(x * x for x in xs) / len(xs)) if xs else None


def _r(x: float | None) -> float | None:
    return None if x is None or math.isnan(x) else round(x, 4)


def run(sc: SimConfig, cfg: AssessmentConfig | None = None) -> dict[str, Any]:
    cfg = (cfg or load_config()).for_mode(sc.mode)
    icfg = load_integrity_config()
    rng = random.Random(sc.seed)
    bank = Bank(sc, cfg, rng)

    # --- main: два пути на кандидата -------------------------------------------------------
    people = [
        make_person(rng, cfg, "cheater" if rng.random() < sc.cheater_share else "honest")
        for _ in range(sc.candidates)
    ]
    seen = [set[int]() for _ in people]
    first = [journey(bank, p, s, sc, rng, icfg) for p, s in zip(people, seen, strict=True)]
    second = [journey(bank, p, s, sc, rng, icfg) for p, s in zip(people, seen, strict=True)]

    honest = [j for j in first if j.person.kind == "honest"]
    honest2 = [j for j in second if j.person.kind == "honest"]
    cheaters = [j for j in first + second if j.person.kind == "cheater"]
    honest_all = honest + honest2
    acc = sum(j.granted == true_grade(j.person.theta, cfg) for j in honest) / max(1, len(honest))
    off1 = sum(
        abs(rank(j.granted) - rank(true_grade(j.person.theta, cfg))) <= 1 for j in honest
    ) / max(1, len(honest))
    clear = [
        j
        for j in honest
        if min(abs(j.person.theta - c) for c in cfg.cuts.values()) >= cfg.sprt_delta
    ]
    acc_clear = sum(j.granted == true_grade(j.person.theta, cfg) for j in clear) / max(
        1, len(clear)
    )
    # Та же точность при фиксированном отступе 0.5 от порогов — сравнима между разными δ.
    clear05 = [j for j in honest if min(abs(j.person.theta - c) for c in cfg.cuts.values()) >= 0.5]
    acc05 = sum(j.granted == true_grade(j.person.theta, cfg) for j in clear05) / max(
        1, len(clear05)
    )
    overgrade = sum(rank(j.granted) > rank(true_grade(j.person.theta, cfg)) for j in honest) / max(
        1, len(honest)
    )
    decisions = [
        (a.passed, j.person.theta >= cfg.cuts[a.grade.value]) for j in honest for a in j.attempts
    ]
    dec_acc = sum(x == y for x, y in decisions) / max(1, len(decisions))
    kappa = cohen_kappa([j.granted for j in honest], [j.granted for j in honest2])
    main_atts = [a for j in honest_all for a in j.attempts]
    mean_items = statistics.fmean(a.main_items for a in main_atts)
    mean_items_total = statistics.fmean(a.items for a in main_atts)
    max_share = sum(a.hit_max for a in main_atts) / len(main_atts)
    theta_r_adaptive = pearson(
        [j.person.theta for j in honest], [j.attempts[-1].theta for j in honest]
    )
    tpr = sum(j.flagged for j in cheaters) / max(1, len(cheaters))
    fpr = sum(j.flagged for j in honest_all) / max(1, len(honest_all))
    cheat_over = sum(
        rank(j.granted) > rank(true_grade(j.person.theta, cfg)) for j in cheaters
    ) / max(1, len(cheaters))

    rmse30 = _rmse([f.b_at[30] - f.b_true for f in bank.fams if 30 in f.b_at and not f.anchor])
    rmse100 = _rmse([f.b_at[100] - f.b_true for f in bank.fams if 100 in f.b_at and not f.anchor])
    rpbs = [
        s.r_pb
        for f in bank.fams
        if f.n >= cfg.admit_min_n and (s := compute_stats(f.answers, f.b, cfg)).r_pb is not None
    ]
    max_exposure = max(f.shown for f in bank.fams) / bank.tests
    quarantined_main = sum(f.status == "quarantine" for f in bank.fams)

    # --- full: фиксированная длина для восстановления θ ------------------------------------
    full_t, full_hat = [], []
    for _ in range(sc.full_candidates):
        p = make_person(rng, cfg)
        a = run_attempt(bank, p, p.declared, set(), sc, rng, icfg, fixed_items=sc.full_items)
        full_t.append(p.theta)
        full_hat.append(a.theta)
    theta_r_full = pearson(full_t, full_hat)

    # --- leak: 20 % активных семейств утекли, 30 % кандидатов знают ответы -----------------
    active = [f for f in bank.fams if f.status == "active"]
    leaked = rng.sample(active, round(len(active) * sc.leak_family_share))
    for f in leaked:
        f.leaked, f.leak_n0 = True, f.n
    clean_before = {f.idx for f in active if not f.leaked}
    leak_j = []
    for _ in range(sc.leak_candidates):
        kind = "knower" if rng.random() < sc.leak_knower_share else "honest"
        leak_j.append(journey(bank, make_person(rng, cfg, kind), set(), sc, rng, icfg))
    knowers = [j for j in leak_j if j.person.kind == "knower"]
    others = [j for j in leak_j if j.person.kind != "knower"]

    def over(js: list[Journey]) -> float:
        bad = sum(rank(j.granted) > rank(true_grade(j.person.theta, cfg)) for j in js)
        return bad / max(1, len(js))

    q_after = sorted(f.quarantined_after for f in leaked if f.quarantined_after is not None)
    leak_answers = [f.n - (f.leak_n0 or 0) for f in leaked]
    false_q = sum(bank.fams[i].status == "quarantine" for i in clean_before)

    # --- llm: LLM как кандидат --------------------------------------------------------------
    llm: dict[str, Any] = {}
    for g in TEST_GRADE_ORDER:
        grants, flags = [], []
        for _ in range(sc.llm_runs):
            j = journey(bank, Person(0.0, g, "llm"), set(), sc, rng, icfg, calibrate=False)
            grants.append(j.granted)
            flags.append(j.flagged)
        llm[g.value] = {
            "granted": {k: grants.count(k) for k in GRADES if grants.count(k)},
            "flagged_share": round(sum(flags) / len(flags), 4),
        }
    ai_solved = sum(f.ai_solvable >= 0.5 for f in bank.fams) / len(bank.fams)

    metrics: dict[str, Any] = {
        "grade_accuracy": _r(acc),
        "grade_accuracy_within1": _r(off1),
        "grade_accuracy_outside_indifference": _r(acc_clear),
        "grade_accuracy_margin_05": _r(acc05),
        "grade_overgrade": _r(overgrade),
        "sprt_decision_accuracy": _r(dec_acc),
        "kappa": _r(kappa),
        "mean_items": _r(mean_items),
        "mean_items_with_bonus": _r(mean_items_total),
        "max_share": _r(max_share),
        "theta_r_adaptive": _r(theta_r_adaptive),
        "theta_r_full": _r(theta_r_full),
        "calib_rmse_30": _r(rmse30),
        "calib_rmse_100": _r(rmse100),
        "median_rpb": _r(statistics.median(rpbs)) if rpbs else None,
        "max_exposure": _r(max_exposure),
        "integrity_tpr": _r(tpr),
        "integrity_fpr": _r(fpr),
        "cheater_overgrade": _r(cheat_over),
        "leak_false_upgrade": _r(over(knowers)),
        "leak_baseline_upgrade": _r(over(others)),
        "leak_excess_upgrade": _r(over(knowers) - over(others)),
        "leak_answers_to_quarantine": statistics.median(q_after) if q_after else None,
        "leak_quarantined_share": _r(len(q_after) / max(1, len(leaked))),
        "leak_median_answers_after": statistics.median(leak_answers) if leak_answers else None,
        "leak_false_quarantine": false_q,
        "quarantined_main": quarantined_main,
        "ai_solvable_share": _r(ai_solved),
    }
    return {
        "seed": sc.seed,
        "config": {k: v for k, v in sc.__dict__.items()},
        "bank": {"families": len(bank.fams), "anchors": sum(f.anchor for f in bank.fams)},
        "counts": {
            "honest_journeys": len(honest_all),
            "cheater_journeys": len(cheaters),
            "attempts_total": bank.tests,
            "families_rpb": len(rpbs),
            "leaked_families": len(leaked),
            "knowers": len(knowers),
        },
        "metrics": metrics,
        "llm": llm,
        "status": {k: check(metrics.get(k), *TARGETS[k]) for k in TARGETS},
    }


def check(value: float | None, op: str, target: float) -> str:
    if value is None:
        return "n/a"
    ok = value >= target if op == ">=" else value <= target
    return "ok" if ok else "fail"
