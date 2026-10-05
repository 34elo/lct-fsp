"""E22-3: SPRT, бонусный этап, выбор задания, экспозиция, пилотные слоты (assessment.md §5–6).

Числа — из документа: θ₀/θ₁ = cut ∓ 0.4, границы ±2.197, минимум 6 / максимум 20, бонус ≤ 10 и
θ ≥ cut_след − 0.5, доли секций по грейду, счёт `P(1−P)·(1 − 0.3·ai_solvable)`, топ-3, 2 пилота
после 3-го задания. Плюс симуляция: точность классификации ≥ 90 %, в среднем ≤ 14 заданий.
"""

import dataclasses
import math
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random

import pytest
from app.assessment import attempts, engine, sprt
from app.assessment import families as registry
from app.assessment import selection as sel
from app.assessment.config import load_config
from app.assessment.families.base import BaseFamily, Item, Kind
from app.assessment.models import Attempt, FamilyRow, Response
from app.assessment.psychometrics import Observation, eap, p_correct
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from core_helpers import register
from fsp_contracts.assessment import TEST_GRADE_ORDER, SkillType, TestGrade
from fsp_platform.db import session_scope
from sqlalchemy import select

CFG = load_config()
TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"
J, M, S = TestGrade.junior, TestGrade.middle, TestGrade.senior

# --- SPRT (§5) --------------------------------------------------------------------------------


def test_sprt_bounds_and_hypotheses():
    lo, hi = sprt.bounds(CFG)
    assert hi == pytest.approx(2.197, abs=1e-3) and lo == pytest.approx(-2.197, abs=1e-3)
    assert sprt.hypotheses(0.0, CFG) == (-0.4, 0.4)
    assert sprt.hypotheses(-1.0, CFG) == pytest.approx((-1.4, -0.6))


def test_llr_increment_numbers():
    # у порога: ln(P₁/P₀) = ln(σ(0.4)/σ(−0.4)) = 0.4; неверный — −0.4; половина — 0
    assert sprt.llr_increment(0.0, 0.0, 1.0, CFG) == pytest.approx(0.4)
    assert sprt.llr_increment(0.0, 0.0, 0.0, CFG) == pytest.approx(-0.4)
    assert sprt.llr_increment(0.0, 0.0, 0.5, CFG) == pytest.approx(0.0)
    # по формуле документа для лёгкого задания
    p0, p1 = p_correct(-0.4, -2.0), p_correct(0.4, -2.0)
    assert sprt.llr_increment(0.0, -2.0, 1.0, CFG) == pytest.approx(math.log(p1 / p0))
    assert sprt.llr_increment(0.0, -2.0, 0.0, CFG) == pytest.approx(math.log((1 - p1) / (1 - p0)))
    # y и 1 − y дают разницу ровно θ₁ − θ₀ = 0.8 (Rasch)
    for b in (-2.0, 0.0, 1.5):
        d = sprt.llr_increment(0.0, b, 1.0, CFG) - sprt.llr_increment(0.0, b, 0.0, CFG)
        assert d == pytest.approx(0.8)


def _decide(llr, n, theta=None, exhausted=False, cut=0.0):
    return sprt.decide(
        llr,
        n,
        min_items=CFG.min_items,
        max_items=CFG.max_items,
        exhausted=exhausted,
        theta=theta,
        cut=cut,
        cfg=CFG,
    )


def test_decide_min_max_and_bounds():
    assert CFG.min_items == 6 and CFG.max_items == 20
    # 6 верных у порога: 6·0.4 = 2.4 ≥ 2.197 → прошёл ровно на шестом
    assert _decide(5 * 0.4, 5) is None
    assert _decide(6 * 0.4, 6) == sprt.Decision("passed", False)
    assert _decide(-6 * 0.4, 6) == sprt.Decision("failed", False)
    assert _decide(9.0, 5) is None  # минимум 6 оцениваемых
    assert _decide(2.19, 10) is None and _decide(-2.19, 19, theta=0.1) is None
    # максимум: решение по EAP θ с пометкой «низкая уверенность»
    assert _decide(1.0, 20, theta=0.05) == sprt.Decision("passed", True)
    assert _decide(1.0, 20, theta=-0.05) == sprt.Decision("failed", True)
    assert _decide(0.0, 3, theta=-1.2, exhausted=True, cut=-1.0) == sprt.Decision("failed", True)
    with pytest.raises(ValueError):
        _decide(0.0, 20)


