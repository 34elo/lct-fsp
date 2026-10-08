import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from app.candidates.models import Candidate
from app.graph import service
from app.graph.embedding import (
    Embedded,
    EmbeddingError,
    MlEmbedder,
    SkillLine,
    build_profile_text,
    text_sha,
)
from app.graph.recompute import recompute_profile
from app.graph.service import EvidenceIn
from app.graph.trust import TrustConfig
from app.identity.models import User
from app.taxonomy.models import Skill
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import func, select

CORE = Path(__file__).resolve().parents[1]
CFG = TrustConfig.load()
NOW = datetime(2026, 6, 1, 12, tzinfo=UTC)


@pytest.fixture
def factory(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'e.db'}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url}", "upgrade", "head"],
        cwd=CORE,
        check=True,
        capture_output=True,
    )
    return make_session_factory(make_engine(url))


class FakeEmbedder:
    def __init__(self, fail=False):
        self.calls: list[str] = []
        self.fail = fail

    async def embed_passage(self, text):
        self.calls.append(text)
        if self.fail:
            raise EmbeddingError("down")
        return Embedded("fake", [float(len(text) % 7)] + [0.5] * 1023)


async def _seed(factory):
    uid = uuid.uuid4()
    async with session_scope(factory) as s:
        s.add(User(id=uid, email=f"{uid.hex}@x.io", password_hash="x", role="candidate"))
        s.add(Candidate(user_id=uid, pseudonym=f"P{uid.hex}", pseudo_id=uid.hex[:12]))
        sk = Skill(slug=f"py-{uid.hex[:6]}", name="py", kind="hard", source="core", status="active")
        s.add(sk)
        await s.flush()
        return uid, sk.id


async def _give(factory, uid, sk, source="fsp", strength=0.9):
    async with session_scope(factory) as s:
        await service.upsert_evidence(
            s, uid, [EvidenceIn(sk, source, strength, NOW.date(), "fact", uuid.uuid4())]
        )


def test_profile_text_is_deterministic_and_has_no_pii():
    kw = dict(
        primary_role="backend",
        roles=[("backend", 0.7), ("data_engineer", 0.3)],
        grade="middle",
        experience_months=30,
        skills=[
            SkillLine("sql", 2, 0.4, False),
            SkillLine("python", 4, 0.9, False),
            SkillLine("docker", 1, 0.2, True),
        ],
    )
    text = build_profile_text(**kw)
    assert text == (
        "Роль: backend. Смежные роли: data_engineer. Грейд: middle. Опыт: 2 лет 6 мес. "
        "Подтверждённые навыки: python (4), sql (2). Заявленные навыки: docker."
    )
    assert build_profile_text(**{**kw, "skills": list(reversed(kw["skills"]))}) == text
    assert (
        build_profile_text(
            primary_role=None, roles=[], grade=None, experience_months=None, skills=[]
        )
        == ""
    )


async def test_embedding_computed_once_per_text(factory):
    uid, sk = await _seed(factory)
    emb = FakeEmbedder()
    await _give(factory, uid, sk)
    async with session_scope(factory) as s:
        await recompute_profile(s, uid, None, CFG, now=NOW, embedder=emb)
    async with session_scope(factory) as s:
        c = await s.get(Candidate, uid)
        assert c.profile_text and c.profile_text_sha == text_sha(c.profile_text)
        assert len(c.embedding) == 1024 and c.embedding_model == "fake"
    # повторный пересчёт того же профиля: текст тот же → в ml-api не ходим
    async with session_scope(factory) as s:
        res = await recompute_profile(s, uid, None, CFG, now=NOW, embedder=emb)
        assert not res.changed
    assert len(emb.calls) == 1
    # изменился профиль → новый текст → новый вектор
    other = Skill(slug="sql-x", name="sql", kind="hard", source="core", status="active")
    async with session_scope(factory) as s:
        s.add(other)
        await s.flush()
        other_id = other.id
    await _give(factory, uid, other_id, "github", 0.5)
    async with session_scope(factory) as s:
        await recompute_profile(s, uid, None, CFG, now=NOW, embedder=emb)
    assert len(emb.calls) == 2


async def test_embedding_does_not_bump_version_or_emit_events(factory):
    uid, sk = await _seed(factory)
    await _give(factory, uid, sk)
    async with session_scope(factory) as s:
        await recompute_profile(s, uid, None, CFG, now=NOW)  # без embedder: только текст
    async with session_scope(factory) as s:
        c = await s.get(Candidate, uid)
        assert c.profile_text and c.embedding is None and c.profile_version == 1
        res = await recompute_profile(s, uid, None, CFG, now=NOW, embedder=FakeEmbedder())
        assert not res.changed and res.profile_version == 1
        assert (await s.get(Candidate, uid)).embedding is not None
        n = await s.scalar(
            select(func.count())
            .select_from(OutboxRecord)
            .where(OutboxRecord.type == "skills.profile.updated")
        )
        assert n == 1


async def test_ml_failure_keeps_recompute_and_retries_next_time(factory):
    uid, sk = await _seed(factory)
    await _give(factory, uid, sk)
    async with session_scope(factory) as s:
        res = await recompute_profile(s, uid, None, CFG, now=NOW, embedder=FakeEmbedder(fail=True))
        assert res.changed
        c = await s.get(Candidate, uid)
        assert c.embedding is None and c.profile_text_sha is None and c.profile_text
    ok = FakeEmbedder()
    async with session_scope(factory) as s:
        await recompute_profile(s, uid, None, CFG, now=NOW, embedder=ok)
        assert (await s.get(Candidate, uid)).embedding is not None
    assert len(ok.calls) == 1


async def test_text_follows_graph_when_evidence_disappears(factory):
    uid, sk = await _seed(factory)
    await _give(factory, uid, sk)
    emb = FakeEmbedder()
    async with session_scope(factory) as s:
        await recompute_profile(s, uid, None, CFG, now=NOW, embedder=emb)
        assert "Подтверждённые навыки" in (await s.get(Candidate, uid)).profile_text
    async with session_scope(factory) as s:
        await service.deactivate(s, uid, source="fsp")
        await recompute_profile(s, uid, None, CFG, now=NOW, embedder=emb)
        c = await s.get(Candidate, uid)
        assert "навыки" not in (c.profile_text or "")
        assert c.profile_text_sha == (text_sha(c.profile_text) if c.profile_text else None)
    assert len(emb.calls) >= 1


class _Redis:
    def __init__(self):
        self.d: dict[str, str] = {}

    async def get(self, k):
        return self.d.get(k)

    async def set(self, k, v, ex=None):
        self.d[k] = v


def _transport(calls, dim=1024, status=200):
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(json.loads(req.content))
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, json={"model": "m", "dim": dim, "vectors": [[0.1] * dim]})

    return httpx.MockTransport(handler)


async def test_ml_embedder_calls_ml_api_and_caches_by_sha():
    calls: list[dict] = []
    redis = _Redis()
    e = MlEmbedder("http://ml", model="m", redis=redis, transport=_transport(calls))
    a = await e.embed_passage("текст")
    b = await e.embed_passage("текст")
    assert a == b and a.model == "m" and len(a.vector) == 1024
    assert calls == [{"texts": ["текст"], "kind": "passage"}]
    assert f"c:emb:p:m:{text_sha('текст')}" in redis.d


async def test_ml_embedder_errors():
    for kw in ({"status": 503}, {"dim": 768}):
        e = MlEmbedder("http://ml", transport=_transport([], **kw))
        with pytest.raises(EmbeddingError):
            await e.embed_passage("x")
