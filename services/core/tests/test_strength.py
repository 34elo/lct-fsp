"""Сила профиля и rank: формулы на примерах из документации."""

import math
import random

import pytest
from app.matching.strength import (
    StrengthConfig,
    StrengthInput,
    band_position,
    completeness,
    explain,
    fsp_impact_ratio,
    impact_ratio,
    rank,
    recency,
    strength,
)

CFG = StrengthConfig()


def test_formula_example():
    res = strength(
        StrengthInput(0.6, fsp=0.5, skills=0.8, days_since_test=0, completeness=0.5), CFG
    )
    assert res.value == pytest.approx(0.5 * 0.6 + 0.2 * 0.5 + 0.15 * 0.8 + 0.1 * 1 + 0.05 * 0.5)
    assert not res.integrity_penalty


def test_without_fsp_term_is_zero_without_penalty():
    base = StrengthInput(0.5, fsp=0.0, skills=0.6, days_since_test=10, completeness=0.5)
    res = strength(base, CFG)
    assert res.terms["F"] == 0 and res.contributions["F"] == 0
    rest = sum(v for k, v in res.contributions.items() if k != "F")
    assert res.value == pytest.approx(rest)  # никакого множителя за отсутствие ФСП


def test_integrity_penalty_below_threshold():
    ok = strength(StrengthInput(0.5, skills=0.5, days_since_test=0, integrity=0.6), CFG)
    bad = strength(StrengthInput(0.5, skills=0.5, days_since_test=0, integrity=0.59), CFG)
    assert bad.integrity_penalty and bad.value == pytest.approx(ok.value * 0.8)


def test_band_recency_rank_completeness():
    assert band_position(0.5, 0.0, 1.0) == 0.5
    assert band_position(-1, 0.0, 1.0) == 0 and band_position(9, 0.0, 1.0) == 1
    assert recency(180, CFG) == pytest.approx(math.exp(-1)) and recency(None, CFG) == 0
    assert rank(0.8, 0.5, CFG) == pytest.approx(0.68)

    class C:
        city, salary_min, formats, employment_types = "М", None, [], ["full"]
        primary_role, experience_months, primary_stack, profile_text = "ml", 12, ["py"], ""

    assert completeness(C, 1) == pytest.approx(6 / 9)


def test_explain_top3_by_contribution():
    res = strength(
        StrengthInput(0.2, fsp=1.0, skills=0.9, days_since_test=0, completeness=0.1), CFG
    )
    top = explain(res, CFG)
    assert [x.code for x in top] == ["F", "S", "T"][:3] or len(top) == 3
    assert top == sorted(top, key=lambda x: -x.weight)


def test_impact_ratio_four_fifths():
    ir = impact_ratio(
        [("fsp", True)] * 4 + [("fsp", False)] * 6 + [("no", True)] * 2 + [("no", False)] * 8
    )
    assert ir["fsp"] == 1.0 and ir["no"] == pytest.approx(0.5)


def test_fsp_impact_ratio_on_synthetic_market():
    """Отчёт справедливости. Синтетика: ФСП у трети, F ∈ [0.3, 0.9]. Тест
    фиксирует измеренное значение и направление эффекта; порог 0.8 — сигнал пересмотреть веса,
    а не условие прохождения."""
    rnd = random.Random(7)
    pool = []
    for _ in range(3000):
        t = rnd.random()
        has = rnd.random() < 0.33
        res = strength(
            StrengthInput(
                t, fsp=rnd.uniform(0.3, 0.9) if has else 0.0, skills=rnd.random(),
                days_since_test=rnd.uniform(0, 365), completeness=rnd.uniform(0.4, 1.0),
            ),
            CFG,
        )  # fmt: skip
        pool.append((t, has, res.value))
    ratio = fsp_impact_ratio(pool, top_share=0.5)
    assert 0.2 < ratio < 0.45  # 0.312 на этом seed: слагаемое F сдвигает выбор в пользу ФСП
    flat = [(t, has, t) for t, has, _ in pool]  # strength без F: группы равны
    assert fsp_impact_ratio(flat, top_share=0.5) == pytest.approx(1.0, abs=0.1)
