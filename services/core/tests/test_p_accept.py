"""p_accept: формула matching.md §4.1 на примерах, подсказка по порогам."""

import math

from app.matching.p_accept import PAcceptConfig, hint, mutual, p_accept

CFG = PAcceptConfig.load()


def _p(**over):
    base = dict(
        salary_to=300_000, salary_min=300_000, vacancy_formats=["remote"],
        candidate_formats=["remote"], vacancy_skills=["python"], primary_stack=["python"],
        responsibility_score=3.0, active=False, cfg=CFG,
    )  # fmt: skip
    return p_accept(**(base | over))


def test_config_comes_from_scoring_yaml():
    assert (CFG.intercept, CFG.salary_gap, CFG.low, CFG.high) == (-0.5, 4.0, 0.35, 0.65)


def test_formula_example():
    # gap 0, format 1, stack 1, rating 0, active 0: z = -0.5 + 1 + 1.5 = 2.0
    assert math.isclose(_p(), 1 / (1 + math.exp(-2.0)))
    # всё нулевое: z = b0
    p0 = _p(candidate_formats=["office"], primary_stack=["go"], salary_min=None)
    assert math.isclose(p0, 1 / (1 + math.exp(0.5)))


def test_salary_gap_is_clamped_and_monotonic():
    assert _p(salary_to=200_000) < _p() < _p(salary_to=330_000)
    assert _p(salary_to=1) == _p(salary_to=150_000)  # −0.5 — нижняя обрезка
    assert _p(salary_to=900_000) == _p(salary_to=450_000)  # +0.5 — верхняя обрезка


def test_hint_thresholds():
    assert hint(0.2, CFG) == "low" and hint(0.5, CFG) == "medium" and hint(0.9, CFG) == "high"
    assert hint(0.35, CFG) == "medium" and hint(0.65, CFG) == "medium"


def test_active_and_rating_raise_probability():
    assert _p(active=True) > _p()
    assert _p(responsibility_score=5.0) > _p() > _p(responsibility_score=1.0)


def test_mutual_is_harmonic_mean():
    assert math.isclose(mutual(0.8, 0.4), 2 * 0.8 * 0.4 / 1.2)
    assert mutual(0.6, 0.6) == 0.6 and mutual(0.0, 0.0) == 0.0
    assert mutual(0.9, 0.1) < 0.5  # низкий интерес тянет H вниз сильнее среднего


def test_suggest_raise_ladder():
    from app.matching.p_accept import suggest_raise

    def compute(to):
        return min(0.9, to / 1_000_000)

    # достигает high: первый шаг с p ≥ 0.65, верх округлён до 5000
    to, p = suggest_raise(500_000, 0.5, compute, CFG)
    assert p >= CFG.high and to % CFG.raise_round == 0 and to < 500_000 * 1.45
    assert suggest_raise(700_000, 0.7, compute, CFG) is None  # уже высокая
    # high недостижим, но из «низкой» можно подняться до «средней»
    to, p = suggest_raise(300_000, 0.3, lambda t: 0.36, CFG)
    assert CFG.low <= p < CFG.high and to == 315_000
    assert suggest_raise(300_000, 0.3, lambda t: 0.3, CFG) is None
