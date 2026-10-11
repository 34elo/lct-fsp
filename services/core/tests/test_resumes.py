import asyncio
import io
import json
import zipfile
from datetime import date
from pathlib import Path

import fakeredis
import pytest
from app.config import Settings
from app.graph.models import Evidence
from app.main import build_app
from app.resumes import service
from app.resumes.handlers import register
from app.resumes.models import Education, Experience, Resume
from app.taxonomy.models import Skill
from core_helpers import upgrade_head
from fastapi.testclient import TestClient
from fsp_contracts import new_envelope
from fsp_contracts.events import MlResumeResult
from fsp_contracts.ml import ParsedResume, ResumeExperience
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.messaging import QUEUES, Consumer
from fsp_platform.outbox import OutboxRecord
from fsp_platform.ratelimit import RateLimiter
from sqlalchemy import func, select

CORE = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parents[3] / "services/ml/fixtures/parsed_resume.json"
PWD = "correct-horse-battery"
PDF = b"%PDF-1.7\n%fake resume\n"
SLUGS = ["python", "fastapi", "postgresql", "docker", "pytest"]
TODAY = date(2026, 6, 1)


class FakeStorage:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    async def ensure_bucket(self):
        pass

    async def put(self, key, data, content_type="application/octet-stream"):
        self.files[key] = data


def _docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


@pytest.fixture
def env(tmp_path):
    db = tmp_path / "r.db"
    url = f"sqlite+aiosqlite:///{db}"
    upgrade_head(url)
    app = build_app(Settings(database_url=url, ui_bus_enabled=False))
    storage = FakeStorage()
    engine = make_engine(url)
    factory = make_session_factory(engine)

    async def seed():
        async with session_scope(factory) as s:
            for slug in [*SLUGS, "communication"]:
                kind = "soft" if slug == "communication" else "hard"
                s.add(Skill(slug=slug, name=slug.title(), kind=kind, source="core"))

    asyncio.run(seed())
    with TestClient(app) as client:
        app.state.redis = fakeredis.FakeAsyncRedis()
        app.state.limiter = RateLimiter(app.state.redis)
        app.state.storage = storage
        client.storage, client.factory, client.url = storage, factory, url
        yield client


