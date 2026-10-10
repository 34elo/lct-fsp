"""E41-17: система предлагает новые профессии — кластеризация, хранение решений, админка."""

import sqlite3
import uuid
from pathlib import Path

import pytest
from app.matching.models import Need
from app.taxonomy import profession_suggest as ps
from app.taxonomy import service
from app.taxonomy.loader import load_taxonomy
from app.taxonomy.models import ProfessionSuggestion, RoleSkill, Skill
from app.vacancies.models import Vacancy, VacancySkill
from core_helpers import PASSWORD, register
from fsp_contracts.assessment import SkillType
from fsp_platform.db import session_scope
from sqlalchemy import func, select
from tests.factories.base import make_company

TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"
ONE_C = frozenset({"1c", "mssql", "xml_json", "sql"})
WEB = frozenset({"python", "fastapi", "docker"})


# --- чистая часть: синтетика -------------------------------------------------------------------


def _vac(skills, title):
    return ps.Basket(frozenset(skills), uuid.uuid4(), title)


def _synthetic() -> list[ps.Basket]:
    ones = [
        _vac(ONE_C, "Senior программист 1С"),
        _vac(ONE_C, "Программист 1С (ERP)"),
        _vac(ONE_C - {"sql"}, "Программист 1С"),
        _vac(ONE_C, "Разработчик 1С"),
    ]
    web = [_vac(WEB | {"sql"}, f"Backend {i}") for i in range(4)]
    noise = [_vac({"figma"}, "Дизайнер"), _vac({"excel", "sql"}, "Аналитик")]
    return [*ones, *web, *noise, ps.Basket(ONE_C)]  # последняя — запрос работодателя


PROFS = {"backend": {"python", "fastapi", "docker", "sql", "postgresql"}, "designer": {"figma"}}


def test_mine_finds_uncovered_cluster_only():
    # web покрыт backend (overlap 1.0), а SQL встречается везде (низкий NPMI) — не в ядре
    (c,) = ps.mine(_synthetic(), PROFS)
    assert set(c.skills) == ONE_C - {"sql"}
    assert (c.support_vacancies, c.support_needs) == (4, 1)
    assert c.nearest is None and c.overlap == 0.0
    assert c.title == "Программист 1С"  # самое частое очищенное название
    assert c.shares["1c"] == 1.0 and c.key == "1c,mssql,xml_json"
    assert len(c.examples) == 3 and all(e["vacancy_id"] for e in c.examples)


def test_mine_thresholds_support_and_overlap():
    few = [_vac(ONE_C, "1С") for _ in range(2)] + [_vac(WEB, "B") for _ in range(4)]
    assert ps.mine(few, PROFS) == []  # пары встречаются 2 раза < 3
    near = {**PROFS, "erp": {"1c", "mssql", "xml_json"}}
    assert ps.mine(_synthetic(), near) == []  # ближайшая профессия покрывает 3/4 > 0.5


def test_mine_is_deterministic():
    data = _synthetic()
    assert ps.mine(data, PROFS) == ps.mine(list(reversed(data)), PROFS)


def test_title_and_weight_formulas():
    assert ps.clean_title("Senior программист 1С (ERP)") == "Программист 1С"
    assert ps.clean_title("Middle+ 1С-разработчик") == "1С-разработчик"
    assert ps.candidate_title([]) is None
    assert ps.core_weight(0.0) == 0.5 and ps.core_weight(0.8) == 0.9 and ps.core_weight(1) == 1.0
    assert ps.jaccard(["a", "b", "c"], ["a", "b", "d"]) == pytest.approx(0.5)
    assert ps.nearest_profession({"a", "b"}, {"x": {"a"}, "y": {"a", "b"}}) == ("y", 1.0)


# --- БД: майнинг, решения, админка -------------------------------------------------------------


@pytest.fixture
async def seeded(factory):
    async with session_scope(factory) as s:
        await service.sync(s, load_taxonomy(TAXONOMY))


async def _market(factory, extra_titles=()):
    """4 вакансии 1С + 4 backend + запрос работодателя с ядром 1С."""
    async with session_scope(factory) as s:
        ids = dict((await s.execute(select(Skill.slug, Skill.id))).all())
        co, _ = await make_company(s)
        titles = [
            "Senior программист 1С",
            "Программист 1С (ERP)",
            "Программист 1С",
            "Разработчик 1С",
            *extra_titles,
        ]
        rows = [(t, ONE_C) for t in titles] + [(f"Backend {i}", WEB) for i in range(4)]
        for title, skills in rows:
            v = Vacancy(
                company_id=co.id, title=title, role="backend", grade_min="middle",
                grade_max="middle", formats=["remote"], employment_type="full",
                salary_from=1, salary_to=2, status="published", important_qualities=[],
            )  # fmt: skip
            s.add(v)
            await s.flush()
            for slug in skills:
                s.add(VacancySkill(vacancy_id=v.id, skill_id=ids[slug], required=True))
        s.add(Need(company_id=co.id, filters={}, weights=dict.fromkeys(ONE_C, 1.0), grades=[]))


async def test_refresh_creates_updates_and_is_idempotent(factory, seeded):
    await _market(factory)
    async with session_scope(factory) as s:
        assert (await ps.refresh(s))["added"] == 1
    async with session_scope(factory) as s:
        rep = await ps.refresh(s)
        assert rep == {"added": 0, "updated": 1, "skipped": 0, "removed": 0}
        (row,) = await ps.list_open(s)
        assert set(row.skills) == ONE_C and row.title == "Программист 1С"
        assert (row.support_vacancies, row.support_needs) == (4, 1)
        assert row.nearest_profession is not None and row.nearest_overlap <= ps.MAX_OVERLAP


