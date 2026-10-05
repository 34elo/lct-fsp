"""E24-1: индекс честности и таймер p95 (assessment.md §8) — формулы на числах документа."""

import math
import uuid
from pathlib import Path
from random import Random

import pytest
from app.assessment import families as registry
from app.assessment.config import load_config
from app.assessment.families.base import BaseFamily, Item, Kind
from app.assessment.integrity import (
    IntegrityConfig,
    ItemSignal,
    assess,
    integrity_index,
    load_integrity_config,
    parse_telemetry,
    person_fit_lz,
    quantile,
    time_limit_s,
)
from app.assessment.models import Attempt, Grade
from app.assessment.psychometrics import Observation, eap, p_correct
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from core_helpers import register
from fsp_contracts.assessment import SkillType
from fsp_platform.db import session_scope

CFG = load_config()
IC = load_integrity_config()


def _plain(n: int = 6, b: float = 0.0, score: float = 1.0) -> list[ItemSignal]:
    return [ItemSignal(b=b, score=score, rt_ms=60_000, median_ms=60_000) for _ in range(n)]


def test_config_matches_document():
    assert IC == IntegrityConfig()  # scoring.yaml = значения §8 по умолчанию
    assert (IC.fast_margin, IC.fast_ratio, IC.fast_penalty) == (-0.5, 0.3, 0.15)
    assert (IC.away_min_ms, IC.away_penalty, IC.away_max) == (10_000, 0.1, 0.3)
    assert (IC.lz_threshold, IC.lz_penalty, IC.copy_penalty) == (-2.0, 0.2, 0.3)
    assert CFG.integrity_threshold == 0.6


def test_clean_attempt_is_one():
    res = integrity_index(_plain(), theta=0.0, copy_matches=0, cfg=IC)
    assert res.index == 1.0 and res.penalties == {}


def test_fast_correct_on_hard_item_minus_015_each():
    # θ = −1, b = 0: θ − b = −1 < −0.5 — трудное; 17 с < 0.3 × 60 с = 18 с
    fast = ItemSignal(b=0.0, score=1.0, rt_ms=17_000, median_ms=60_000)
    items = [fast, fast] + _plain(4, b=-2.0, score=0.0)
    res = integrity_index(items, theta=-1.0, copy_matches=0, cfg=IC)
    assert res.fast_correct == 2 and res.penalties["fast_correct"] == pytest.approx(0.30)
    # не быстро (18 с = порог), не трудно (θ − b = −0.5), неверно, нет медианы — без штрафа
    for it, theta in [
        (ItemSignal(b=0.0, score=1.0, rt_ms=18_000, median_ms=60_000), -1.0),
        (ItemSignal(b=0.0, score=1.0, rt_ms=1_000, median_ms=60_000), -0.5),
        (ItemSignal(b=0.0, score=0.0, rt_ms=1_000, median_ms=60_000), -1.0),
        (ItemSignal(b=0.0, score=1.0, rt_ms=1_000, median_ms=None), -1.0),
    ]:
        assert integrity_index([it], theta, 0, IC).fast_correct == 0


def test_tab_away_minus_01_each_max_03():
    away = ItemSignal(b=0.0, score=1.0, away_ms=(3_000, 10_001))
    assert integrity_index([away], 0.0, 0, IC).index == pytest.approx(0.9)
    assert integrity_index([away] * 2, 0.0, 0, IC).index == pytest.approx(0.8)
    res = integrity_index([away] * 5, 0.0, 0, IC)
    assert res.tab_away == 5 and res.index == pytest.approx(0.7)  # максимум −0.3
    # ровно 10 с или уход перед неверным ответом — не сигнал
    assert integrity_index([ItemSignal(b=0, score=1.0, away_ms=(10_000,))], 0.0, 0, IC).index == 1
    assert integrity_index([ItemSignal(b=0, score=0.0, away_ms=(60_000,))], 0.0, 0, IC).index == 1