def test_bonus_eligibility_numbers():
    ok = sprt.Decision("passed", False)
    assert sprt.bonus_eligible(M, ok, 10, 0.5, CFG) == S  # ≤ 10 и θ ≥ 1.0 − 0.5
    assert sprt.bonus_eligible(M, ok, 10, 0.49, CFG) is None
    assert sprt.bonus_eligible(M, ok, 11, 2.0, CFG) is None
    assert sprt.bonus_eligible(J, ok, 6, -0.5, CFG) == M
    assert sprt.bonus_eligible(S, ok, 6, 3.0, CFG) is None  # выше Senior грейда нет
    assert sprt.bonus_eligible(M, sprt.Decision("failed", False), 6, 2.0, CFG) is None
    assert CFG.bonus_max_items == 6


# --- выбор задания (§6) -----------------------------------------------------------------------


def test_type_shares_table():
    assert sel.type_shares(J, CFG) == {
        "fundamental": 0.35,
        "hard": 0.40,
        "thinking": 0.10,
        "business": 0.05,
        "soft": 0.05,
        "experience": 0.05,
    }
    assert sel.type_shares(M, CFG)["thinking"] == 0.20
    assert sel.type_shares(S, CFG)["business"] == 0.15
    for g in TEST_GRADE_ORDER:
        shares = sel.type_shares(g, CFG)
        assert set(shares) == {t.value for t in SkillType}
        assert sum(shares.values()) == pytest.approx(1.0)


WEIGHTS = {"python": 1.0, "sql": 1.0, "algorithms": 1.0, "estimation": 1.0, "teamwork": 0.5}
TYPES = {
    "python": "hard",
    "sql": "hard",
    "algorithms": "fundamental",
    "estimation": "thinking",
    "teamwork": "soft",
}


def test_build_plan_shares():
    plan = {s.skill: s.share for s in sel.build_plan(WEIGHTS, TYPES, M, CFG)}
    # типы есть: hard .35, fundamental .25, thinking .20, soft .05 → сумма .85
    assert plan["python"] == pytest.approx(0.35 / 0.85 / 2)
    assert plan["algorithms"] == pytest.approx(0.25 / 0.85)
    assert plan["estimation"] == pytest.approx(0.20 / 0.85)
    assert plan["teamwork"] == pytest.approx(0.05 / 0.85)
    assert sum(plan.values()) == pytest.approx(1.0)
    # без заданий по навыку — навык выпадает, доли перераспределяются
    only = sel.build_plan(WEIGHTS, TYPES, M, CFG, available={"python", "algorithms"})
    assert {s.skill: s.share for s in only} == pytest.approx(
        {"python": 0.35 / 0.60, "algorithms": 0.25 / 0.60}
    )
    assert sel.build_plan(WEIGHTS, TYPES, M, CFG, available=set()) == []


def test_deficit_picks_largest_and_follows_shares():
    plan = sel.build_plan(WEIGHTS, TYPES, M, CFG)
    s = {x.skill: x for x in plan}
    assert sel.deficit(s["algorithms"], 0, 0) == pytest.approx(0.25 / 0.85)
    assert sel.deficit(s["algorithms"], 1, 2) == pytest.approx(0.25 / 0.85 * 3 - 1)
    issued: Counter[str] = Counter()
    for k in range(17):
        issued[sel.sections_by_deficit(plan, issued, k)[0].skill] += 1
    # за 17 шагов выдача следует долям плана с точностью до одного задания
    for x in plan:
        assert abs(issued[x.skill] - x.share * 17) <= 1


def test_item_score_numbers():
    assert sel.item_score(0.0, 0.0, 0.0, CFG) == pytest.approx(0.25)
    assert sel.item_score(0.0, 0.0, 1.0, CFG) == pytest.approx(0.25 * 0.7)
    assert sel.item_score(1.0, 1.0 + math.log(3), 0.0, CFG) == pytest.approx(0.25 * 0.75)
    assert sel.item_score(0.0, 0.0, 0.5, CFG) > sel.item_score(0.0, 1.0, 0.0, CFG)


def _cand(i, b, ai=0.0, n=0):
    return sel.Candidate(uuid.UUID(int=i), b, ai, n)


