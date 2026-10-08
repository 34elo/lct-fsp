import boto3
import pytest
from fsp_platform.db import Base, make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord
from fsp_platform.storage import ObjectStorage
from moto import mock_aws
from sqlalchemy import select


@pytest.fixture
def storage():
    with mock_aws():
        yield ObjectStorage("https://s3.amazonaws.com", "k", "s", "fsp-test")


async def test_storage_roundtrip_presign_delete(storage):
    await storage.ensure_bucket()
    await storage.ensure_bucket()  # идемпотентно
    assert not await storage.exists("resumes/a.pdf")
    await storage.put("resumes/a.pdf", b"%PDF-1", "application/pdf")
    assert await storage.exists("resumes/a.pdf")
    assert await storage.get("resumes/a.pdf") == b"%PDF-1"
    url = storage.presigned_get("resumes/a.pdf", 60)
    assert "X-Amz-Signature" in url
    await storage.delete("resumes/a.pdf")
    assert not await storage.exists("resumes/a.pdf")


def test_presigned_uses_public_host():
    with mock_aws():
        st = ObjectStorage("http://minio:9000", "k", "s", "fsp", "https://s3.fsp.example")
        assert st.presigned_get("a").startswith("https://s3.fsp.example/fsp/a")
        assert boto3  # клиент создаётся без сети


async def test_session_scope_commits_and_rolls_back(tmp_path):
    from fsp_contracts import new_envelope
    from fsp_platform.outbox import add_to_outbox

    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path}/s.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    f = make_session_factory(engine)
    with pytest.raises(RuntimeError):
        async with session_scope(f) as s:
            await add_to_outbox(s, new_envelope("offer.sent", "core", {}))
            raise RuntimeError
    async with f() as s:
        assert (await s.execute(select(OutboxRecord))).first() is None
    await engine.dispose()