async def test_rejected_is_remembered_and_stale_removed(factory, seeded):
    await _market(factory)
    async with session_scope(factory) as s:
        await ps.refresh(s)
        (row,) = await ps.list_open(s)
        await ps.reject(s, row.id, None)
    await _market(factory, extra_titles=("Ведущий программист 1С",))  # рынок вырос
    async with session_scope(factory) as s:
        rep = await ps.refresh(s)
        assert rep["skipped"] == 1 and rep["added"] == 0
        assert await ps.list_open(s) == []
        # открытое предложение майнинга без кластера удаляется, сидовое остаётся
        s.add(ProfessionSuggestion(key="a,b,c", title="X", skills=["a", "b", "c"], weights={},
                                   examples=[]))  # fmt: skip
        await ps.seed(
            s, title="Демо", skills=["rust", "haskell", "elixir"], examples=[],
            support_vacancies=3, support_needs=0,
        )  # fmt: skip
        await s.flush()
        await ps.refresh(s)
        assert [r.title for r in await ps.list_open(s)] == ["Демо"]


def _admin(api) -> dict[str, str]:
    email = f"root-{uuid.uuid4().hex[:6]}@example.test"
    r = api.post("/auth/register", json={"email": email, "password": PASSWORD, "role": "candidate"})
    with sqlite3.connect(api.db_path) as con:
        con.execute("update users set role='fsp_admin' where email=?", (email,))
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_admin_roles_required(api, factory, seeded):
    cand = register(api)
    sid = uuid.uuid4()
    for method, url in [
        ("get", "/admin/profession-suggestions"),
        ("post", f"/admin/profession-suggestions/{sid}/accept"),
        ("post", f"/admin/profession-suggestions/{sid}/reject"),
    ]:
        assert getattr(api, method)(url).status_code == 401
        assert getattr(api, method)(url, headers=cand).status_code == 403
    adm = _admin(api)
    assert api.post(f"/admin/profession-suggestions/{sid}/accept", headers=adm).status_code == 404


async def test_admin_accept_one_click_and_reject(api, factory, seeded):
    await _market(factory)
    async with session_scope(factory) as s:
        await ps.refresh(s)
        await ps.seed(
            s, title="Демо", skills=["rust", "haskell", "elixir"], examples=[],
            support_vacancies=1, support_needs=0,
        )  # fmt: skip
    adm = _admin(api)
    items = api.get("/admin/profession-suggestions", headers=adm).json()
    assert [i["title"] for i in items] == ["Программист 1С", "Демо"]
    first = items[0]
    assert {sk["slug"] for sk in first["skills"]} == ONE_C
    assert first["skills"][0]["name"] and first["nearest"]["title"]
    assert len(first["examples"]) == 3 and first["status"] == "open"

    r = api.post(f"/admin/profession-suggestions/{first['id']}/accept", headers=adm)
    assert r.status_code == 201, r.text
    body = r.json()
    prof = body["profession"]
    assert body["suggestion"]["status"] == "created"
    assert body["suggestion"]["profession"] == prof["slug"] == "p_1c_mssql"  # из ядра навыков
    assert prof["title"] == "Программист 1С" and prof["taxonomy_version"]
    assert ONE_C <= set(prof["skill_weights"])
    profs = {p["slug"] for p in api.get("/admin/professions", headers=adm).json()}
    assert prof["slug"] in profs
    async with session_scope(factory) as s:  # профиль покрывает все шесть типов навыков
        types = set(
            await s.scalars(
                select(Skill.skill_type)
                .join(RoleSkill, RoleSkill.skill_id == Skill.id)
                .where(RoleSkill.role == prof["slug"])
            )
        )
        assert types >= {t.value for t in SkillType}
    again = api.post(f"/admin/profession-suggestions/{first['id']}/accept", headers=adm)
    assert again.status_code == 409 and again.json()["code"] == "suggestion_decided"

    r = api.post(f"/admin/profession-suggestions/{items[1]['id']}/reject", headers=adm)
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert api.get("/admin/profession-suggestions", headers=adm).json() == []
    async with session_scope(factory) as s:  # принятое не предлагается снова
        await ps.refresh(s)
        assert await ps.list_open(s) == []
        assert await s.scalar(select(func.count()).select_from(ProfessionSuggestion)) == 2


async def test_weekly_command_via_consumer_and_redelivery(factory, seeded):
    """`taxonomy.professions.suggest` из scheduler → предложение; повтор того же конверта — без
    эффекта, повтор новой командой — без новых строк."""
    from fsp_contracts.commands import COMMANDS
    from fsp_contracts.registry import new_command
    from fsp_platform.messaging import QUEUES, Consumer

    await _market(factory)
    consumers = {"core.jobs": Consumer(QUEUES["core.jobs"])}
    ps.register(consumers, factory)
    cmd = "taxonomy.professions.suggest"
    envelope, _ = new_command(cmd, "core-scheduler", COMMANDS[cmd].model())
    await consumers["core.jobs"].dispatch(envelope)
    await consumers["core.jobs"].dispatch(envelope)
    again, _ = new_command(cmd, "core-scheduler", COMMANDS[cmd].model())
    await consumers["core.jobs"].dispatch(again)
    async with session_scope(factory) as s:
        assert await s.scalar(select(func.count()).select_from(ProfessionSuggestion)) == 1
