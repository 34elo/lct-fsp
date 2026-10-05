"""E22-2: психометрия — Rasch, EAP и SE, θ по типам, частичный балл, калибровка, якоря.

Числа — из assessment.md §5 и §7.
"""

import math
import uuid
from pathlib import Path
from random import Random

import pytest
from app.assessment import attempts
from app.assessment import families as registry
from app.assessment.config import load_config
from app.assessment.models import Attempt, FamilyRow, Response
from app.assessment.psychometrics import (
    Observation,
    calibrate_b,
    calibration_k,
    eap,
    grid,
    log_likelihood,
    p_correct,
    theta_by_type,
)
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from core_helpers import register
from fsp_platform.db import session_scope
from sqlalchemy import select

CFG = load_config()
TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"


# --- Rasch и частичный балл ------------------------------------------------------------------


def test_rasch_numbers():
    assert p_correct(0.0, 0.0) == 0.5
    assert p_correct(1.0, 0.0) == pytest.approx(0.731059, abs=1e-6)
    assert p_correct(-1.0, 0.0) == pytest.approx(0.268941, abs=1e-6)
    assert p_correct(0.4, 0.0) == pytest.approx(1 / (1 + math.exp(-0.4)))
    assert p_correct(-800.0, 0.0) == pytest.approx(0.0) and p_correct(800.0, 0.0) == 1.0


def test_prior_b_by_level_from_config():
    assert CFG.b_by_level == {1: -2.0, 2: -1.0, 3: 0.0, 4: 1.0, 5: 2.0}
    assert CFG.cuts == {"junior": -1.0, "middle": 0.0, "senior": 1.0}


def test_partial_score_is_fractional_outcome():
    # y = 0.5 при θ = b: ln L = 0.5·ln 0.5 + 0.5·ln 0.5 = ln 0.5
    assert log_likelihood(0.0, [Observation(0.0, 0.5)]) == pytest.approx(math.log(0.5))
    # частичный балл лежит между верным и неверным
    full = eap([Observation(0.0, 1.0)], CFG).theta
    half = eap([Observation(0.0, 0.5)], CFG).theta
    zero = eap([Observation(0.0, 0.0)], CFG).theta
    assert zero < half < full
    assert half == pytest.approx(0.0, abs=1e-9)


# --- EAP и SE --------------------------------------------------------------------------------


def test_grid_minus4_to_4_step_01():
    g = grid(CFG)
    assert len(g) == 81 and g[0] == -4.0 and g[-1] == 4.0 and g[40] == 0.0


def test_eap_without_answers_is_prior():
    est = eap([], CFG)
    assert est.theta == pytest.approx(0.0, abs=1e-9)
    assert est.se == pytest.approx(1.0, abs=0.01)  # N(0, 1), усечённое [−4, 4]
    assert est.n == 0


def test_eap_symmetry_and_se_shrinks():
    up = eap([Observation(0.0, 1.0)], CFG)
    down = eap([Observation(0.0, 0.0)], CFG)
    assert up.theta > 0 and down.theta == pytest.approx(-up.theta)
    assert up.se < 1.0
    many = eap([Observation(b, s) for b in (-1, 0, 1) for s in (1.0, 0.0)] * 3, CFG)
    assert many.theta == pytest.approx(0.0, abs=1e-9) and many.se < up.se


def test_eap_monotone_in_score():
    bs = [-2.0, -1.0, 0.0, 1.0, 2.0]
    thetas = [
        eap([Observation(b, 1.0 if i < k else 0.0) for i, b in enumerate(bs)], CFG).theta
        for k in range(6)
    ]
    assert thetas == sorted(thetas) and len(set(thetas)) == 6


def test_theta_by_type_uses_only_own_answers():
    obs = [
        Observation(0.0, 1.0, "hard"),
        Observation(1.0, 1.0, "hard"),
        Observation(0.0, 0.0, "thinking"),
        Observation(0.0, 1.0, None),
    ]
    by = theta_by_type(obs, CFG)
    assert set(by) == {"hard", "thinking"}
    assert by["hard"] == pytest.approx(eap(obs[:2], CFG).theta)
    assert by["thinking"] == pytest.approx(eap(obs[2:3], CFG).theta) and by["thinking"] < 0


def test_synthetic_recovery_r_at_least_085():
    """Синтетика: 20 заданий у порогов, 500 кандидатов θ ~ N(0, 1) → r(θ̂, θ) ≥ 0.85."""
    rng = Random(2026)
    bs = [CFG.prior_b(1 + i % 5) + rng.uniform(-0.5, 0.5) for i in range(20)]
    true, est = [], []
    for _ in range(500):
        t = rng.gauss(0.0, 1.0)
        obs = [Observation(b, 1.0 if rng.random() < p_correct(t, b) else 0.0) for b in bs]
        true.append(t)
        est.append(eap(obs, CFG).theta)
    mt, me = sum(true) / len(true), sum(est) / len(est)
    cov = sum((a - mt) * (b - me) for a, b in zip(true, est, strict=True))
    r = cov / math.sqrt(sum((a - mt) ** 2 for a in true) * sum((b - me) ** 2 for b in est))
    assert r >= 0.85, r


