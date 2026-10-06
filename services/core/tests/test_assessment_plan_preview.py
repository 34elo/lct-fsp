"""E22-5: план теста из профессии или вакансии, `POST /assessment/plan/preview` (§6)."""

from pathlib import Path

import pytest
from app.assessment import plan_preview
from app.assessment import selection as sel
from app.assessment.config import load_config
from app.identity.service import make_access
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from app.vacancies.models import VacancySkill
from core_helpers import assert_foreign_is_404, register
from factories.base import make_company, make_vacancy
from fsp_contracts.assessment import TestGrade
from fsp_platform.db import session_scope
from sqlalchemy import select

CFG = load_config()
TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"
URL = "/assessment/plan/preview"


@pytest.fixture
async def taxonomy_loaded(factory):
    async with session_scope(factory) as s:
        await tax.sync(s, load_taxonomy(TAXONOMY))


def test_grade_mapping_and_vacancy_weights():
    assert plan_preview.to_test_grade("lead") is TestGrade.senior
    assert plan_preview.to_test_grade("intern") is TestGrade.junior
    assert plan_preview.to_test_grade(None) is TestGrade.middle
    w = plan_preview.vacancy_weights([(1.0, True, "python"), (1.0, False, "sql"), (0.0, True, "x")])
    assert w == {"python": 1.0, "sql": 0.5}


def test_preview_sums_to_one_and_grade_shifts_shares():
    weights = {"python": 1.0, "algorithms": 1.0, "system_design": 1.0}
    types = {"python": "hard", "algorithms": "fundamental", "system_design": "thinking"}
    shares = {}
    for g in (TestGrade.junior, TestGrade.senior):
        out = plan_preview.preview(weights, types, g, CFG)
        assert sum(s["share"] for s in out["sections"]) == pytest.approx(1.0, abs=1e-5)
        shares[g] = {s["skill"]: s["share"] for s in out["sections"]}
        assert out["type_shares"].keys() == {"hard", "fundamental", "thinking"}
    # мышление весит больше у senior, чем у junior (§6)
    assert shares[TestGrade.senior]["system_design"] > shares[TestGrade.junior]["system_design"]
    assert sel.type_shares(TestGrade.junior, CFG)["hard"] == pytest.approx(0.40)


async def _vacancy(api, factory, skills, grade_min="middle"):
    """Вакансия компании с владельцем; возвращает `(vacancy_id, заголовок владельца)`."""
    async with session_scope(factory) as s:
        company, owner = await make_company(s)
        vac = await make_vacancy(s, company, grade_min=grade_min)
        ids = await tax.resolve_slugs(s, [slug for slug, *_ in skills])
        for slug, weight, required in skills:
            s.add(
                VacancySkill(
                    vacancy_id=vac.id, skill_id=ids[slug], required=required, weight=weight
                )
            )
        await s.flush()
        token = make_access(api.app.state.settings.jwt_secret, owner)
        return vac.id, {"Authorization": f"Bearer {token}"}


async def test_profession_and_skills_sources(api, taxonomy_loaded):
    h = register(api)
    body = api.post(URL, json={"profession": "backend", "grade": "senior"}, headers=h).json()
    assert body["source"] == "profession" and body["grade"] == "senior"
    assert sum(s["share"] for s in body["sections"]) == pytest.approx(1.0, abs=1e-4)
    assert len(body["examples"]) == 3
    for ex in body["examples"]:
        assert "key" not in ex and ex["stem"]
    again = api.post(URL, json={"profession": "backend", "grade": "senior"}, headers=h).json()
    assert again == body  # детерминизм

    r = api.post(URL, json={"skills": ["python", "no_such_skill"]}, headers=h)
    assert r.status_code == 200 and r.json()["ignored"] == ["no_such_skill"]
    assert r.json()["grade"] == "middle"

    assert api.post(URL, json={"profession": "nope"}, headers=h).status_code == 422
    assert api.post(URL, json={}, headers=h).status_code == 422
    both = {"profession": "backend", "skills": ["python"]}
    assert api.post(URL, json=both, headers=h).status_code == 422
    empty = api.post(URL, json={"skills": ["no_such_skill"]}, headers=h)
    assert empty.status_code == 422 and empty.json()["code"] == "empty_plan"
    assert api.post(URL, json={"profession": "backend"}).status_code == 401


async def test_vacancies_give_different_plans_and_foreign_is_404(api, factory, taxonomy_loaded):
    async with session_scope(factory) as s:
        from app.taxonomy.models import Skill

        slugs = list(
            await s.scalars(
                select(Skill.slug)
                .where(Skill.skill_type == "hard", Skill.status == "active")
                .order_by(Skill.slug)
            )
        )
    assert len(slugs) >= 4
    specs = [
        [(slugs[0], 1.0, True), (slugs[1], 0.6, False)],
        [(slugs[1], 1.0, True), (slugs[2], 1.0, True), (slugs[3], 0.3, False)],
        [(slugs[3], 1.0, True)],
    ]
    plans = []
    for sk in specs:
        vid, owner = await _vacancy(api, factory, sk)
        r = api.post(URL, json={"vacancy_id": str(vid)}, headers=owner)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["source"] == "vacancy" and body["grade"] == "middle"
        assert {s["skill"] for s in body["sections"]} == {x[0] for x in sk}
        plans.append(tuple((s["skill"], s["share"]) for s in body["sections"]))
        assert_foreign_is_404(
            api, "POST", URL, register(api, "employer"), json={"vacancy_id": str(vid)}
        )
        assert (
            api.post(URL, json={"vacancy_id": str(vid)}, headers=register(api)).status_code == 403
        )
    assert len(set(plans)) == 3
