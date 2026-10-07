"""E16-2: подграф доказательств `GET /candidates/me/graph` и анонимный `/candidates/{id}/graph`."""

import asyncio
import uuid
from datetime import date

import pytest
from app.candidates.models import Candidate
from app.graph.fsp_models import FspCompetitionRow
from app.graph.models import CandidateSkill, Evidence
from app.taxonomy.models import Skill, SkillRelation
from app.vacancies.models import VacancySkill
from core_helpers import assert_foreign_is_404, register
from factories.base import make_vacancy
from fsp_platform.db import make_engine, make_session_factory, session_scope
from sqlalchemy import select, text

D = date(2026, 5, 1)
INN = "7707083893"


@pytest.fixture
def world(api):
    """Кандидат с тестом, ФСП-результатом, репозиторием, заявленным навыком; работодатель."""
    factory = make_session_factory(make_engine(f"sqlite+aiosqlite:///{api.db_path}"))
    cand_h = register(api, "candidate")
    api.get("/candidates/me/profile", headers=cand_h)  # создаёт анкету
    emp_h = register(api, "employer")
    co = api.post("/companies", json={"name": "Acme Labs", "inn": INN}, headers=emp_h).json()
    w: dict = {"cand": cand_h, "emp": emp_h, "factory": factory}

    async def seed():
        async with session_scope(factory) as s:
            c = (await s.scalars(select(Candidate))).one()
            c.primary_role, c.search_status, c.profile_version = "backend", "open", 12
            c.visibility = {"repos": False, "teams": True}
            await s.execute(text("update companies set status='verified'"))
            sk = {}
            for slug in ("python", "fastapi", "django", "teamwork"):
                sk[slug] = Skill(slug=slug, name=slug.title(), kind="hard", source="core")
                s.add(sk[slug])
            await s.flush()
            s.add(SkillRelation(skill_a=sk["fastapi"].id, skill_b=sk["python"].id, kind="parent",
                                weight=0.6, source="seed"))  # fmt: skip
            s.add(FspCompetitionRow(id="comp1", title="Кубок России", level="national",
                                    start_date=date(2025, 4, 10)))  # fmt: skip
            att, res, repo = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            rows = [
                ("python", "test", 0.5, "test_attempt", att,
                 {"profession": "backend", "grade": "middle", "secret": "x"}),
                ("fastapi", "fsp", 0.7, "fsp_result", res,
                 {"label": "Кубок России · 2 из 40", "competition_id": "comp1", "team_size": 4,
                  "teammates": ["Иван Иванов"]}),
                ("fastapi", "github", 0.5, "code_repo", repo, {"url": "https://x/repo"}),
                ("teamwork", "self", 0.15, "self", c.user_id, {}),
            ]  # fmt: skip
            for slug, src, st, ft, fid, det in rows:
                s.add(Evidence(candidate_id=c.user_id, skill_id=sk[slug].id, source=src,
                               strength=st, observed_at=D, fact_type=ft, fact_id=fid,
                               details=det))  # fmt: skip
            for slug, conf, lvl, claimed, src in [
                ("fastapi", 0.65, 3, False, ["fsp", "github"]),
                ("python", 0.54, 2, False, ["test"]),
                ("teamwork", 0.15, 1, True, ["self"]),
            ]:
                s.add(CandidateSkill(candidate_id=c.user_id, skill_id=sk[slug].id,
                                     confidence=conf, level=lvl, sources=src, top_evidence=[],
                                     claimed_only=claimed))  # fmt: skip
            company_id = uuid.UUID((await s.execute(text("select id from companies"))).scalar())
            from app.companies.models import Company

            vac = await make_vacancy(s, await s.get(Company, company_id))
            for slug in ("fastapi", "django"):
                s.add(VacancySkill(vacancy_id=vac.id, skill_id=sk[slug].id, required=True))
            w.update(pid=c.pseudo_id, vac=str(vac.id), att=str(att), co=co["id"])

    asyncio.run(seed())
    return w


def _h(w, k):
    return {"Authorization": w[k]["Authorization"]}


def test_owner_graph_includes_test_source(api, world):
    r = api.get("/candidates/me/graph", headers=_h(world, "cand"))
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["profile_version"] == 12
    by_id = {n["id"]: n for n in g["nodes"]}
    assert by_id["cand"]["type"] == "candidate"
    assert by_id[f"f:test:{world['att']}"]["label"] == "Тест: backend, middle"
    assert by_id["s:fastapi"]["level"] == 3 and by_id["s:python"]["confidence"] == 0.54
    confirms = [e for e in g["edges"] if e["type"] == "confirms"]
    assert {(e["from"], e["to"]) for e in confirms} >= {(f"f:test:{world['att']}", "s:python")}
    assert all(e["evidence_id"] and 0 <= e["strength"] <= 1 for e in confirms)
    assert {"from": "s:fastapi", "to": "s:python", "type": "parent", "weight": 0.6} in g["edges"]
    # заявленный навык без фактов — прямое ребро owns
    assert any(e["type"] == "owns" and e["to"] == "s:teamwork" for e in g["edges"])
    assert "secret" not in r.text