# --- калибровка и якоря ----------------------------------------------------------------------


def test_calibration_k_numbers():
    assert calibration_k(0, CFG) == pytest.approx(0.5)
    assert calibration_k(3, CFG) == pytest.approx(0.25)
    assert calibration_k(99, CFG) == pytest.approx(0.05)
    assert calibration_k(1000, CFG) == pytest.approx(0.05)  # 0.0158 → нижняя граница 0.05
    assert calibration_k(0, CFG, anchor=True) == 0.0


def test_calibrate_b_numbers():
    # b = 0, n = 0, θ = 0: P = 0.5; K = 0.5
    assert calibrate_b(0.0, 0, 0.0, 1.0, CFG) == pytest.approx(-0.25)  # верно → легче
    assert calibrate_b(0.0, 0, 0.0, 0.0, CFG) == pytest.approx(0.25)  # неверно → сложнее
    assert calibrate_b(0.0, 0, 0.0, 0.5, CFG) == pytest.approx(0.0)
    # b = 1, n = 3 (K = 0.25), θ = 1, y = 1 → 1 + 0.25·(0.5 − 1) = 0.875
    assert calibrate_b(1.0, 3, 1.0, 1.0, CFG) == pytest.approx(0.875)
    assert calibrate_b(1.0, 0, -2.0, 1.0, CFG, anchor=True) == 1.0


def test_calibration_converges_to_true_b():
    rng = Random(7)
    true_b, b = 1.2, CFG.prior_b(3)
    for n in range(2000):
        t = rng.gauss(0.0, 1.0)
        y = 1.0 if rng.random() < p_correct(t, true_b) else 0.0
        b = calibrate_b(b, n, t, y, CFG)
    assert abs(b - true_b) < 0.3, b


# --- попытка: θ, SE, θ по типам и калибровка при завершении ----------------------------------


@pytest.fixture
async def taxonomy_loaded(factory):
    async with session_scope(factory) as s:
        await tax.sync(s, load_taxonomy(TAXONOMY))


async def _key(factory, response_id: str):
    async with session_scope(factory) as s:
        resp = await s.get(Response, uuid.UUID(response_id))
        att = await s.get(Attempt, resp.attempt_id)
        row = await s.get(FamilyRow, resp.family_id)
    return attempts.build_item(registry.get(row.slug), resp.seed, att.plan["domain"]).key


async def test_finished_attempt_has_theta_and_calibrates_bank(api, factory, taxonomy_loaded):
    h = register(api)
    r = api.post(
        "/assessment/attempts",
        json={"profession": "backend", "declared_grade": "middle"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    async with session_scope(factory) as s:
        rows = {f.id: f for f in await s.scalars(select(FamilyRow))}
        anchor_id = sorted(rows)[0]
        rows[anchor_id].anchor = True
        before = {fid: (f.b, f.n) for fid, f in rows.items()}

    last = None
    while True:
        body = api.get(f"/assessment/attempts/{aid}/next", headers=h).json()
        if body["done"]:
            break
        last = {
            "response_id": body["response_id"],
            "answer": await _key(factory, body["response_id"]),
        }
        assert (
            api.post(f"/assessment/attempts/{aid}/answers", json=last, headers=h).status_code == 200
        )
    # повторная доставка ответа после завершения не калибрует второй раз
    assert api.post(f"/assessment/attempts/{aid}/answers", json=last, headers=h).status_code == 200

    async with session_scope(factory) as s:
        att = await s.get(Attempt, uuid.UUID(aid))
        assert att.theta is not None and att.theta > 0  # все ответы верные
        assert att.se is not None and 0 < att.se < 1
        by_type = att.plan["theta_by_type"]
        answered = list(await s.scalars(select(Response).where(Response.attempt_id == att.id)))
        types = {(await s.get(FamilyRow, a.family_id)).skill_type for a in answered}
        assert set(by_type) == types
        for a in answered:
            fam = await s.get(FamilyRow, a.family_id)
            b0, n0 = before[fam.id]
            assert fam.n == n0 + 1
            if fam.anchor:
                assert fam.b == b0  # якорь держит шкалу
            else:
                assert fam.b == pytest.approx(calibrate_b(b0, n0, att.theta, 1.0, CFG))
                assert fam.b < b0
