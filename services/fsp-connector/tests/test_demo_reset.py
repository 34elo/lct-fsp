"""Сброс демо-привязок ФСП (E40-1): только демо-кандидаты и участники песочниц жюри."""

from uuid import uuid4

import pytest
from fsp_connector import demo
from fsp_connector.models import FspLink, RegistryParticipant, RegistryResult, metadata
from fsp_platform.db import make_engine, make_session_factory, session_scope
from sqlalchemy import func, select


@pytest.fixture
async def factory(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path}/d.db")
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield make_session_factory(engine)
    await engine.dispose()


def _link(cid, pid):
    return FspLink(candidate_id=cid, participant_id=pid, verified=True, method="registry")


def test_parse_ids_skips_noise():
    a = uuid4()
    assert demo.parse_ids([f"DEMO_ID {a}\n", "log line", "DEMO_ID nope", ""]) == [a]


async def test_reset_keeps_real_links_and_restores_demo(factory):
    hero, real, sandbox = uuid4(), uuid4(), uuid4()
    async with session_scope(factory) as s:
        s.add(_link(hero, "p-hero"))
        s.add(
            RegistryParticipant(
                id="r-jury", full_name="Жюри", email_norm="jury-candidate@demo.fsp.test"
            )
        )
        await s.flush()
        await demo.snapshot(s, [hero])
    async with session_scope(factory) as s:
        await s.execute(FspLink.__table__.delete().where(FspLink.candidate_id == hero))
        s.add(_link(real, "p-real"))  # реальная привязка после снапшота
        s.add(
            RegistryParticipant(
                id="r-sb", full_name="Жюри", email_norm="jury-0123456789ab-c@demo.fsp.test"
            )
        )
        await s.flush()
        s.add(RegistryResult(participant_id="r-sb", event_id="e-1", place=2))
        s.add(_link(sandbox, "r-sb"))
    async with session_scope(factory) as s:
        out = await demo.reset(s, [hero, sandbox])
    assert out["deleted"]["fsp_reg_participants"] == 1
    async with session_scope(factory) as s:
        links = {lk.candidate_id: lk.participant_id for lk in await s.scalars(select(FspLink))}
        assert links == {hero: "p-hero", real: "p-real"}
        ids = set(await s.scalars(select(RegistryParticipant.id)))
        assert ids == {"r-jury"}  # базовый участник жюри на месте, копия песочницы удалена
        assert await s.scalar(select(func.count()).select_from(RegistryResult)) == 0


async def test_reset_without_snapshot_fails(factory):
    async with session_scope(factory) as s:
        with pytest.raises(demo.SnapshotMissing):
            await demo.reset(s, [uuid4()])
