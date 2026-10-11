"""Слагаемое F силы профиля по результативности."""

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


# --- релевантность дисциплины профессии -------------------------------

from dataclasses import replace  # noqa: E402
from pathlib import Path  # noqa: E402

from app.graph.fsp_strength import (  # noqa: E402
    discipline_relevance,
    is_relevant,
    relevance_multiplier,
)
from app.taxonomy.loader import parse_discipline_rules  # noqa: E402

RULES = parse_discipline_rules(
    Path(__file__).resolve().parents[3] / "data" / "fsp" / "discipline_rules.yaml"
)
SEC_PROFILE = {"security": 1.0, "pentest": 0.8, "networks": 0.7, "linux": 0.6}


def rel(discipline, profile=SEC_PROFILE, track=None):
    return discipline_relevance(RULES[discipline], profile, track)


def test_relevance_is_weight_share_of_discipline_skills_in_profile():
    # security: сумма весов 4.3; в профиле нет reverse_engineering и cryptography
    assert rel("security") == pytest.approx((1.0 + 0.8 + 0.7 + 0.7) / 4.3, abs=1e-5)
    assert rel("uav") == pytest.approx(0.0)  # ни одного навыка дисциплины нет в профиле
    assert discipline_relevance([], SEC_PROFILE) is None  # правил нет — множитель не применяется


def test_relevant_discipline_weighs_more_than_robotics():
    sec = fsp_term([replace(r(2, 40), relevance=rel("security"))], TODAY, CFG)
    uav = fsp_term([replace(r(2, 40), relevance=rel("uav"))], TODAY, CFG)
    none = fsp_term([r(2, 40)], TODAY, CFG)
    assert uav < sec <= none
    assert uav > 0  # нерелевантная дисциплина весит меньше, но не ноль
    assert uav == pytest.approx(none * CFG.f_relevance_floor, rel=1e-3)


def test_multiplier_bounds_and_labels():
    assert relevance_multiplier(None, CFG) == 1.0
    assert relevance_multiplier(1.0, CFG) == 1.0
    assert relevance_multiplier(0.0, CFG) == CFG.f_relevance_floor == 0.4
    assert is_relevant(rel("security"), CFG) is True
    assert is_relevant(rel("uav"), CFG) is False
    assert is_relevant(None, CFG) is None


def test_track_rules_only_for_matching_track():
    web = {"frontend": 1.0, "backend": 1.0}
    assert discipline_relevance(RULES["product"], web, "web") > discipline_relevance(
        RULES["product"], web, "ml"
    )


def test_relevance_ctx_marks_highlight_relevance():
    from app.matching.search import RelevanceCtx

    ctx = RelevanceCtx(
        {d: [(s, w, t) for s, w, t in rs] for d, rs in RULES.items()}, {"security": SEC_PROFILE}
    )
    assert is_relevant(ctx.of("security", "security", None), CFG) is True  # «релевантно»
    assert is_relevant(ctx.of("security", "uav", None), CFG) is False  # «другое направление»
    assert ctx.of("backend", "security", None) is None  # профиль профессии неизвестен
