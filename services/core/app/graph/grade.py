"""Грейд кандидата: сигналы, пороги, ограничения, уверенность, разбивка, `next_grade` (ml.md §5).

С E22-4 (ADR-018) это не грейд кандидата: грейд берётся из `grades` (тест, `assessment.service`).
Баллы тут — сигнал силы профиля и подсказки «как подтвердить»; доказательства `test` из теста
попадают сюда как `test_theta`.

Чистые формулы без БД: вход — `GradeInputs` (собирает `recompute`), параметры — секции
`grade_signals`, `grade_thresholds`, `lead_requirements` из `data/scoring.yaml`.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SCORING_PATH = ROOT / "data" / "scoring.yaml"

GRADES = ("intern", "junior", "junior_plus", "middle", "middle_plus", "senior", "lead")
LEAD = "lead"
NO_COMMERCIAL_CAP = "middle"
PRELIMINARY_BELOW = 0.5
FSP_LEVELS = {"regional": 0, "interregional": 1, "national": 2, "international": 3}
# группы сигналов для grade_confidence (ml.md §5): стаж, ФСП, тесты, код
GROUPS = ("experience", "fsp", "tests", "code")

_ACH_KEYS = {
    "top_national": "national_international_medalist",
    "national_finalist": "national_finalist",
    "interregional_medalist": "interregional_medalist",
    "regional_medalist": "regional_medalist",
    "participant": "participant",
}


@dataclass(frozen=True, slots=True)
class GradeConfig:
    experience: tuple[tuple[int, float], ...] = ((0, 1), (12, 3), (36, 5), (60, 7), (96, 8))
    achievement: Mapping[str, float] = field(
        default_factory=lambda: {
            "top_national": 3.0,
            "national_finalist": 2.0,
            "interregional_medalist": 1.5,
            "regional_medalist": 1.0,
            "participant": 0.5,
        }
    )
    ranks: Mapping[str, float] = field(
        default_factory=lambda: {
            "youth_1": 0.5,
            "youth_2": 0.5,
            "youth_3": 0.5,
            "rank_1": 1.0,
            "rank_2": 1.0,
            "rank_3": 1.0,
            "cms": 2.5,
            "ms": 3.5,
            "msic": 3.5,
        }  # fmt: skip
    )
    test_points: tuple[float, float, float, float] = (0, 1, 2, 3)  # θ<0, 0–1, 1–2, >2
    code_max: float = 2.0
    interview_min: float = 2.0
    interview_points: float = 1.0
    leadership_k: float = 1.5
    thresholds: tuple[tuple[str, float], ...] = (
        ("intern", 0.0), ("junior", 2.0), ("junior_plus", 4.0), ("middle", 6.0),
        ("middle_plus", 8.5), ("senior", 10.5), ("lead", 13.0),
    )  # fmt: skip
    lead_min_leadership: float = 0.5

    @classmethod
    def load(cls, path: Path | str | None = None) -> GradeConfig:
        data = yaml.safe_load(Path(path or DEFAULT_SCORING_PATH).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Mapping | None) -> GradeConfig:
        if not data or "grade_signals" not in data:
            return cls()
        sig, base = data["grade_signals"], cls()
        e = sig["experience"]
        t = sig["test_score"]["points"]
        return cls(
            experience=(
                (0, float(e["under_12m"])),
                (12, float(e["12_35m"])),
                (36, float(e["36_59m"])),
                (60, float(e["60_95m"])),
                (96, float(e["96_plus"])),
            ),
            achievement={k: float(sig["fsp_achievement"][v]) for k, v in _ACH_KEYS.items()},
            ranks={k: float(v) for k, v in sig["fsp_rank"].items()},
            test_points=(
                float(t["negative"]),
                float(t["0_to_1"]),
                float(t["1_to_2"]),
                float(t["over_2"]),
            ),
            code_max=float(sig["code_maturity"]["range"][1]),
            interview_min=float(sig["ai_interview"]["requires_score"]),
            interview_points=float(sig["ai_interview"]["points"]),
            leadership_k=float(sig["leadership"]["multiplier"]),
            thresholds=tuple((g, float(v["min"])) for g, v in data["grade_thresholds"].items()),
            lead_min_leadership=float(
                data.get("lead_requirements", {}).get(
                    "min_leadership_signal", base.lead_min_leadership
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class FspResult:
    """Результат ФСП, как его видит грейд (из `evidence(source=fsp).details`)."""

    level: str  # regional | interregional | national | international
    place: int | None = None
    final: bool = False
    evidence_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class GradeInputs:
    experience_months: int | None = None
    fsp_results: Sequence[FspResult] = ()
    fsp_rank: str | None = None
    fsp_rank_evidence: uuid.UUID | None = None
    test_theta: float | None = None  # максимальный θ по навыкам основной роли
    test_evidence: tuple[uuid.UUID, ...] = ()
    test_skill: str | None = None  # навык, по которому лучший θ (для подсказок)
    code_maturity: float | None = None  # 0…1 (ДНК)
    code_evidence: tuple[uuid.UUID, ...] = ()
    interview_avg: float | None = None  # 0…3
    interview_evidence: tuple[uuid.UUID, ...] = ()
    leadership: float = 0.0  # L, 0…1
    management_confirmed: bool = False
    has_github: bool = False
    has_fsp_link: bool = False


@dataclass(frozen=True, slots=True)
class SignalPoints:
    signal: str
    value: object
    points: float
    evidence_ids: tuple[str, ...] = ()

    def as_json(self) -> dict:
        return {
            "signal": self.signal,
            "value": self.value,
            "points": self.points,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class Hint:
    signal: str
    max_gain: float
    text: str

    def as_json(self) -> dict:
        return {"signal": self.signal, "max_gain": self.max_gain, "text": self.text}


@dataclass(frozen=True, slots=True)
class NextGrade:
    grade: str
    points_needed: float
    hints: list[Hint] = field(default_factory=list)

    def as_json(self) -> dict:
        return {
            "grade": self.grade,
            "points_needed": self.points_needed,
            "hints": [h.as_json() for h in self.hints],
        }


@dataclass(frozen=True, slots=True)
class GradeResult:
    grade: str
    score: float
    confidence: float
    preliminary: bool
    breakdown: list[SignalPoints]
    next_grade: NextGrade | None

    def breakdown_json(self) -> list[dict]:
        return [b.as_json() for b in self.breakdown]

    def next_json(self) -> dict | None:
        return self.next_grade.as_json() if self.next_grade else None


def experience_points(months: int | None, cfg: GradeConfig) -> float:
    """Баллы за стаж: значение последней ступени `experience`, до которой дорос стаж (ml.md §5)."""
    if not months or months <= 0:
        return 0.0
    pts = 0.0
    for lo, p in cfg.experience:
        if months >= lo:
            pts = p
    return pts


def achievement_kind(r: FspResult) -> str:
    """Вид достижения ФСП для баллов грейда: медаль и уровень соревнования, финал (ml.md §5)."""
    medal = r.place is not None and r.place <= 3
    national = FSP_LEVELS.get(r.level, 0) >= FSP_LEVELS["national"]
    if medal and national:
        return "top_national"
    if national and r.final:
        return "national_finalist"
    if medal and r.level == "interregional":
        return "interregional_medalist"
    if medal and r.level == "regional":
        return "regional_medalist"
    return "participant"


def theta_points(theta: float | None, cfg: GradeConfig) -> float:
    """Баллы за θ теста по ступеням `test_points` (<0, <1, ≤2, >2); нет теста — 0 (ml.md §5)."""
    if theta is None:
        return 0.0
    p = cfg.test_points
    if theta < 0:
        return p[0]
    if theta < 1:
        return p[1]
    return p[2] if theta <= 2 else p[3]


def grade_for_points(points: float, cfg: GradeConfig, *, leadership_ok: bool) -> str:
    """Старший грейд, чей порог набран; Lead — только при подтверждённом лидерстве (ml.md §5)."""
    grade = cfg.thresholds[0][0]
    for g, lo in cfg.thresholds:
        if points >= lo and (g != LEAD or leadership_ok):
            grade = g
    return grade


def _signals(inp: GradeInputs, cfg: GradeConfig) -> list[SignalPoints]:
    out: list[SignalPoints] = []
    out.append(
        SignalPoints(
            "experience", inp.experience_months or 0, experience_points(inp.experience_months, cfg)
        )
    )
    if inp.fsp_results:
        best = max(
            inp.fsp_results,
            key=lambda r: (cfg.achievement[achievement_kind(r)], FSP_LEVELS.get(r.level, 0)),
        )
        kind = achievement_kind(best)
        ev = (str(best.evidence_id),) if best.evidence_id else ()
        out.append(SignalPoints("fsp_achievement", kind, cfg.achievement[kind], ev))
    if inp.fsp_rank:
        ev = (str(inp.fsp_rank_evidence),) if inp.fsp_rank_evidence else ()
        out.append(SignalPoints("fsp_rank", inp.fsp_rank, cfg.ranks.get(inp.fsp_rank, 0.0), ev))
    if inp.test_theta is not None:
        out.append(
            SignalPoints(
                "tests",
                round(inp.test_theta, 2),
                theta_points(inp.test_theta, cfg),
                tuple(map(str, inp.test_evidence)),
            )
        )
    if inp.code_maturity is not None:
        m = min(1.0, max(0.0, inp.code_maturity))
        out.append(
            SignalPoints(
                "code_maturity",
                round(m, 2),
                round(m * cfg.code_max, 2),
                tuple(map(str, inp.code_evidence)),
            )
        )
    if inp.interview_avg is not None:
        ok = inp.interview_avg >= cfg.interview_min
        out.append(
            SignalPoints(
                "ai_interview",
                round(inp.interview_avg, 2),
                cfg.interview_points if ok else 0.0,
                tuple(map(str, inp.interview_evidence)),
            )
        )
    if inp.leadership > 0:
        out.append(
            SignalPoints(
                "leadership",
                round(inp.leadership, 2),
                round(cfg.leadership_k * min(1.0, inp.leadership), 2),
            )
        )
    return out


def _groups(inp: GradeInputs) -> set[str]:
    g = set()
    if inp.experience_months and inp.experience_months > 0:
        g.add("experience")
    if inp.fsp_results or inp.fsp_rank:
        g.add("fsp")
    if inp.test_theta is not None or inp.interview_avg is not None:
        g.add("tests")
    if inp.code_maturity is not None:
        g.add("code")
    return g


def _hints(inp: GradeInputs, cfg: GradeConfig, role_skill: str | None) -> list[Hint]:
    hints: list[Hint] = []
    cur_test = theta_points(inp.test_theta, cfg)
    max_test = cfg.test_points[3]
    if cur_test < max_test:
        skill = inp.test_skill or role_skill
        what = f"тест по {skill}" if skill else "тест по навыкам роли"
        hints.append(
            Hint("tests", max_test - cur_test, f"пройди {what}: до +{max_test - cur_test:g}")
        )
    cur_code = (
        round(min(1.0, max(0.0, inp.code_maturity)) * cfg.code_max, 2)
        if inp.code_maturity is not None
        else 0.0
    )
    if cur_code < cfg.code_max:
        verb = "добавь код с тестами и CI" if inp.has_github else "подключи GitHub"
        gain = round(cfg.code_max - cur_code, 2)
        hints.append(Hint("code_maturity", gain, f"{verb}: до +{gain:g}"))
    if inp.interview_avg is None or inp.interview_avg < cfg.interview_min:
        hints.append(
            Hint(
                "ai_interview",
                cfg.interview_points,
                f"пройди ИИ-интервью по коду: до +{cfg.interview_points:g}",
            )
        )
    if not inp.fsp_results and not inp.fsp_rank:
        top = max(cfg.achievement.values())
        hints.append(Hint("fsp", top, f"привяжи профиль ФСП: до +{top:g}"))
    if not inp.experience_months:
        hints.append(Hint("experience", cfg.experience[0][1], "добавь опыт работы в профиль"))
    return sorted(hints, key=lambda h: (-h.max_gain, h.signal))


def compute_grade(
    inp: GradeInputs, cfg: GradeConfig, *, role_skill: str | None = None
) -> GradeResult:
    """Сигнал силы профиля в баллах: сумма сигналов, грейд по порогам, ограничения и разбивка (ml.md
    §5).
    """
    breakdown = _signals(inp, cfg)
    score = round(sum(b.points for b in breakdown), 2)
    leadership_ok = inp.leadership >= cfg.lead_min_leadership or inp.management_confirmed
    grade = grade_for_points(score, cfg, leadership_ok=leadership_ok)
    if grade_for_points(score, cfg, leadership_ok=True) == LEAD and not leadership_ok:
        breakdown.append(SignalPoints("constraint_lead_requires_leadership", False, 0.0))
    cap_idx = GRADES.index(NO_COMMERCIAL_CAP)
    if not inp.experience_months and GRADES.index(grade) > cap_idx:
        grade = NO_COMMERCIAL_CAP
        breakdown.append(SignalPoints("constraint_no_commercial_cap", NO_COMMERCIAL_CAP, 0.0))

    confidence = round(len(_groups(inp)) / len(GROUPS), 2)
    nxt: NextGrade | None = None
    idx = GRADES.index(grade)
    if idx < len(GRADES) - 1:
        target = GRADES[idx + 1]
        lo = dict(cfg.thresholds)[target]
        nxt = NextGrade(target, round(max(0.0, lo - score), 2), _hints(inp, cfg, role_skill))
    return GradeResult(grade, score, confidence, confidence < PRELIMINARY_BELOW, breakdown, nxt)
