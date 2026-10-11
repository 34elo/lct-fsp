"""Формулы доверия на примерах."""

import uuid
from datetime import date, timedelta

import pytest
from app.graph.trust import EvidenceView, TrustConfig, combine, effective_strength, level_for

CFG = TrustConfig.load()
TODAY = date(2026, 6, 1)


def ev(source, s, observed=TODAY, verified=True):
    return EvidenceView(uuid.uuid4(), source, s, observed, verified)


def test_config_from_scoring_yaml():
    assert CFG.level_min == (0.0, 0.2, 0.4, 0.6, 0.8)
    assert CFG.half_life_years["github"] == 2 and CFG.half_life_years["fsp"] == 3
    assert CFG.half_life_years["resume"] is None
    assert CFG.provisional_cap == 0.25 and CFG.test_validity_months == 12


@pytest.mark.parametrize(
    ("items", "level"),
    [
        ([("resume", 0.30)], 1),  # только резюме -> ●○○○
        ([("github", 0.50)], 2),
        ([("github", 0.50), ("resume", 0.30)], 3),  # 1 - 0.5*0.7 = 0.65
        ([("test", 0.65)], 3),
        ([("fsp", 0.90)], 4),
        ([("self", 0.15)], 0),
    ],
)
def test_levels_match_product_table(items, level):
    t = combine([ev(s, v) for s, v in items], TODAY, CFG)
    assert t is not None and t.level == level


def test_noisy_or_value_and_claimed_only():
    t = combine([ev("github", 0.5), ev("resume", 0.3)], TODAY, CFG)
    assert t.confidence == 0.65 and not t.claimed_only and t.sources == ["github", "resume"]
    t = combine([ev("self", 0.15), ev("resume", 0.3)], TODAY, CFG)
    assert t.claimed_only and t.confidence == 0.405 and t.level == 2


def test_level_boundaries():
    assert [level_for(c, CFG) for c in (0.199, 0.2, 0.399, 0.4, 0.6, 0.8, 1.0)] == [
        0,
        1,
        1,
        2,
        3,
        4,
        4,
    ]


def test_max_within_source_ten_resumes_do_not_add_up():
    t = combine([ev("resume", 0.25), ev("resume", 0.30), ev("resume", 0.40)] * 4, TODAY, CFG)
    assert t.confidence == 0.4 and t.sources == ["resume"]


def test_decay_half_life():
    two_years = TODAY - timedelta(days=round(365.25 * 2))
    assert effective_strength(ev("github", 0.6, two_years), TODAY, CFG) == pytest.approx(
        0.3, abs=1e-3
    )
    three = TODAY - timedelta(days=round(365.25 * 3))
    assert effective_strength(ev("fsp", 0.9, three), TODAY, CFG) == pytest.approx(0.45, abs=1e-3)
    old = TODAY - timedelta(days=5000)
    assert effective_strength(ev("resume", 0.3, old), TODAY, CFG) == 0.3  # без затухания
    assert effective_strength(ev("github", 0.6, TODAY + timedelta(days=9)), TODAY, CFG) == 0.6


def test_test_result_expires_after_12_months():
    fresh = TODAY - timedelta(days=360)
    stale = TODAY - timedelta(days=380)
    assert effective_strength(ev("test", 0.7, fresh), TODAY, CFG) > 0
    assert effective_strength(ev("test", 0.7, stale), TODAY, CFG) == 0
    assert combine([ev("test", 0.7, stale)], TODAY, CFG) is None


def test_unverified_fsp_halved_and_provisional_capped():
    assert effective_strength(ev("fsp", 0.9, verified=False), TODAY, CFG) == pytest.approx(0.45)
    assert effective_strength(ev("fsp", 0.9), TODAY, CFG, provisional=True) == 0.25
    t = combine([ev("fsp", 0.9)], TODAY, CFG, provisional=True)
    assert t.level == 1


def test_top_evidence_strongest_first_max_three():
    items = [ev("github", 0.5), ev("resume", 0.3), ev("fsp", 0.9), ev("test", 0.6)]
    t = combine(items, TODAY, CFG)
    assert t.top_evidence == [items[2].id, items[3].id, items[0].id]


def test_single_test_never_reaches_level_4():
    """Один тест (даже полный балл) — не выше ●●●○; ●●●● только со вторым источником."""
    from app.assessment.config import load_config

    cap = load_config().evidence_max_strength
    assert cap == CFG.level_min[4] - 0.05
    one = combine([ev("test", cap)], TODAY, CFG)
    assert one.level == 3
    assert combine([ev("test", cap), ev("fsp", 0.5)], TODAY, CFG).level == 4