def test_person_fit_lz_formula_and_penalty():
    # θ = b: ln(P/(1 − P)) = 0 → V = 0, lz не определён
    assert person_fit_lz(0.0, [(0.0, 1.0)]) is None
    # θ = 0, b = ±2: P = 0.881 / 0.119; верный на трудном и неверный на лёгком
    p = p_correct(0.0, -2.0)
    lp, lq = math.log(p), math.log(1 - p)
    l0 = 2 * lq
    e = 2 * (p * lp + (1 - p) * lq)
    v = 2 * p * (1 - p) * (lp - lq) ** 2
    assert person_fit_lz(0.0, [(-2.0, 0.0), (2.0, 1.0)]) == pytest.approx((l0 - e) / math.sqrt(v))
    assert (l0 - e) / math.sqrt(v) == pytest.approx(-3.844, abs=0.001)
    # 6 «наоборот»-ответов → lz < −2 → −0.2
    odd = [ItemSignal(b=-2.0, score=0.0)] * 3 + [ItemSignal(b=2.0, score=1.0)] * 3
    res = integrity_index(odd, 0.0, 0, IC)
    assert res.lz < -2 and res.penalties == {"person_fit": 0.2} and res.index == 0.8
    # меньше lz_min_items ответов — lz не считается
    assert integrity_index(odd[:5], 0.0, 0, IC).lz is None


def test_copy_minus_03_from_two_matches():
    assert integrity_index(_plain(), 0.0, 1, IC).index == 1.0
    assert integrity_index(_plain(), 0.0, 2, IC).index == pytest.approx(0.7)


def test_threshold_06_combination():
    # копия −0.3 + два ухода −0.2 = 0.5 < 0.6 → «требует подтверждения»
    away = ItemSignal(b=0.0, score=1.0, away_ms=(20_000,))
    res = integrity_index([away, away], 0.0, 2, IC)
    assert res.index == pytest.approx(0.5) and res.index < CFG.integrity_threshold
    # одна копия ровно 0.7 — без пометки
    assert integrity_index(_plain(), 0.0, 3, IC).index >= CFG.integrity_threshold
    # не уходит ниже 0
    fast = ItemSignal(b=3.0, score=1.0, rt_ms=1, median_ms=60_000)
    assert integrity_index([fast] * 10, 0.0, 5, IC).index == 0.0


def test_parse_telemetry_is_defensive():
    assert parse_telemetry({"away_ms": [12_000, -1, "x", 5.0], "pastes": 2}) == ((12_000, 5), 2)
    assert parse_telemetry(None) == ((), 0)
    assert parse_telemetry({"away_ms": "bad", "pastes": -3}) == ((), 0)


def test_timer_is_p95():
    rts = [i * 1000 for i in range(1, 101)]  # 1…100 с
    assert quantile(rts, 0.95) == pytest.approx(95_050)
    assert quantile(rts, 0.5) == pytest.approx(50_500)
    assert time_limit_s(rts, 120, IC) == 96  # ⌈95.05⌉
    assert time_limit_s(rts[:19], 120, IC) == 120  # < 20 ответов — таймер семейства
    assert time_limit_s([1000] * 30, 120, IC) == 15  # не меньше min_s


# --- синтетика: «списывающие» помечаются, ложных срабатываний ≤ 5 % -----------------------------

N_ITEMS = 12
MEDIAN = 60_000.0


def _rt(rng: Random) -> int:
    return int(MEDIAN * math.exp(rng.gauss(0.0, 0.45)))


def _honest(rng: Random) -> tuple[list[ItemSignal], float, int]:
    theta = rng.gauss(0.0, 1.0)
    items = []
    for _ in range(N_ITEMS):
        b = rng.uniform(-2.0, 2.0)
        y = 1.0 if rng.random() < p_correct(theta, b) else 0.0
        away = (rng.randint(2_000, 40_000),) if rng.random() < 0.05 else ()
        items.append(ItemSignal(b=b, score=y, rt_ms=_rt(rng), median_ms=MEDIAN, away_ms=away))
    return items, theta, 1 if rng.random() < 0.05 else 0


def _cheater(rng: Random, kind: str) -> tuple[list[ItemSignal], float, int]:
    theta = rng.gauss(-1.0, 0.5)
    items = []
    for _ in range(N_ITEMS):
        b = rng.uniform(-2.0, 2.0)
        honest_y = 1.0 if rng.random() < p_correct(theta, b) else 0.0
        if kind == "lookup":  # ищет ответ в другой вкладке; rt_ms — активное время на вкладке
            if b > theta + 0.5:
                away = (rng.randint(15_000, 90_000),)
                items.append(ItemSignal(b, 1.0, rng.randint(3_000, 15_000), MEDIAN, away_ms=away))
                continue
        elif kind == "leak":  # знает ключи трудных заданий и отвечает мгновенно
            if b > theta + 0.5:
                items.append(ItemSignal(b, 1.0, rng.randint(3_000, 15_000), MEDIAN))
                continue
        items.append(ItemSignal(b, honest_y, _rt(rng), MEDIAN))
    copies = rng.randint(2, 5) if kind == "copy" else 0
    if kind == "copy":  # списывает у соседа: плюс уходы со вкладки перед верными
        items = [
            ItemSignal(it.b, 1.0, it.rt_ms, MEDIAN, away_ms=(20_000,)) if it.b > theta else it
            for it in items
        ]
    return items, theta, copies


