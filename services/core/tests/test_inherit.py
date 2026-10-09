import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.candidates.models import Candidate
from app.graph import service
from app.graph.models import CandidateSkill, Evidence
from app.graph.recompute import recompute_profile
from app.graph.service import EvidenceIn
from app.graph.trust import SkillTrust, TrustConfig, inherit
from app.identity.models import User
from app.taxonomy.models import ScoringConfig, Skill, SkillRelation
from app.taxonomy.service import SkillGraphCache, load_skill_graph
from core_helpers import upgrade_head
from fsp_platform.db import make_engine, make_session_factory, session_scope
from sqlalchemy import select

CORE = Path(__file__).resolve().parents[1]
CFG = TrustConfig.load()
NOW = datetime(2026, 6, 1, 12, tzinfo=UTC)
D = NOW.date()


@pytest.fixture
def factory(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'i.db'}"
    upgrade_head(url)
    return make_session_factory(make_engine(url))


def _t(conf: float) -> SkillTrust:
    return SkillTrust(
        conf, max(i for i, lo in enumerate(CFG.level_min) if conf >= lo), ["fsp"], [], False
    )


def test_fastapi_gives_python_derived():
    fastapi, python, lang = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    parents = {fastapi: [(python, 0.6)], python: [(lang, 0.5)]}
    res = inherit({fastapi: _t(0.9)}, lambda s: parents.get(s, ()), CFG)
    assert res[python][0].confidence == pytest.approx(0.54)
    assert res[python][0].level == 2  # ●●○○
    assert res[python][1] == fastapi
    assert res[lang][0].confidence == pytest.approx(0.27)  # второй уровень
    assert res[lang][1] == python


def test_inherit_depth_limited_to_two_levels():
    a, b, c, d = (uuid.uuid4() for _ in range(4))
    parents = {a: [(b, 1.0)], b: [(c, 1.0)], c: [(d, 1.0)]}
    res = inherit({a: _t(0.8)}, lambda s: parents.get(s, ()), CFG)
    assert set(res) == {b, c}


def test_own_trust_higher_is_kept():
    f, p = uuid.uuid4(), uuid.uuid4()
    res = inherit({f: _t(0.9), p: _t(0.6)}, lambda s: [(p, 0.5)] if s == f else (), CFG)
    assert res == {}  # 0.45 < 0.6
    res = inherit({f: _t(0.9), p: _t(0.3)}, lambda s: [(p, 0.5)] if s == f else (), CFG)
    assert res[p][0].confidence == pytest.approx(0.45)


async def _setup(factory):
    uid = uuid.uuid4()
    async with session_scope(factory) as s:
        s.add(User(id=uid, email=f"{uid.hex}@x.io", password_hash="x", role="candidate"))
        s.add(Candidate(user_id=uid, pseudonym=f"P{uid.hex}", pseudo_id=uid.hex[:12]))
        fa = Skill(slug=f"fa-{uid.hex[:6]}", name="fa", kind="hard", source="core", status="active")
        py = Skill(slug=f"py-{uid.hex[:6]}", name="py", kind="hard", source="core", status="active")
        s.add_all([fa, py])
        await s.flush()
        s.add(SkillRelation(skill_a=fa.id, skill_b=py.id, kind="parent", weight=0.6, source="seed"))
        s.add(ScoringConfig(key="taxonomy", value={"hash": "h"}, version=1))
        return uid, fa.id, py.id


async def test_recompute_writes_derived_row_and_is_stable(factory):
    uid, fa, py = await _setup(factory)
    async with session_scope(factory) as s:
        await service.upsert_evidence(s, uid, [EvidenceIn(fa, "fsp", 0.9, D, "fact", uuid.uuid4())])
    cache = SkillGraphCache()
    async with session_scope(factory) as s:
        g = await cache.get(s)
        res = await recompute_profile(s, uid, None, CFG, g, now=NOW)
        assert res.changed
        rows = {r.skill_id: r for r in await s.scalars(select(CandidateSkill))}
        assert rows[fa].derived is False
        assert rows[py].derived is True and rows[py].derived_from == fa
        assert rows[py].confidence == pytest.approx(0.54) and rows[py].level == 2
    async with session_scope(factory) as s:
        res = await recompute_profile(s, uid, None, CFG, await cache.get(s), now=NOW)
        assert not res.changed  # повтор ничего не меняет


async def test_derived_removed_when_child_evidence_gone(factory):
    uid, fa, py = await _setup(factory)
    ev = EvidenceIn(fa, "fsp", 0.9, D, "fact", uuid.uuid4())
    async with session_scope(factory) as s:
        await service.upsert_evidence(s, uid, [ev])
        await recompute_profile(s, uid, None, CFG, await load_skill_graph(s), now=NOW)
    async with session_scope(factory) as s:
        for e in await s.scalars(select(Evidence)):
            e.is_active = False
        res = await recompute_profile(s, uid, None, CFG, await load_skill_graph(s), now=NOW)
        assert res.changed
        assert list(await s.scalars(select(CandidateSkill))) == []


async def test_cache_reloads_on_version_and_invalidate(factory):
    uid, fa, py = await _setup(factory)
    cache = SkillGraphCache()
    async with session_scope(factory) as s:
        g1 = await cache.get(s)
        assert g1.parents_of(fa) == ((py, 0.6),)
        assert await cache.get(s) is g1  # из памяти
    async with session_scope(factory) as s:
        rel = await s.get(SkillRelation, (fa, py, "parent"))
        rel.weight = 0.4
        (await s.get(ScoringConfig, "taxonomy")).version = 2
    async with session_scope(factory) as s:
        assert (await cache.get(s)).parents_of(fa) == ((py, 0.4),)
    cache.invalidate()
    async with session_scope(factory) as s:
        assert await cache.get(s) is not None
