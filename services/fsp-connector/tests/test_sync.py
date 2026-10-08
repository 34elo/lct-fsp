from datetime import date
from uuid import uuid4

import fakeredis
import pytest
from fsp_connector import handlers
from fsp_connector.models import FspLink, metadata
from fsp_connector.sync import SyncService
from fsp_contracts import Envelope, new_envelope
from fsp_contracts.commands import FspSync, FspSyncAll
from fsp_contracts.events import FspCompetitionsUpdated, FspResultsImported
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.messaging import QUEUES, Consumer
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import select


@pytest.fixture
async def env(tmp_path, adapter, mock_store):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    factory = make_session_factory(engine)
    yield SyncService(adapter, factory), factory, mock_store
    await engine.dispose()


async def _link(factory, pid="p-anya", verified=True):
    cid = uuid4()
    async with session_scope(factory) as s:
        s.add(FspLink(candidate_id=cid, participant_id=pid, verified=verified, method="oauth"))
    return cid


async def _events(factory, type_=None):
    async with factory() as s:
        recs = (await s.execute(select(OutboxRecord).order_by(OutboxRecord.id))).scalars().all()
    return [r for r in recs if type_ is None or r.type == type_]


async def test_full_sync_publishes_results_ranks_teams_and_competitions(env):
    svc, factory, _ = env
    cid = await _link(factory)
    async with session_scope(factory) as s:
        assert await svc.sync_candidate(s, cid, reason="linked") is True
    assert [e.type for e in await _events(factory)] == [
        "fsp.competitions.updated",
        "fsp.results.imported",
    ]
    comps = FspCompetitionsUpdated.model_validate(
        Envelope.model_validate(
            (await _events(factory, "fsp.competitions.updated"))[0].payload
        ).payload
    )
    assert [c.id for c in comps.competitions] == ["c-002"]
    imp = FspResultsImported.model_validate(
        Envelope.model_validate((await _events(factory, "fsp.results.imported"))[0].payload).payload
    )
    assert imp.new is True and imp.candidate_id == cid and imp.participant_id == "p-anya"
    (res,) = imp.results
    assert (res.competition_id, res.team_role, res.place, res.track) == (
        "c-002",
        "captain",
        2,
        "web",
    )
    assert [(r.discipline, r.rank) for r in imp.ranks] == [("product", "rank_2")]
    (team,) = imp.teams
    assert {m.participant_id for m in team.members} == {"p-anya", "p-m01", "p-m02"}
    async with factory() as s:
        link = await s.get(FspLink, cid)
    assert link.last_synced_at is not None and link.sync_cursor


async def test_incremental_sync_without_news_publishes_nothing(env):
    svc, factory, _ = env
    cid = await _link(factory)
    async with session_scope(factory) as s:
        await svc.sync_candidate(s, cid, reason="linked")
    async with session_scope(factory) as s:
        assert await svc.sync_candidate(s, cid, reason="schedule") is False
    assert len(await _events(factory)) == 2


async def test_incremental_sync_picks_new_result_with_new_false(env):
    svc, factory, store = env
    cid = await _link(factory, "p-dima")
    async with session_scope(factory) as s:
        await svc.sync_candidate(s, cid, reason="linked")
    store.add_result(
        "p-dima",
        competition_id="c-002",
        discipline="product",
        stage="qualifier",
        team_role="individual",
        place=5,
        participants_total=50,
        score=1.0,
        date=date.today(),
    )
    async with session_scope(factory) as s:
        assert await svc.sync_candidate(s, cid, reason="webhook") is True
    last = FspResultsImported.model_validate(
        Envelope.model_validate(
            (await _events(factory, "fsp.results.imported"))[-1].payload
        ).payload
    )
    assert last.new is False and [r.stage for r in last.results] == ["qualifier"]


async def test_unlinked_candidate_is_skipped(env):
    svc, factory, _ = env
    async with session_scope(factory) as s:
        assert await svc.sync_candidate(s, uuid4(), reason="manual") is False
    assert await _events(factory) == []


async def test_sync_all_publishes_calendar_and_syncs_every_link(env):
    svc, factory, _ = env
    a, b = await _link(factory, "p-anya"), await _link(factory, "p-dima")
    assert await svc.sync_all() == 2
    types = [e.type for e in await _events(factory)]
    assert types.count("fsp.results.imported") == 2
    assert types.count("fsp.competitions.updated") >= 1
    assert {e.aggregate_id for e in await _events(factory, "fsp.results.imported")} == {a, b}


async def test_command_handler_is_idempotent_on_redelivery(env):
    svc, factory, _ = env
    cid = await _link(factory)
    consumers = {"fsp.sync": Consumer(QUEUES["fsp.sync"])}
    handlers.register(consumers, factory, svc, fakeredis.FakeAsyncRedis())
    env_ = new_envelope("fsp.sync", "core", FspSync(candidate_id=cid, reason="linked"))
    await consumers["fsp.sync"].dispatch(env_)
    await consumers["fsp.sync"].dispatch(env_)  # повторная доставка того же сообщения
    assert len(await _events(factory, "fsp.results.imported")) == 1

    all_ = new_envelope("fsp.sync_all", "core-scheduler", FspSyncAll())
    await consumers["fsp.sync"].dispatch(all_)
    await consumers["fsp.sync"].dispatch(all_)
    assert len(await _events(factory, "fsp.competitions.updated")) == 2  # 1 от sync + 1 от sync_all
