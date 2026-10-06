"""Слагаемое F силы профиля по результативности (ADR-025 п. 3, E32-2)."""

from datetime import date

import pytest
from app.graph.fsp_strength import FspResultIn, FspStrengthConfig, fsp_term, result_tier

CFG = FspStrengthConfig.from_dict({"evidence_sources": {"fsp": {}}})
TODAY = date(2026, 10, 6)


def r(place=None, total=None, final=False, when=date(2026, 5, 1), verified=True):
    return FspResultIn(place, total, final, when, verified)


def test_tiers():
    assert result_tier(r(1, 40), CFG) == "winner"
    assert result_tier(r(3, 40), CFG) == "prize"
    assert result_tier(r(8, 40), CFG) == "finalist"  # топ-25%
    assert result_tier(r(30, 40, final=True), CFG) == "finalist"
    assert result_tier(r(30, 40), CFG) == "participant"
    assert result_tier(r(), CFG) == "no_result"


def test_ten_online_appearances_weaker_than_one_prize():
    many = fsp_term([r() for _ in range(10)], TODAY, CFG)
    one = fsp_term([r(2, 40)], TODAY, CFG)
    assert 0 < many < 0.2 < one


def test_no_fsp_is_zero():
    assert fsp_term([], TODAY, CFG) == 0.0


def test_diminishing_returns_and_cap():
    one = fsp_term([r(30, 40, when=TODAY)], TODAY, CFG)
    two = fsp_term([r(30, 40, when=TODAY)] * 2, TODAY, CFG)
    five = fsp_term([r(30, 40, when=TODAY)] * 5, TODAY, CFG)
    assert one < two < five
    assert two - one < one  # отдача убывает
    assert fsp_term([r(1, 10, when=TODAY)] * 5, TODAY, CFG) == CFG.max_strength


def test_level_and_discipline_do_not_matter():
    # на входе уровня нет вообще: равные результаты дают равный F
    assert fsp_term([r(2, 40)], TODAY, CFG) == fsp_term([r(2, 40)], TODAY, CFG)


def test_recency_is_soft_and_unverified_halves():
    fresh = fsp_term([r(30, 40, when=TODAY)], TODAY, CFG)
    old = fsp_term([r(30, 40, when=date(2010, 1, 1))], TODAY, CFG)
    assert old == pytest.approx(fresh * CFG.f_decay_floor, rel=0.05)
    assert fsp_term([r(30, 40, when=TODAY, verified=False)], TODAY, CFG) == pytest.approx(
        fresh * 0.5
    )
