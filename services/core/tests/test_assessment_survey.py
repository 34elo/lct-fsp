"""Опрос — сохранение, история, предзаполнение из резюме, права."""

import uuid
from pathlib import Path

import jwt
import pytest
from app.assessment import service as svc
from app.candidates.models import Candidate
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from core_helpers import register
from fsp_platform.db import session_scope

TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"
BODY = {
    "industry": "fintech",
    "profession": "backend",
    "stack": ["Python", "python", " SQL "],
    "formats": ["remote", "hybrid"],
    "salary_from": 200_000,
    "salary_to": 300_000,
    "declared_grade": "middle",
}


@pytest.fixture
async def taxonomy_loaded(factory):
    async with session_scope(factory) as s:
        await tax.sync(s, load_taxonomy(TAXONOMY))


def test_survey_save_history_and_dedup(api, taxonomy_loaded):
    h = register(api)
    assert api.get("/assessment/survey", headers=h).json()["prefilled"] is False
    r = api.put("/assessment/survey", json=BODY, headers=h)
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["stack"] == ["python", "sql"] and first["formats"] == ["hybrid", "remote"]
    assert api.get("/assessment/survey", headers=h).json()["id"] == first["id"]
    # тот же опрос — не новая строка; изменённый — новая
    assert api.put("/assessment/survey", json=BODY, headers=h).json()["id"] == first["id"]
    second = api.put("/assessment/survey", json={**BODY, "declared_grade": "senior"}, headers=h)
    assert second.json()["id"] != first["id"]
    hist = api.get("/assessment/history", headers=h).json()
    assert [s["declared_grade"] for s in hist["surveys"]] == ["senior", "middle"]
    assert hist["attempts"] == [] and hist["cooldowns"] == []
    assert api.get("/assessment/survey", headers=h).json()["declared_grade"] == "senior"


def test_survey_it_direction_without_industry(api, taxonomy_loaded):
    """Первый шаг — IT-направление (профессия), отрасль не обязательна."""
    h = register(api)
    body = {k: v for k, v in BODY.items() if k != "industry"}
    r = api.put("/assessment/survey", json=body, headers=h)
    assert r.status_code == 200, r.text
    assert (r.json()["profession"], r.json()["industry"]) == ("backend", None)
    r = api.put("/assessment/survey", json={"profession": "frontend"}, headers=h)
    assert r.status_code == 200 and r.json()["declared_grade"] is None


def test_survey_validation_and_isolation(api, taxonomy_loaded):
    h, other = register(api), register(api)
    r = api.put("/assessment/survey", json={**BODY, "profession": "nope"}, headers=h)
    assert (r.status_code, r.json()["code"]) == (422, "unknown_profession")
    r = api.put("/assessment/survey", json={**BODY, "salary_from": 9, "salary_to": 1}, headers=h)
    assert (r.status_code, r.json()["code"]) == (422, "invalid_salary_range")
    assert (
        api.put("/assessment/survey", json={**BODY, "formats": ["x"]}, headers=h).status_code == 422
    )
    api.put("/assessment/survey", json=BODY, headers=h)
    # чужих опросов не видно
    assert api.get("/assessment/survey", headers=other).json()["id"] is None
    assert api.get("/assessment/history", headers=other).json()["surveys"] == []
    assert api.get("/assessment/survey").status_code == 401


async def test_prefill_from_resume_and_claimed(api, factory, taxonomy_loaded):
    h = register(api)
    uid = uuid.UUID(jwt.decode(h["Authorization"][7:], options={"verify_signature": False})["sub"])
    api.get("/assessment/survey", headers=h)
    async with session_scope(factory) as s:
        cand = await s.get(Candidate, uid)
        if cand is None:
            from app.candidates import service as cands

            cand = await cands.get_or_create(s, uid, "secret")
        cand.primary_role, cand.grade, cand.salary_min = "backend", "middle", 150_000
        cand.formats, cand.primary_stack = ["remote", "bogus"], ["python"]
    d = api.get("/assessment/survey", headers=h).json()
    assert d["prefilled"] is True and d["id"] is None
    assert (d["profession"], d["declared_grade"], d["salary_from"]) == (
        "backend",
        "middle",
        150_000,
    )
    assert d["formats"] == ["remote"] and d["stack"] == ["python"]
    # опрос попадает в «заявлено против подтверждённого»
    api.put("/assessment/survey", json={**BODY, "declared_grade": "senior"}, headers=h)
    async with session_scope(factory) as s:
        await svc.seed_grade(s, uid, "backend", "middle", 0.5)
    async with session_scope(factory) as s:
        (r,) = await svc.claimed_vs_confirmed(s, uid)
    assert (r.declared_grade, r.status) == ("senior", "overclaimed")
    # то же самое видит владелец в профиле
    async with session_scope(factory) as s:
        (await s.get(Candidate, uid)).formats = ["remote"]  # профиль не принимает «bogus»
    cvc = api.get("/candidates/me/profile", headers=h).json()["claimed_vs_confirmed"]
    assert [
        (x["profession"], x["declared_grade"], x["confirmed_grade"], x["status"]) for x in cvc
    ] == [("backend", "senior", "middle", "overclaimed")]
    hist = api.get("/assessment/history", headers=h).json()
    assert hist["cooldowns"][0]["profession"] == "backend"


async def test_survey_analytics_event_once_without_pii(api, factory, taxonomy_loaded):
    """`survey_saved` пишется один раз на изменение, без стека и вилки."""
    from app.analytics.models import AnalyticsEventRow
    from sqlalchemy import select

    h = register(api)
    assert api.put("/assessment/survey", json=BODY, headers=h).status_code == 200
    api.put("/assessment/survey", json=BODY, headers=h)  # повтор без изменений
    async with session_scope(factory) as s:
        rows = list(
            await s.scalars(
                select(AnalyticsEventRow).where(AnalyticsEventRow.event == "survey_saved")
            )
        )
    assert len(rows) == 1
    assert rows[0].props == {
        "profession": "backend",
        "declared_grade": "middle",
        "stack_size": 2,
        "formats_count": 2,
        "has_salary": True,
    }
    assert rows[0].actor.startswith("a_") and rows[0].role == "candidate"