def test_choose_uniform_from_top3():
    cands = [_cand(1, 0.0), _cand(2, 0.1), _cand(3, -0.2), _cand(4, 1.5), _cand(5, -2.0, 0.0)]
    rng = Random(0)
    picks = Counter(sel.choose(cands, 0.0, rng, CFG).id.int for _ in range(3000))
    assert set(picks) == {1, 2, 3}
    assert all(800 < v < 1200 for v in picks.values())
    # ИИ-решаемое уходит из топа
    cands2 = [_cand(1, 0.0, 1.0), _cand(2, 0.3), _cand(3, -0.3), _cand(4, 0.5)]
    assert {sel.choose(cands2, 0.0, Random(i), CFG).id.int for i in range(200)} == {2, 3, 4}
    assert sel.choose([], 0.0, rng, CFG) is None


def test_pilot_rules():
    for seed in range(200):
        pos = sel.pilot_positions(Random(seed), CFG)
        assert len(pos) == 2 and pos[0] < pos[1]
        assert pos[0] >= 4  # после 3-го задания
        # обе позиции до того, как SPRT может остановиться (6 оцениваемых)
        assert pos[1] <= CFG.min_items + CFG.pilot_slots - 1
    cands = [_cand(1, 0, n=5), _cand(2, 0, n=2), _cand(3, 0, n=2), _cand(4, 0, n=9)]
    got = {sel.pick_pilot(cands, Random(i)).id.int for i in range(100)}
    assert got == {2, 3}  # наименьшее n, при равенстве случайно
    assert sel.pick_pilot([], Random(0)) is None


def test_level_window():
    assert [lv for lv in range(1, 6) if sel.level_ok(lv, M, CFG)] == [2, 3, 4]
    assert [lv for lv in range(1, 6) if sel.level_ok(lv, J, CFG)] == [1, 2, 3]
    assert [lv for lv in range(1, 6) if sel.level_ok(lv, S, CFG)] == [3, 4, 5]


# --- симуляция ---------------------------------------------------------------------------------


def _simulate(n_candidates: int, seed: int = 7):
    """Синтетика: θ ~ N(0, 1), заявленный грейд — случайный, банк 300 семейств с шумом b.

    Точность — доля верных решений (основной и бонусный этапы) вне зоны безразличия SPRT
    |θ − cut| > 0.4: там α = β = 0.1 гарантируют ≥ 90 %. Внутри зоны ошибка допустима по
    построению теста. Возвращает (точность вне зоны, точность всех решений, среднее заданий).
    """
    rng = Random(seed)
    bank = []
    for i in range(300):
        lv = rng.randint(1, 5)
        bank.append((_cand(i, CFG.prior_b(lv) + rng.gauss(0, 0.3), rng.random()), lv))

    def stage(theta, grade, r, used, obs, min_items, max_items):
        cut, llr, n = CFG.cuts[grade.value], 0.0, 0
        while True:
            cands = [c for c, lv in bank if c.id not in used and sel.level_ok(lv, grade, CFG)]
            need_theta = n >= max_items or not cands
            d = sprt.decide(
                llr,
                n,
                min_items=min_items,
                max_items=max_items,
                exhausted=not cands,
                theta=eap(obs, CFG).theta if need_theta else None,
                cut=cut,
                cfg=CFG,
            )
            if d is not None:
                return d, n
            c = sel.choose(cands, cut, r, CFG)
            used.add(c.id)
            y = 1.0 if r.random() < p_correct(theta, c.b) else 0.0
            llr += sprt.llr_increment(cut, c.b, y, CFG)
            obs.append(Observation(c.b, y))
            n += 1

    ok_zone = zone = ok_all = decisions = items = 0
    for i in range(n_candidates):
        r = Random(seed * 100_003 + i)
        theta = r.gauss(0.0, 1.0)
        grade = r.choice(TEST_GRADE_ORDER)
        used: set[uuid.UUID] = set()
        obs: list[Observation] = []
        d, n = stage(theta, grade, r, used, obs, CFG.min_items, CFG.max_items)
        results = [(grade, d)]
        total = n
        nxt = sprt.bonus_eligible(grade, d, n, eap(obs, CFG).theta, CFG)
        if nxt is not None:
            d2, n2 = stage(theta, nxt, r, used, obs, 0, CFG.bonus_max_items)
            results.append((nxt, d2))
            total += n2
        items += total
        for g, dec in results:
            cut = CFG.cuts[g.value]
            right = (dec.result == "passed") == (theta >= cut)
            decisions += 1
            ok_all += right
            if abs(theta - cut) > CFG.sprt_delta:
                zone += 1
                ok_zone += right
    return ok_zone / zone, ok_all / decisions, items / n_candidates


