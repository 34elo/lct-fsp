"""Категория: роли, мульти-метки, стек, объяснение (ml.md §4)."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.candidates.models import Candidate
from app.graph import service
from app.graph.category import (
    CategoryConfig,
    SkillConf,
    compute_category,
    load_category,
    role_score,
)
from app.graph.recompute import recompute_profile
from app.graph.service import EvidenceIn
from app.graph.trust import TrustConfig
from app.identity.models import User
from app.taxonomy import service as tax
from app.taxonomy.loader import load_taxonomy
from core_helpers import upgrade_head
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import select

CORE = Path(__file__).resolve().parents[1]
DATA = load_taxonomy(CORE.parents[1] / "data" / "taxonomy")
CFG = TrustConfig.load()
CAT = CFG.category
NOW = datetime(2026, 6, 1, 12, tzinfo=UTC)
ROLES = {r.slug: r.skills for r in DATA.roles}
LANGS = {s.slug for s in DATA.skills if s.group == "language"}
STACK = LANGS | {p.child for p in DATA.parent if p.parent in LANGS}


def _s(**conf: float) -> dict[str, SkillConf]:
    return {
        k.replace("_", "-") if k == "spring_boot" else k: SkillConf(
            v, int(v * 5) - (v == 1), ("github",)
        )
        for k, v in conf.items()
    }


def test_config_loaded_from_scoring_yaml():
    assert CAT == CategoryConfig(8, 0.6, 0.05, 0.5, 0.15, 3, 5)


def test_role_score_normalised_by_top_k():
    w = {f"s{i}": 1.0 for i in range(10)} | {"tail": 0.1}
    skills = {f"s{i}": SkillConf(1.0, 4) for i in range(8)}
    assert role_score(w, skills, 8) == pytest.approx(1.0)  # хвост не мешает
    assert role_score(w, {"s0": SkillConf(0.5, 2)}, 8) == pytest.approx(0.5 / 8)
    assert role_score({}, skills) == 0.0


def test_backend_candidate():
    skills = _s(python=0.9, fastapi=0.8, postgresql=0.8, sql=0.8, docker=0.6, rest=0.7, git=0.7)
    cat = compute_category(skills, ROLES, STACK, CAT)
    assert cat.primary_role == "backend"
    assert cat.roles[0].role == "backend"
    assert sum(r.weight for r in cat.roles) == pytest.approx(1.0, abs=0.01)
    assert cat.primary_stack == ["python", "fastapi"]  # только языки и фреймворки, по confidence
    assert len(cat.explanation) == 5
    top = cat.explanation[0]
    assert top.contribution == max(e.contribution for e in cat.explanation)
    assert all(e.sources == ("github",) for e in cat.explanation)


def test_stack_top3_languages_and_frameworks():
    skills = _s(python=0.9, fastapi=0.5, django=0.6, java=0.7, go=0.3, sql=0.9)
    cat = compute_category(skills, ROLES, STACK, CAT)
    assert cat.primary_stack == ["python", "java", "django"]


def test_fullstack_rule():
    skills = _s(
        python=0.8,
        sql=0.8,
        rest=0.9,
        postgresql=0.7,
        javascript=0.9,
        react=0.8,
        html=0.9,
        css=0.8,
        docker=0.8,
        redis=0.6,
        databases=0.7,
        typescript=0.7,
        git=0.8,
    )
    cat = compute_category(skills, ROLES, STACK, CAT)
    assert cat.scores["backend"] >= 0.5 and cat.scores["frontend"] >= 0.5
    assert abs(cat.scores["backend"] - cat.scores["frontend"]) < 0.15
    assert cat.primary_role == "fullstack"
    assert {r.role for r in cat.roles} >= {"fullstack", "backend", "frontend"}


def test_no_fullstack_when_gap_large():
    skills = _s(python=0.9, fastapi=0.9, sql=0.9, rest=0.9, postgresql=0.9, git=0.9, html=0.5)
    cat = compute_category(skills, ROLES, STACK, CAT)
    assert cat.primary_role == "backend"
    assert "fullstack" not in {r.role for r in cat.roles}


def test_multilabel_threshold():
    skills = _s(python=1.0, pandas=0.9, numpy=0.9, sql=0.9, rest=0.5)
    cat = compute_category(skills, ROLES, STACK, CAT)
    best = max(cat.scores.values())
    assert {r.role for r in cat.roles} == {r for r, s in cat.scores.items() if s >= 0.6 * best}


def test_empty_profile_has_no_category():
    cat = compute_category({}, ROLES, STACK, CAT)
    assert cat.primary_role is None and cat.roles == [] and cat.primary_stack == []


def test_deterministic():
    skills = _s(python=0.9, sql=0.7, docker=0.5)
    a = compute_category(skills, ROLES, STACK, CAT)
    b = compute_category(dict(reversed(list(skills.items()))), ROLES, STACK, CAT)
    assert a == b


@pytest.fixture
def db_url(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'c.db'}"
    upgrade_head(url)
    return url


@pytest.fixture
async def factory(db_url):
    f = make_session_factory(make_engine(db_url))
    async with session_scope(f) as s:
        await tax.sync(s, DATA)
    return f


async def test_recompute_writes_category_and_event(factory):
    uid = uuid.uuid4()
    async with session_scope(factory) as s:
        s.add(User(id=uid, email=f"{uid.hex}@x.io", password_hash="x", role="candidate"))
        s.add(Candidate(user_id=uid, pseudonym=f"P{uid.hex}", pseudo_id=uid.hex[:12]))
        await s.flush()
        ids = {sl: tax.skill_id(sl) for sl in ("python", "fastapi", "sql", "postgresql", "rest")}
        await service.upsert_evidence(
            s,
            uid,
            [EvidenceIn(i, "fsp", 0.9, NOW.date(), "fact", uuid.uuid4()) for i in ids.values()],
        )
    async with session_scope(factory) as s:
        graph = await tax.load_skill_graph(s)
        res = await recompute_profile(s, uid, None, CFG, graph, now=NOW)
        assert res.changed and res.profile_version == 1
    async with session_scope(factory) as s:
        c = await s.get(Candidate, uid)
        assert c.primary_role == "backend"
        assert c.roles[0]["role"] == "backend"
        assert c.primary_stack == ["python", "fastapi"]
        ev = (
            await s.scalars(
                select(OutboxRecord).where(OutboxRecord.type == "skills.profile.updated")
            )
        ).one()
        cat = ev.payload["payload"]["diff"]["category"]
        assert cat["to"] == "backend" and cat["from"] is None
        loaded = await load_category(s, uid, await tax.load_skill_graph(s), CAT)
        assert loaded.primary_role == "backend" and loaded.explanation
    async with session_scope(factory) as s:  # повтор ничего не меняет
        res = await recompute_profile(s, uid, None, CFG, await tax.load_skill_graph(s), now=NOW)
        assert not res.changed and res.profile_version == 1
