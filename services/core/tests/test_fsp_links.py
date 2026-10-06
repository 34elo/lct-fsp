"""Связи людей по командам ФСП: перестройка, идемпотентность, приватность (E16-9)."""

import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from app.candidates.models import Candidate
from app.graph import fsp_links
from app.graph.fsp_models import CandidateLink, FspResultRow, FspTeamMember, FspTeamRow
from app.identity.models import User
from fsp_contracts import new_envelope
from fsp_contracts.commands import CoreJob
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.messaging import QUEUES, Consumer
from sqlalchemy import select

CORE = Path(__file__).resolve().parents[1]


@pytest.fixture
def factory(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'l.db'}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url}", "upgrade", "head"],
        cwd=CORE, check=True, capture_output=True,
    )  # fmt: skip
    return make_session_factory(make_engine(url))


async def _cands(factory, n):
    ids = [uuid.uuid4() for _ in range(n)]
    async with session_scope(factory) as s:
        for u in ids:
            t = u.hex[:6]
            s.add(User(id=u, email=f"{t}@x.io", password_hash="x", role="candidate"))
            s.add(Candidate(user_id=u, pseudonym=f"P{t}", pseudo_id=t))
    return ids


async def _team(factory, team_id, members, places):
    """members: id кандидатов (None - участник вне платформы); places: место каждого."""
    async with session_scope(factory) as s:
        s.add(FspTeamRow(id=team_id, name="T", competition_id="c1"))
        await s.flush()
        for i, (cid, place) in enumerate(zip(members, places, strict=True)):
            s.add(FspTeamMember(team_id=team_id, participant_id=f"{team_id}-{i}", candidate_id=cid))
            if cid:
                s.add(
                    FspResultRow(
                        id=uuid.uuid4(), candidate_id=cid, participant_id=f"{team_id}-{i}",
                        competition_id="c1", stage="final", team_id=team_id, place=place,
                    )
                )  # fmt: skip


async def _links(factory):
    q = select(
        CandidateLink.candidate_a,
        CandidateLink.candidate_b,
        CandidateLink.kind,
        CandidateLink.context_id,
    )
    async with factory() as s:
        return {tuple(r) for r in (await s.execute(q)).all()}


async def test_refresh_builds_ordered_pairs_and_is_idempotent(factory):
    a, b, c = await _cands(factory, 3)
    await _team(factory, "t1", [a, b, c, None], [1, 1, 1, 1])
    async with session_scope(factory) as s:
        assert await fsp_links.refresh_links(s) == 3
    first = await _links(factory)
    assert len(first) == 3 and all(x < y and k == "fsp_team" for x, y, k, _ in first)
    async with session_scope(factory) as s:
        await fsp_links.refresh_links(s)
    assert await _links(factory) == first  # повтор не плодит пары
    # состав команды изменился - связи пересобраны
    async with session_scope(factory) as s:
        m = await s.get(FspTeamMember, ("t1", "t1-2"))
        await s.delete(m)
    async with session_scope(factory) as s:
        assert await fsp_links.refresh_links(s) == 1
    assert len(await _links(factory)) == 1


async def test_prize_partner_counts_is_anonymous_aggregate(factory):
    a, b, c, d = await _cands(factory, 4)
    await _team(factory, "t1", [a, b], [2, 9])  # b - не призёр, a - призёр
    await _team(factory, "t2", [a, c], [2, 1])  # c - призёр
    await _team(factory, "t3", [b, d], [9, 9])
    async with session_scope(factory) as s:
        await fsp_links.refresh_links(s)
    async with factory() as s:
        counts = await fsp_links.prize_partner_counts(s, [a, b, c, d])
        assert await fsp_links.prize_partner_counts(s, []) == {}
    # a играл с призёром c (b не призёр); b - с призёром a; c - с призёром a; d - ни с кем
    assert counts == {a: 1, b: 1, c: 1}
    assert all(isinstance(v, int) for v in counts.values())  # только числа, без id напарников


async def test_refresh_job_handler_dedups_delivery(factory):
    a, b = await _cands(factory, 2)
    await _team(factory, "t1", [a, b], [1, 1])
    consumer = Consumer(QUEUES["core.jobs"])
    fsp_links.register({"core.jobs": consumer}, factory)
    env = new_envelope("candidate_links.refresh", "test", CoreJob())
    await consumer.dispatch(env)
    await consumer.dispatch(env)  # повторная доставка: inbox
    assert len(await _links(factory)) == 1