def test_simulation_accuracy_and_length():
    acc_zone, acc_all, mean_items = _simulate(400)
    assert acc_zone >= 0.90
    assert mean_items <= 14
    assert acc_all >= 0.80  # с зоной безразличия — для справки, держим от регресса


# --- через БД и API ----------------------------------------------------------------------------


class _Fake(BaseFamily):
    """Тестовое семейство: ответ «1» — верный."""

    kind = Kind.exact
    skill_type = SkillType.hard

    def __init__(self, slug: str, skill: str, level: int):
        self.slug, self.skill, self.level = slug, skill, level

    def generate(self, rng, world) -> Item:
        return Item(Kind.exact, f"{self.slug}: введите 1", "1")


_SKILLS = ["python", "sql", "algorithms", "estimation", "debugging"]


@pytest.fixture
def fake_bank(monkeypatch):
    reg = {}
    for skill in _SKILLS:
        for level in range(1, 6):
            for j in range(6):
                f = _Fake(f"t_{skill}_{level}_{j}", skill, level)
                reg[f.slug] = f
    monkeypatch.setattr(registry, "REGISTRY", reg)
    return reg


@pytest.fixture
async def taxonomy_loaded(factory):
    async with session_scope(factory) as s:
        await tax.sync(s, load_taxonomy(TAXONOMY))