def test_depth_competitions_adds_competition_and_team(api, world):
    h = _h(world, "cand")
    base = api.get("/candidates/me/graph", headers=h).json()
    assert not [n for n in base["nodes"] if n["type"] in ("competition", "team")]
    g = api.get("/candidates/me/graph?depth=competitions", headers=h).json()
    types = {n["type"]: n for n in g["nodes"]}
    assert types["competition"]["label"] == "Кубок России"
    assert types["team"]["label"] == "Команда, 4 участн."
    assert {"at", "member_of"} <= {e["type"] for e in g["edges"]}


def test_skills_top_limits_nodes(api, world, monkeypatch):
    from app.graph import subgraph

    monkeypatch.setattr(subgraph, "TOP_SKILLS", 1)
    h = _h(world, "cand")
    top = api.get("/candidates/me/graph?skills=top", headers=h).json()
    assert [n["id"] for n in top["nodes"] if n["type"] == "skill"] == ["s:fastapi"]
    full = api.get("/candidates/me/graph?skills=all", headers=h).json()
    assert len([n for n in full["nodes"] if n["type"] == "skill"]) == 3


def test_employer_graph_is_anonymous(api, world):
    pid = world["pid"]
    r = api.get(f"/candidates/{pid}/graph?depth=competitions", headers=_h(world, "emp"))
    assert r.status_code == 200, r.text
    text_ = r.text
    for leak in ("Иван", "https://x/repo", "teammates", "url"):
        assert leak not in text_
    assert not [n for n in r.json()["nodes"] if n["type"] == "repo"]  # repos=false
    assert any(n["type"] == "team" for n in r.json()["nodes"])  # teams=true


def test_employer_teams_hidden_and_repos_shown_by_visibility(api, world):
    async def flip():
        async with session_scope(world["factory"]) as s:
            c = (await s.scalars(select(Candidate))).one()
            c.visibility = {"repos": True, "teams": False}

    asyncio.run(flip())
    g = api.get(f"/candidates/{world['pid']}/graph?depth=competitions", headers=_h(world, "emp"))
    nodes = g.json()["nodes"]
    assert any(n["type"] == "repo" and n["label"] == "Публичный репозиторий" for n in nodes)
    assert not [n for n in nodes if n["type"] in ("team", "competition")]


def test_highlight_for_vacancy_with_ghost(api, world):
    r = api.get(f"/candidates/{world['pid']}/graph?vacancy_id={world['vac']}",
                headers=_h(world, "emp"))  # fmt: skip
    assert r.status_code == 200, r.text
    g = r.json()
    hl = {h["requirement"]: h["path"] for h in g["highlight"]}
    assert hl["fastapi"][:3] == ["vac", "s:fastapi", "cand"] and hl["fastapi"][3].startswith("f:")
    assert hl["django"] == ["vac", "s:django"]
    ghost = next(n for n in g["nodes"] if n["id"] == "s:django")
    assert ghost["ghost"] is True and ghost["level"] == 0


def test_permissions_and_foreign_resources(api, world):
    pid = world["pid"]
    assert api.get("/candidates/me/graph").status_code == 401
    assert api.get("/candidates/me/graph", headers=_h(world, "emp")).status_code == 403
    assert api.get(f"/candidates/{pid}/graph", headers=_h(world, "cand")).status_code == 403
    # чужая вакансия и несуществующий кандидат → 404
    other = register(api, "employer")
    api.post("/companies", json={"name": "Other", "inn": "7736050003"}, headers=other)
    assert_foreign_is_404(api, "GET", f"/candidates/{pid}/graph?vacancy_id={world['vac']}", other)
    assert_foreign_is_404(api, "GET", "/candidates/nope/graph", _h(world, "emp"))


def test_hidden_candidate_is_404(api, world):
    async def hide():
        async with session_scope(world["factory"]) as s:
            (await s.scalars(select(Candidate))).one().search_status = "dnd"

    asyncio.run(hide())
    assert_foreign_is_404(api, "GET", f"/candidates/{world['pid']}/graph", _h(world, "emp"))


def test_minor_without_parent_consent_is_404(api, world):
    async def minor():
        async with session_scope(world["factory"]) as s:
            (await s.scalars(select(Candidate))).one().age_group = "minor"

    asyncio.run(minor())
    assert_foreign_is_404(api, "GET", f"/candidates/{world['pid']}/graph", _h(world, "emp"))


def test_graph_edges_view(api, world):
    import sqlite3

    with sqlite3.connect(api.db_path) as con:
        kinds = {r[0] for r in con.execute("select kind from graph_edges")}
        cols = [d[0] for d in con.execute("select * from graph_edges limit 1").description]
    assert cols == ["src_type", "src_id", "dst_type", "dst_id", "kind", "weight", "observed_at"]
    assert {"has_fact", "confirms", "owns", "parent", "requires"} <= kinds