def _flagged(items: list[ItemSignal], copies: int) -> bool:
    return assess(items, copies, CFG, IC).index < CFG.integrity_threshold


def test_theta_ref_ignores_fast_answers():
    # списанные быстрые верные ответы не завышают опорный θ: трудность меряется без них
    slow = [ItemSignal(b=-1.0, score=0.0, rt_ms=60_000, median_ms=60_000)] * 4
    quick = [ItemSignal(b=1.0, score=1.0, rt_ms=5_000, median_ms=60_000)] * 8
    full = eap([Observation(b=it.b, score=it.score) for it in slow + quick], CFG).theta
    assert full == pytest.approx(0.857, abs=0.01)  # θ − b = −0.14: по итоговому θ «не трудно»
    assert integrity_index(slow + quick, full, 0, IC).fast_correct == 0
    res = assess(slow + quick, 0, CFG, IC)  # опорный θ ≈ −1.53 по медленным ответам
    assert res.fast_correct == 8 and res.index == 0.0


def test_synthetic_cheaters_flagged_false_positives_le_5pct():
    rng = Random(20261006)
    honest = [_flagged(*(lambda r: (r[0], r[2]))(_honest(rng))) for _ in range(1000)]
    fp = sum(honest) / len(honest)
    assert fp <= 0.05, fp
    for kind in ["lookup", "leak", "copy"]:
        runs = [_cheater(rng, kind) for _ in range(300)]
        rate = sum(_flagged(items, c) for items, _, c in runs) / len(runs)
        assert rate >= 0.8, (kind, rate)


# --- сквозной путь: телеметрия ответа → индекс попытки → грейд ---------------------------------

TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"


class _Fake(BaseFamily):
    kind = Kind.exact
    skill_type = SkillType.hard

    def __init__(self, slug: str, skill: str, level: int):
        self.slug, self.skill, self.level = slug, skill, level

    def generate(self, rng, world) -> Item:
        return Item(Kind.exact, f"{self.slug}: введите 1", "1")


@pytest.fixture
async def bank(factory, monkeypatch):
    reg = {}
    for skill in ["python", "sql", "algorithms", "estimation", "debugging"]:
        for level in range(1, 6):
            for j in range(6):
                f = _Fake(f"t_{skill}_{level}_{j}", skill, level)
                reg[f.slug] = f
    monkeypatch.setattr(registry, "REGISTRY", reg)
    async with session_scope(factory) as s:
        await tax.sync(s, load_taxonomy(TAXONOMY))


async def test_attempt_integrity_from_telemetry(api, factory, bank):
    h = register(api)
    body = {"profession": "backend", "declared_grade": "middle"}
    aid = api.post("/assessment/attempts", json=body, headers=h).json()["id"]
    while True:
        nxt = api.get(f"/assessment/attempts/{aid}/next", headers=h).json()
        if nxt["done"]:
            break
        assert nxt["time_limit_s"] == 120  # данных мало — таймер семейства
        ans = {
            "response_id": nxt["response_id"],
            "answer": "1",
            "rt_ms": 40_000,
            "telemetry": {"away_ms": [25_000], "pastes": 1},
        }
        assert api.post(f"/assessment/attempts/{aid}/answers", json=ans, headers=h).is_success
    res = api.get(f"/assessment/attempts/{aid}", headers=h).json()["result"]
    assert res["integrity"] == pytest.approx(0.7)  # уходы: −0.1 за каждый, максимум −0.3
    async with session_scope(factory) as s:
        att = await s.get(Attempt, uuid.UUID(aid))
        assert att.integrity == pytest.approx(0.7)
        assert att.plan["integrity"]["penalties"] == {"tab_away": 0.3}
        assert att.plan["integrity"]["pastes"] >= 6
        row = await s.get(Grade, (att.candidate_id, "backend"))
        assert row.integrity == pytest.approx(0.7) and not row.needs_confirmation