def _start(api, h, grade="middle", profession="backend"):
    r = api.post(
        "/assessment/attempts", json={"profession": profession, "declared_grade": grade}, headers=h
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _run(api, h, aid, answer="1"):
    n = 0
    while True:
        body = api.get(f"/assessment/attempts/{aid}/next", headers=h).json()
        if body["done"]:
            return n
        r = api.post(
            f"/assessment/attempts/{aid}/answers",
            json={"response_id": body["response_id"], "answer": answer},
            headers=h,
        )
        assert r.status_code == 200, r.text
        n += 1
        assert n <= CFG.max_items + CFG.bonus_max_items + CFG.pilot_slots


async def _state(factory, aid):
    async with session_scope(factory) as s:
        att = await s.get(Attempt, uuid.UUID(aid))
        rows = await s.execute(
            select(Response, FamilyRow)
            .join(FamilyRow, FamilyRow.id == Response.family_id)
            .where(Response.attempt_id == att.id)
            .order_by(Response.seq)
        )
        return att, rows.all()


async def test_all_correct_passes_at_6_then_bonus_offers_upgrade(
    api, factory, taxonomy_loaded, fake_bank
):
    h = register(api)
    aid = _start(api, h)
    total = _run(api, h, aid)
    att, rows = await _state(factory, aid)
    assert att.status == "passed" and att.stage == "bonus"
    main, bonus = att.plan["main"], att.plan["bonus"]
    assert main == {"result": "passed", "low_confidence": False, "items": 6, "llr": main["llr"]}
    assert main["llr"] == pytest.approx(2.4)  # 6 × 0.4: все задания у порога (уровень 3, b = 0)
    assert bonus["grade"] == "senior" and bonus["result"] == "passed"
    assert bonus["from_seq"] == 6 and total == 12
    assert {f.level for r, f in rows[:6]} == {3} and {f.level for r, f in rows[6:]} == {4}
    assert len({f.id for _, f in rows}) == len(rows)  # семейства не повторяются
    out = api.get(f"/assessment/attempts/{aid}", headers=h).json()
    assert out["upgrade_offer"] == "senior" and out["low_confidence"] is False
    assert out["status"] == "passed" and out["stage"] == "bonus"
    # план основного этапа: секции по навыкам банка, первые 6 заданий — по дефициту
    assert {sec["skill"] for sec in att.plan["sections"]} == set(_SKILLS)
    assert att.theta is not None and att.theta > 1.0


async def test_all_wrong_fails_without_bonus(api, factory, taxonomy_loaded, fake_bank):
    h = register(api)
    aid = _start(api, h, grade="junior")
    assert _run(api, h, aid, answer="0") == 6
    att, rows = await _state(factory, aid)
    assert att.status == "failed" and att.stage == "main" and "bonus" not in att.plan
    assert att.llr == pytest.approx(-2.4)
    assert {f.level for _, f in rows} == {2}  # junior: b = cut = −1
    assert api.get(f"/assessment/attempts/{aid}", headers=h).json()["upgrade_offer"] is None


async def test_pilot_slots_hidden_and_without_effect(api, factory, taxonomy_loaded, fake_bank):
    async with session_scope(factory) as s:
        await attempts.sync_code_families(s, CFG)
        for r in await s.scalars(select(FamilyRow).where(FamilyRow.slug.like("t_sql_1_%"))):
            r.status = "pilot"
            r.n = 0 if r.slug.endswith("_0") or r.slug.endswith("_1") else 7
    h = register(api)
    aid = _start(api, h, grade="senior")
    _run(api, h, aid)
    att, rows = await _state(factory, aid)
    pilots = [(r, f) for r, f in rows if r.is_pilot]
    assert [r.seq for r, _ in pilots] == att.plan["pilot_seqs"]
    assert {f.slug for _, f in pilots} == {"t_sql_1_0", "t_sql_1_1"}  # наименьшее n
    assert all(f.status == "pilot" for _, f in pilots)
    assert att.plan["main"]["items"] == 6  # пилоты не считаются в оцениваемые
    scored = [f for r, f in rows if not r.is_pilot]
    expect = sum(sprt.llr_increment(1.0, CFG.prior_b(f.level), 1.0, CFG) for f in scored)
    assert att.plan["main"]["llr"] == pytest.approx(expect)
    # пилоты калибруются вместе с остальными
    assert all(f.n >= 1 for _, f in pilots)


async def test_small_bank_decides_by_eap_with_low_confidence(
    api, factory, taxonomy_loaded, monkeypatch
):
    reg = {f.slug: f for f in (_Fake(f"t_py_{j}", "python", 3) for j in range(3))}
    monkeypatch.setattr(registry, "REGISTRY", reg)
    h = register(api)
    aid = _start(api, h)
    assert _run(api, h, aid) == 3
    out = api.get(f"/assessment/attempts/{aid}", headers=h).json()
    att, _ = await _state(factory, aid)
    assert out["status"] == ("passed" if att.theta >= 0.0 else "failed")
    assert out["low_confidence"] is True and att.plan["main"]["items"] == 3


async def test_no_items_for_profession_is_503(api, taxonomy_loaded, monkeypatch):
    monkeypatch.setattr(registry, "REGISTRY", {"x": _Fake("t_x", "kotlin", 3)})
    r = api.post(
        "/assessment/attempts",
        json={"profession": "backend", "declared_grade": "middle"},
        headers=register(api),
    )
    assert r.status_code == 503 and r.json()["code"] == "no_items"


async def test_no_repeat_within_90_days(api, factory, taxonomy_loaded, fake_bank):
    h = register(api)
    first = _start(api, h)
    _run(api, h, first, answer="0")
    async with session_scope(factory) as s:  # E22-4: повтор грейда после неудачи — через 30 дней
        (await s.get(Attempt, uuid.UUID(first))).finished_at = datetime.now(UTC) - timedelta(
            days=31
        )
    second = _start(api, h)
    _run(api, h, second, answer="0")
    _, rows1 = await _state(factory, first)
    _, rows2 = await _state(factory, second)
    assert not {f.id for _, f in rows1} & {f.id for _, f in rows2}


async def test_exposure_filter(api, factory, taxonomy_loaded, fake_bank):
    cfg = dataclasses.replace(CFG, exposure_min_tests=3)
    aids = [uuid.UUID(_start(api, register(api))) for _ in range(4)]
    hot, warm = attempts.family_id("t_sql_3_0"), attempts.family_id("t_sql_3_1")
    async with session_scope(factory) as s:
        # 4 теста в окне: `hot` показан в двух (2/4 ≥ 0.3), `warm` — в одном (1/4 < 0.3)
        for i, (aid, fid) in enumerate([(aids[0], hot), (aids[1], hot), (aids[2], warm)]):
            s.add(Response(attempt_id=aid, seq=1, family_id=fid, seed=i))
        await s.flush()
        me = (await s.get(Attempt, aids[3])).candidate_id
        ids = {
            r.id for rows in (await engine.eligible(s, me, _SKILLS, M, cfg)).values() for r in rows
        }
        assert warm in ids and hot not in ids
        # пока тестов в окне меньше exposure_min_tests (20), экспозиция не проверяется
        loose = await engine.eligible(s, me, _SKILLS, M, CFG)
        assert hot in {r.id for rows in loose.values() for r in rows}
        # окно 7 дней: старые попытки не считаются
        old = datetime.now(UTC) - timedelta(days=8)
        for a in await s.scalars(select(Attempt)):
            a.started_at = old
        await s.flush()
        assert await engine._overexposed(s, datetime.now(UTC), cfg) == set()