def _user(c, email):
    r = c.post("/auth/register", json={"email": email, "password": PWD, "role": "candidate"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    body = {"consents": [{"type": "pd_processing", "granted": True}]}
    assert c.put("/me/consents", json=body, headers=h).status_code == 200
    return h


def _upload(c, h, data=PDF, name="cv.pdf"):
    return c.post("/candidates/me/resumes", files={"file": (name, data)}, headers=h)


def _run(c, coro_fn):
    async def go():
        async with session_scope(c.factory) as s:
            return await coro_fn(s)

    return asyncio.run(go())


def _deliver(c, resume_id, candidate_id, parsed=None, error=None, published=None, env=None):
    consumers = {"core.ingest": Consumer(QUEUES["core.ingest"])}
    register(consumers, c.factory, _collect(published) if published is not None else None)
    typ = "ml.resume.failed" if error else "ml.resume.completed"
    if env is None:
        payload = MlResumeResult(
            resume_id=resume_id, candidate_id=candidate_id, parsed=parsed, error=error
        )
        env = new_envelope(typ, "ml", payload)
    asyncio.run(consumers["core.ingest"].dispatch(env))
    return env


def _collect(bucket):
    async def publish(msg):
        bucket.append(msg)

    return publish


def _parsed() -> ParsedResume:
    return ParsedResume.model_validate(json.loads(FIXTURE.read_text()))


def _uid(c, resume_id):
    return _run(c, lambda s: _cid(s, resume_id))


async def _cid(s, resume_id):
    return (await s.get(Resume, resume_id)).candidate_id


# --- формулы ---------------------------------------------------
def test_skill_strength_levels():
    exp = [
        ResumeExperience(start="2022-03", end=None, skills=["python"]),
        ResumeExperience(start="2021-06", end="2021-09", skills=["pytest"]),
    ]
    assert service.skill_strength("python", exp, TODAY) == 0.40  # >= 12 мес в опыте
    assert service.skill_strength("pytest", exp, TODAY) == 0.30  # в опыте, но коротко
    assert service.skill_strength("docker", exp, TODAY) == 0.25  # только блок «Навыки»


def test_experience_months_union_and_commercial():
    exp = [
        ResumeExperience(start="2020-01", end="2021-01"),
        ResumeExperience(start="2020-07", end="2021-07"),  # пересекается: итого 18 мес
        ResumeExperience(start="2022-01", end="2022-07", is_commercial=False),  # не считаем
        ResumeExperience(start=None, end=None),  # без дат
    ]
    assert service.experience_months(exp, TODAY) == 18


def test_detect_mime_by_signature():
    assert service.detect_mime(PDF) == service.PDF
    assert service.detect_mime(_docx()) == service.DOCX
    assert service.detect_mime(b"PK\x03\x04junk") is None
    assert service.detect_mime(b"MZ\x90\x00") is None


# --- загрузка -------------------------------------------------------------------
def test_upload_stores_file_and_enqueues_parse(env):
    h = _user(env, "a@x.io")
    r = _upload(env, h)
    assert r.status_code == 202
    body = r.json()
    rid = body["resume_id"]
    assert list(env.storage.files.values()) == [PDF]

    async def check(s):
        cmds = list(
            await s.scalars(select(OutboxRecord).where(OutboxRecord.type == "ml.resume.parse"))
        )
        resume = await s.get(Resume, __import__("uuid").UUID(rid))
        return cmds, resume

    cmds, resume = _run(env, check)
    assert resume.status == "queued" and resume.mime == service.PDF
    assert len(cmds) == 1
    payload = cmds[0].payload["payload"]
    assert payload["resume_id"] == rid and payload["object_key"] == resume.file_key
    assert str(cmds[0].payload["message_id"]) == body["job_id"]
    got = env.get(f"/candidates/me/resumes/{rid}", headers=h).json()
    assert got == {"status": "queued", "parsed": None, "error": None}


def test_upload_rejects_bad_files(env):
    h = _user(env, "a@x.io")
    assert _upload(env, h, b"MZ\x90\x00 evil", "cv.pdf").status_code == 415
    assert _upload(env, h, b"", "cv.pdf").status_code == 422
    big = PDF + b"0" * (service.MAX_BYTES)
    assert _upload(env, h, big).status_code == 413
    assert _upload(env, h, _docx(), "cv.docx").status_code == 202
    assert env.storage.files  # только корректный файл


def test_upload_needs_auth_consent_and_role(env):
    assert _upload(env, {}).status_code == 401
    r = env.post("/auth/register", json={"email": "n@x.io", "password": PWD, "role": "candidate"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert _upload(env, h).status_code == 403  # без согласия
    r = env.post("/auth/register", json={"email": "e@x.io", "password": PWD, "role": "employer"})
    e = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert _upload(env, e).status_code == 403


def test_upload_rate_limit(env):
    h = _user(env, "a@x.io")
    for _ in range(service.UPLOAD_LIMIT):
        assert _upload(env, h).status_code == 202
    r = _upload(env, h)
    assert r.status_code == 429 and "retry-after" in r.headers


def test_foreign_resume_is_404(env):
    a, b = _user(env, "a@x.io"), _user(env, "b@x.io")
    rid = _upload(env, a).json()["resume_id"]
    assert env.get(f"/candidates/me/resumes/{rid}", headers=b).status_code == 404
    assert env.post(f"/candidates/me/resumes/{rid}/confirm", json={}, headers=b).status_code == 404
    unknown = "00000000-0000-4000-8000-000000000000"
    assert env.get(f"/candidates/me/resumes/{unknown}", headers=a).status_code == 404


# --- результат разбора ----------------------------------------------------------
def test_ml_result_saved_idempotent_and_ui(env):
    h = _user(env, "a@x.io")
    rid = _upload(env, h).json()["resume_id"]
    import uuid

    cid = _uid(env, uuid.UUID(rid))
    ui: list = []
    e = _deliver(env, uuid.UUID(rid), cid, parsed=_parsed(), published=ui)
    _deliver(env, uuid.UUID(rid), cid, parsed=_parsed(), published=ui, env=e)  # повторная доставка
    got = env.get(f"/candidates/me/resumes/{rid}", headers=h).json()
    assert got["status"] == "parsed" and got["parsed"]["parser_version"] == "fake-1"
    assert len(got["parsed"]["skills"]) == 5
    assert [m.event for m in ui] == ["resume.parsed"] and ui[0].data["resume_id"] == rid

    async def events(s):
        return await s.scalar(
            select(func.count())
            .select_from(OutboxRecord)
            .where(OutboxRecord.type == "resume.parsed")
        )

    assert _run(env, events) == 1


def test_ml_failure_saved(env):
    h = _user(env, "a@x.io")
    rid = _upload(env, h).json()["resume_id"]
    import uuid

    cid = _uid(env, uuid.UUID(rid))
    ui: list = []
    _deliver(env, uuid.UUID(rid), cid, error="scanned_pdf", published=ui)
    got = env.get(f"/candidates/me/resumes/{rid}", headers=h).json()
    assert got == {"status": "failed", "parsed": None, "error": "scanned_pdf"}
    assert ui[0].event == "resume.failed" and ui[0].data["reason"] == "scanned_pdf"
    # подтвердить нельзя
    assert env.post(f"/candidates/me/resumes/{rid}/confirm", json={}, headers=h).status_code == 409


# --- подтверждение --------------------------------------------------------------
def _parsed_resume(env, h, parsed=None):
    import uuid

    rid = _upload(env, h).json()["resume_id"]
    cid = _uid(env, uuid.UUID(rid))
    _deliver(env, uuid.UUID(rid), cid, parsed=parsed or _parsed())
    return rid, cid


def _evidence(env, cid):
    async def q(s):
        rows = await s.execute(
            select(
                Skill.slug,
                Evidence.source,
                Evidence.strength,
                Evidence.is_active,
                Evidence.verified,
            )
            .join(Skill, Skill.id == Evidence.skill_id)
            .where(Evidence.candidate_id == cid)
        )
        return sorted(rows.all())

    return _run(env, q)


def test_confirm_creates_evidence_experience_and_profile(env):
    h = _user(env, "a@x.io")
    parsed = _parsed()
    parsed.skills.append(  # софт-навык: заявлен, но не доказательство
        type(parsed.skills[0])(
            raw="Коммуникация",
            slug="communication",
            quote="команда",
            method="alias",
            confidence=0.7,
        )
    )
    rid, cid = _parsed_resume(env, h, parsed)
    r = env.post(f"/candidates/me/resumes/{rid}/confirm", json={}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    ev = {slug: (src, st, act, ver) for slug, src, st, act, ver in _evidence(env, cid)}
    assert set(ev) == set(SLUGS)  # communication — не evidence
    assert ev["python"][:3] == ("resume", 0.40, True)  # опыт с 2022-03, >= 12 мес
    assert ev["docker"][1] == 0.40
    assert ev["pytest"][1] == 0.30  # стажировка 8 мес
    assert all(v[3] is False for v in ev.values())  # заявлено, не подтверждено

    async def rows(s):
        ex = list(await s.scalars(select(Experience).where(Experience.candidate_id == cid)))
        ed = list(await s.scalars(select(Education).where(Education.candidate_id == cid)))
        evt = list(
            await s.scalars(
                select(OutboxRecord.type).where(
                    OutboxRecord.type.in_(
                        ["resume.confirmed", "evidence.changed", "core.recompute"]
                    )
                )
            )
        )
        return ex, ed, evt

    ex, ed, evt = _run(env, rows)
    assert len(ex) == 2 and len(ed) == 1 and ex[0].source == "resume"
    assert "resume.confirmed" in evt and "evidence.changed" in evt and "core.recompute" in evt
    prof = env.get("/candidates/me/profile", headers=h).json()
    assert prof["claimed_soft"] == ["Communication"]
    assert prof["experience"][0]["title"] == "Backend-разработчик"
    assert prof["experience"][0]["skills"] == ["python", "fastapi", "postgresql", "docker"]
    assert prof["experience"][0]["start"] == "2022-03" and prof["experience"][0]["end"] is None

    async def cand(s):
        from app.candidates.models import Candidate

        return (await s.get(Candidate, cid)).experience_months

    assert _run(env, cand) == 42


def test_confirm_edits_remove_add_and_experience(env):
    h = _user(env, "a@x.io")
    rid, cid = _parsed_resume(env, h)
    edits = {
        "remove_skills": ["pytest"],
        "add_skills": ["communication", "pytest"],  # soft — в заявленные; pytest добавлен вручную
        "experience": [
            {
                "company": "Вымышленная",
                "title": "Dev",
                "start": "2020-01",
                "end": "2021-01",
                "skills": ["python"],
            }
        ],
        "education": [],
    }
    r = env.post(f"/candidates/me/resumes/{rid}/confirm", json={"edits": edits}, headers=h)
    assert r.status_code == 200, r.text
    ev = {(slug, src): st for slug, src, st, act, ver in _evidence(env, cid)}
    assert ("pytest", "resume") not in ev and ev[("pytest", "self")] == 0.15
    assert ev[("python", "resume")] == 0.40  # 12 мес ровно в новом опыте
    assert ev[("docker", "resume")] == 0.25  # привязка к опыту убрана правкой

    async def rows(s):
        from app.candidates.models import Candidate

        ed = await s.scalar(select(func.count()).select_from(Education))
        return ed, (await s.get(Candidate, cid))

    ed, cand = _run(env, rows)
    assert ed == 0 and cand.experience_months == 12 and cand.claimed_soft == ["Communication"]


def test_confirm_unknown_added_skill_422_and_not_parsed_409(env):
    h = _user(env, "a@x.io")
    rid = _upload(env, h).json()["resume_id"]
    assert env.post(f"/candidates/me/resumes/{rid}/confirm", json={}, headers=h).status_code == 409
    rid, cid = _parsed_resume(env, h)
    r = env.post(
        f"/candidates/me/resumes/{rid}/confirm", json={"edits": {"add_skills": ["nope"]}}, headers=h
    )
    assert r.status_code == 422 and r.json()["code"] == "unknown_skill"
    assert _evidence(env, cid) == []  # ничего не записано
    assert env.get(f"/candidates/me/resumes/{rid}", headers=h).json()["status"] == "parsed"


def test_confirm_twice_is_noop_and_late_result_ignored(env):
    import uuid

    h = _user(env, "a@x.io")
    rid, cid = _parsed_resume(env, h)
    assert env.post(f"/candidates/me/resumes/{rid}/confirm", json={}, headers=h).status_code == 200
    before = _evidence(env, cid)

    async def n(s):
        return await s.scalar(select(func.count()).select_from(OutboxRecord))

    count = _run(env, n)
    assert env.post(f"/candidates/me/resumes/{rid}/confirm", json={}, headers=h).status_code == 200
    assert _evidence(env, cid) == before and _run(env, n) == count
    # запоздавший результат не откатывает подтверждённое резюме
    _deliver(env, uuid.UUID(rid), cid, error="llm_timeout")
    assert env.get(f"/candidates/me/resumes/{rid}", headers=h).json()["status"] == "confirmed"


def test_new_confirmed_resume_replaces_old_evidence(env):
    h = _user(env, "a@x.io")
    rid1, cid = _parsed_resume(env, h)
    env.post(f"/candidates/me/resumes/{rid1}/confirm", json={}, headers=h)
    small = _parsed()
    small.skills = [s for s in small.skills if s.slug == "python"]
    rid2, _ = _parsed_resume(env, h, small)
    env.post(f"/candidates/me/resumes/{rid2}/confirm", json={}, headers=h)
    active = {slug for slug, src, st, act, ver in _evidence(env, cid) if act}
    assert active == {"python"}
