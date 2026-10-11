"""Рост связей: NPMI, веса ролей по lift, подсказки ФСП, кластеры, продвижение."""

import math
import uuid
from pathlib import Path

import pytest
from app.graph.fsp_models import FspResultRow
from app.graph.models import CandidateSkill
from app.taxonomy import growth
from app.taxonomy.models import (
    Discipline,
    Role,
    RoleSkill,
    ScoringConfig,
    Skill,
    SkillRelation,
)
from app.vacancies.models import Vacancy, VacancySkill
from core_helpers import upgrade_head
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import func, select
from tests.factories.base import make_candidate, make_company

CORE = Path(__file__).resolve().parents[1]


def test_npmi_formula():
    # p(a,b)=0.1, p(a)=p(b)=0.2: log(2.5) / -log(0.1)
    assert growth.npmi(10, 20, 20, 100) == pytest.approx(math.log(2.5) / math.log(10))
    assert growth.npmi(6, 6, 6, 10) == pytest.approx(1.0)  # всегда вместе
    assert growth.npmi(0, 5, 5, 10) == 0.0
    assert growth.npmi(10, 10, 10, 10) == 1.0  # p(a,b)=1


def test_edge_weight_and_cap():
    assert growth.edge_weight(0.3) == pytest.approx(0.55)
    assert growth.edge_weight(0.398) == pytest.approx(0.599, abs=1e-3)
    assert growth.edge_weight(1.0) == 0.9


def test_lift_and_role_weight():
    assert growth.lift(8, 10, 20, 100) == pytest.approx(4.0)
    assert growth.role_weight(4.0) == pytest.approx(0.4)  # 0.2·log2(4)
    assert growth.role_weight(16.0) == 0.8  # потолок
    assert growth.role_weight(1.0) == 0.0  # не лифт: связи нет


def test_strong_pairs_support_and_threshold():
    a, b, c = (uuid.uuid4() for _ in range(3))
    baskets = [{a, b}] * 5 + [{c}] * 5
    assert set(growth.strong_pairs(baskets)) == {tuple(sorted((a, b), key=str))}
    assert growth.strong_pairs([{a, b}] * 4 + [{c}] * 6) == {}  # поддержка 4 < 5


def test_clusters_min_size():
    a, b, c, d, e = (uuid.uuid4() for _ in range(5))
    pairs = {(a, b): 0.5, (b, c): 0.5, (d, e): 0.9}
    assert growth.clusters(pairs) == [{a, b, c}]


@pytest.fixture
def factory(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'g.db'}"
    upgrade_head(url)
    return make_session_factory(make_engine(url))


def _sk(slug: str, status: str = "active", source: str = "seed") -> Skill:
    return Skill(slug=slug, name=slug, kind="hard", status=status, source=source)


async def _owns(s, cid, sid, level=3):
    s.add(
        CandidateSkill(
            candidate_id=cid,
            skill_id=sid,
            confidence=0.7,
            level=level,
            sources=["github"],
            top_evidence=[],
            claimed_only=False,
        )
    )


async def _world(s):
    """10 кандидатов: 6 backend с {a, b}, 4 data с {c}; роль backend, дисциплина ИБ."""
    a, b, c, core = _sk("a"), _sk("b", "provisional", "pipeline"), _sk("c"), _sk("core")
    s.add_all([a, b, c, core, Role(slug="backend", name="B", is_profession=True)])
    s.add(Role(slug="data", name="D"))
    s.add(Discipline(slug="sec", name="ИБ"))
    await s.flush()
    s.add(RoleSkill(role="backend", skill_id=core.id, weight=0.9, source="seed"))
    cands = []
    for i in range(10):
        cand = await make_candidate(s, primary_role="backend" if i < 6 else "data")
        cands.append(cand)
        for sk in (a, b) if i < 6 else (c,):
            await _owns(s, cand.user_id, sk.id)
        if i < 6:
            await _owns(s, cand.user_id, c.id, level=1)  # ниже порога: в корзину не входит
    for cand in cands[:6]:
        s.add(
            FspResultRow(
                id=uuid.uuid4(),
                candidate_id=cand.user_id,
                participant_id=str(cand.user_id),
                competition_id="c1",
                stage="final",
                discipline="sec",
            )
        )
    await s.flush()
    return a, b, c, core


