from uuid import uuid4

import pytest
from fsp_connector.models import metadata
from fsp_connector.publisher import (
    publish_competitions_updated,
    publish_linked,
    publish_results_imported,
)
from fsp_contracts import Envelope
from fsp_contracts.events import FspCompetitionsUpdated, FspLinked, FspResultsImported
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord, relay_once
from sqlalchemy import select


@pytest.fixture
async def factory(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield make_session_factory(engine)
    await engine.dispose()


async def test_events_go_to_outbox_in_transaction_and_relay_once(factory):
    cid = uuid4()
    async with session_scope(factory) as s:
        await publish_linked(
            s, FspLinked(candidate_id=cid, participant_id="p-anya", verified=True, method="oauth")
        )
        await publish_results_imported(
            s, FspResultsImported(candidate_id=cid, participant_id="p-anya", new=True)
        )
        await publish_competitions_updated(s, FspCompetitionsUpdated(competitions=[]))
    async with factory() as s:
        recs = (await s.execute(select(OutboxRecord).order_by(OutboxRecord.id))).scalars().all()
    assert [r.type for r in recs] == [
        "fsp.linked",
        "fsp.results.imported",
        "fsp.competitions.updated",
    ]
    assert recs[0].aggregate_id == cid and recs[2].aggregate_id is None
    assert Envelope.model_validate(recs[0].payload).producer == "fsp-connector"

    sent = []

    async def publish(e):
        sent.append(e.type)

    async with factory() as s:
        assert await relay_once(s, publish) == 3
    async with factory() as s:
        assert await relay_once(s, publish) == 0
    assert len(sent) == 3


async def test_rollback_publishes_nothing(factory):
    with pytest.raises(RuntimeError):
        async with session_scope(factory) as s:
            await publish_competitions_updated(s, FspCompetitionsUpdated(competitions=[]))
            raise RuntimeError
    async with factory() as s:
        assert (await s.execute(select(OutboxRecord))).first() is None
