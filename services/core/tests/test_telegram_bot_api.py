"""Internal API бота: резюме файлом и краткий профиль (api.md §2.10)."""

import asyncio
import io
import json
import zipfile
from pathlib import Path

import fakeredis
import pytest
from app.config import Settings
from app.main import build_app
from app.resumes import service
from app.resumes.handlers import register
from app.resumes.models import Resume
from app.taxonomy.models import Skill
from core_helpers import upgrade_head
from fastapi.testclient import TestClient
from fsp_contracts import new_envelope
from fsp_contracts.events import MlResumeResult
from fsp_contracts.ml import ParsedResume
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.messaging import QUEUES, Consumer
from fsp_platform.ratelimit import RateLimiter
from sqlalchemy import func, select

CORE = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parents[3] / "services/ml/fixtures/parsed_resume.json"
SVC = {"Authorization": "Service test-bot-token"}
PDF = b"%PDF-1.7\n%fake resume\n"
SLUGS = ["python", "fastapi", "postgresql", "docker", "pytest"]


class FakeStorage:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    async def ensure_bucket(self):
        pass

    async def put(self, key, data, content_type="application/octet-stream"):
        self.files[key] = data


@pytest.fixture
def env(tmp_path):
    db = tmp_path / "b.db"
    url = f"sqlite+aiosqlite:///{db}"
    upgrade_head(url)
    app = build_app(
        Settings(database_url=url, ui_bus_enabled=False, service_token_bot="test-bot-token")
    )
    factory = make_session_factory(make_engine(url))

    async def seed():
        async with session_scope(factory) as s:
            for slug in SLUGS:
                s.add(Skill(slug=slug, name=slug.title(), kind="hard", source="core"))

    asyncio.run(seed())
    with TestClient(app) as c:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        app.state.storage = FakeStorage()
        c.storage, c.factory = app.state.storage, factory
        yield c


def _start(c, tg=501):
    r = c.post(
        "/internal/tg/start", json={"tg_user_id": tg, "chat_id": tg, "username": "u"}, headers=SVC
    )
    assert r.status_code == 200
    return r.json()["user_id"]


def _consent(c, tg=501):
    r = c.post(
        "/internal/tg/consents",
        json={"tg_user_id": tg, "types": ["pd_processing"]},
        headers=SVC,
    )
    assert r.status_code == 204


def _up(c, data=PDF, tg=501, headers=SVC):
    return c.post(
        "/internal/tg/resumes",
        files={"file": ("cv.pdf", data)},
        data={"tg_user_id": str(tg)},
        headers=headers,
    )


def _docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


def _deliver(c, resume_id, uid):
    parsed = ParsedResume.model_validate(json.loads(FIXTURE.read_text()))
    consumers = {"core.ingest": Consumer(QUEUES["core.ingest"])}
    register(consumers, c.factory, None)
    env = new_envelope(
        "ml.resume.completed",
        "ml",
        MlResumeResult(resume_id=resume_id, candidate_id=uid, parsed=parsed, error=None),
    )
    asyncio.run(consumers["core.ingest"].dispatch(env))


def test_upload_needs_service_token_and_known_user_and_consent(env):
    c = env
    assert _up(c, headers={}).status_code == 401
    assert _up(c).status_code == 404  # Telegram неизвестен
    _start(c)
    r = _up(c)
    assert r.status_code == 403 and r.json()["code"] == "consent_required"


def test_upload_checks_signature_size_and_stores(env):
    c = env
    _start(c)
    _consent(c)
    r = _up(c, b"MZ\x90\x00 exe")
    assert r.status_code == 415 and r.json()["code"] == "unsupported_file_type"
    assert _up(c, b"").status_code == 422
    big = b"%PDF-" + b"0" * service.MAX_BYTES
    assert _up(c, big).status_code == 413
    ok = _up(c)
    assert ok.status_code == 202 and set(ok.json()) == {"resume_id", "job_id"}
    assert _up(c, _docx()).status_code == 202
    assert len(c.storage.files) == 2


def test_status_confirm_and_owner_isolation(env):
    c = env
    uid = _start(c)
    _consent(c)
    rid = _up(c).json()["resume_id"]
    st = c.get(f"/internal/tg/resumes/{rid}", params={"tg_user_id": 501}, headers=SVC)
    assert st.status_code == 200 and st.json()["status"] == "queued"
    early = c.post(f"/internal/tg/resumes/{rid}/confirm", json={"tg_user_id": 501}, headers=SVC)
    assert early.status_code == 409 and early.json()["code"] == "resume_not_parsed"
    _deliver(c, rid, uid)
    st = c.get(f"/internal/tg/resumes/{rid}", params={"tg_user_id": 501}, headers=SVC).json()
    assert st["status"] == "parsed" and st["skills"] and st["experience_months"] is not None
    # чужой Telegram видит 404
    _start(c, tg=502)
    other = c.get(f"/internal/tg/resumes/{rid}", params={"tg_user_id": 502}, headers=SVC)
    assert other.status_code == 404
    done = c.post(f"/internal/tg/resumes/{rid}/confirm", json={"tg_user_id": 501}, headers=SVC)
    assert done.status_code == 200 and done.json()["status"] == "confirmed"
    again = c.post(f"/internal/tg/resumes/{rid}/confirm", json={"tg_user_id": 501}, headers=SVC)
    assert again.status_code == 200 and again.json()["status"] == "confirmed"

    async def n(s):
        return await s.scalar(select(func.count()).select_from(Resume))

    async def go():
        async with session_scope(c.factory) as s:
            return await n(s)

    assert asyncio.run(go()) == 1


def test_profile_short(env):
    c = env
    uid = _start(c)
    _consent(c)
    empty = c.get("/internal/tg/profile", params={"tg_user_id": 501}, headers=SVC)
    assert empty.status_code == 200
    assert empty.json()["skills"] == [] and empty.json()["grade_preliminary"] is True
    rid = _up(c).json()["resume_id"]
    _deliver(c, rid, uid)
    c.post(f"/internal/tg/resumes/{rid}/confirm", json={"tg_user_id": 501}, headers=SVC)
    body = c.get("/internal/tg/profile", params={"tg_user_id": 501}, headers=SVC).json()
    assert set(body) == {"primary_role", "grade", "grade_preliminary", "skills", "fsp"}
    assert c.get("/internal/tg/profile", params={"tg_user_id": 999}, headers=SVC).status_code == 404
    assert c.get("/internal/tg/profile", params={"tg_user_id": 501}).status_code == 401


def test_user_token_for_bot(env):
    c = env
    uid = _start(c)
    ok = c.post("/internal/tg/token", json={"tg_user_id": 501}, headers=SVC)
    assert ok.status_code == 200 and ok.json()["expires_in"] == 300
    # токен рабочий для обычного API кандидата, но выдан только по сервисному токену
    me = c.get(
        "/assessment/survey", headers={"Authorization": f"Bearer {ok.json()['access_token']}"}
    )
    assert me.status_code == 200, (me.text, uid)
    assert c.post("/internal/tg/token", json={"tg_user_id": 501}).status_code == 401
    assert c.post("/internal/tg/token", json={"tg_user_id": 999}, headers=SVC).status_code == 404