async def test_refresh_edges_roles_promotion(factory):
    async with session_scope(factory) as s:
        a, b, c, core = await _world(s)
        rep = await growth.refresh(s)
        assert rep.edges_added == 2  # a↔b в обе стороны
        edge = await s.get(SkillRelation, (a.id, b.id, "adjacent"))
        assert edge.source == "cooccurrence" and edge.weight == pytest.approx(0.9)
        assert await s.get(SkillRelation, (a.id, c.id, "adjacent")) is None
        assert rep.promoted == ["b"] and (await s.get(Skill, b.id)).status == "active"
        assert (await s.get(Skill, a.id)).support_candidates == 6
        rs = await s.get(RoleSkill, ("backend", a.id))
        assert rs.source == "data" and rs.weight == pytest.approx(0.2 * math.log2(10 / 6))
        assert await s.get(RoleSkill, ("backend", core.id)) is not None  # ядро цело
        assert await s.get(RoleSkill, ("backend", c.id)) is None  # c не у backend
        assert rep.version is not None
        events = await s.scalar(select(func.count()).select_from(OutboxRecord))
        assert events == 1


async def test_refresh_idempotent_and_keeps_foreign_edges(factory):
    async with session_scope(factory) as s:
        a, b, c, _ = await _world(s)
        s.add(
            SkillRelation(skill_a=a.id, skill_b=b.id, kind="adjacent", weight=0.5, source="admin")
        )
        await s.flush()
        first = await growth.refresh(s)
        assert (
            await s.get(SkillRelation, (a.id, b.id, "adjacent"))
        ).weight == 0.5  # админа не трогаем
        assert (await s.get(SkillRelation, (b.id, a.id, "adjacent"))).source == "cooccurrence"
        assert first.edges_added == 1
        second = await growth.refresh(s)
        assert (second.edges_added, second.edges_updated, second.edges_removed) == (0, 0, 0)
        assert second.role_skills == 0 and second.promoted == [] and second.version is None


async def test_refresh_removes_stale_cooccurrence_edge(factory):
    async with session_scope(factory) as s:
        a, b, c, _ = await _world(s)
        s.add_all(
            [
                SkillRelation(
                    skill_a=a.id, skill_b=c.id, kind="adjacent", weight=0.7, source="cooccurrence"
                ),
                SkillRelation(
                    skill_a=c.id, skill_b=a.id, kind="adjacent", weight=0.7, source="cooccurrence"
                ),
            ]
        )
        await s.flush()
        rep = await growth.refresh(s)
        assert rep.edges_removed == 2
        assert await s.get(SkillRelation, (a.id, c.id, "adjacent")) is None


async def test_vacancies_count_and_discipline_hints(factory):
    async with session_scope(factory) as s:
        a, b, c, _ = await _world(s)
        co, _owner = await make_company(s)
        for i in range(5):  # вакансии data с навыком c: поддержка роли data = 5
            v = Vacancy(
                company_id=co.id,
                title=f"V{i}",
                role="data",
                grade_min="middle",
                grade_max="middle",
                formats=["remote"],
                employment_type="full",
                salary_from=1,
                salary_to=2,
                status="published",
                important_qualities=[],
            )
            s.add(v)
            await s.flush()
            s.add(VacancySkill(vacancy_id=v.id, skill_id=c.id, required=True))
        await s.flush()
        rep = await growth.refresh(s)
        assert (await s.get(RoleSkill, ("data", c.id))).source == "data"
        assert (await s.get(Skill, c.id)).support_vacancies == 5
        # участников sec 6 (< 10): подсказок нет
        assert rep.discipline_hints == []
        cfg = await s.get(ScoringConfig, growth.HINTS_KEY)
        assert cfg.value["discipline_rules"] == []


async def test_discipline_hint_threshold(factory, monkeypatch):
    monkeypatch.setattr(growth, "HINT_SUPPORT", 5)
    async with session_scope(factory) as s:
        a, b, c, _ = await _world(s)
        rep = await growth.refresh(s)
        # p(a | sec)=1, p(a)=0.6: lift 1.67 < 2
        assert not any(h["skill"] == "a" for h in rep.discipline_hints)
        for _ in range(6):  # не участники sec: p(a)=6/16
            cand = await make_candidate(s, primary_role="data")
            await _owns(s, cand.user_id, c.id)
        await s.flush()
        rep = await growth.refresh(s)
        hint = next(h for h in rep.discipline_hints if h["skill"] == "a")
        assert hint["discipline"] == "sec" and hint["support"] == 6
        assert hint["lift"] == pytest.approx(1 / (6 / 16), abs=1e-3)
