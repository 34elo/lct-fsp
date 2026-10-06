"""F13: DELETE /candidates/me — удаление профиля по 152-ФЗ."""

import uuid

from app.candidates.models import Candidate
from app.graph.models import CandidateSkill, Evidence
from app.identity.models import EmailVerification, RefreshToken, User
from app.resumes.models import Education, Experience, Resume
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import func, select
from test_candidate_profile_form import PWD, _patch, _q, _user, c  # noqa: F401


class _Storage:
    def __init__(self, fail: bool = False):
        self.deleted: list[str] = []
        self.fail = fail

    async def delete(self, key: str) -> None:
        if self.fail:
            raise OSError("down")
        self.deleted.append(key)


def _fill(c, uid):  # noqa: F811
    async def go(s):
        cand = await s.get(Candidate, uid)
        cand.primary_role, cand.grade, cand.city = "backend", "middle", "Казань"
        s.add(Resume(id=uuid.uuid4(), candidate_id=uid, file_key="k1", sha256="x", mime="a/b"))
        s.add(Experience(candidate_id=uid, company="ООО Пример", source="resume"))
        s.add(Education(candidate_id=uid, institution="КФУ"))

    return _q(c, go)


def _uid(c):  # noqa: F811
    return _q(c, lambda s: s.scalar(select(User.id)))


def _prep(c, h):  # noqa: F811
    """Анкета создаётся лениво — открываем профиль."""
    assert c.get("/candidates/me/profile", headers=h).status_code == 200


def _delete(c, h, body=None):  # noqa: F811
    return c.request(
        "DELETE", "/candidates/me", json={"password": PWD} if body is None else body, headers=h
    )


def test_delete_erases_pii_and_is_irreversible(c):  # noqa: F811
    c.app.state.storage = st = _Storage()
    h = _user(c, "del@x.io")
    _patch(c, h, {"contacts": {"email": "del@x.io"}, "stack": [{"slug": "python"}]})
    uid = _uid(c)
    _fill(c, uid)
    assert _q(c, lambda s: s.scalar(select(func.count()).select_from(Evidence))) >= 1

    assert _delete(c, h).status_code == 204
    assert st.deleted == ["k1"]

    async def state(s):
        cand = await s.get(Candidate, uid)
        user = await s.get(User, uid)
        counts = [
            await s.scalar(select(func.count()).select_from(m))
            for m in (Evidence, CandidateSkill, Resume, Experience, Education, EmailVerification)
        ]
        events = (await s.scalars(select(OutboxRecord.type))).all()
        return cand, user, counts, events

    cand, user, counts, events = _q(c, state)
    assert counts == [0] * 6
    assert cand.deleted_at is not None and cand.contacts_enc is None and cand.city is None
    assert cand.grade is None and cand.embedding is None and cand.pseudonym
    assert user.email is None and user.password_hash is None and not user.is_active
    assert events.count("candidate.deleted") == 1
    # токен больше не работает, вход невозможен, email свободен
    assert c.get("/candidates/me/profile", headers=h).status_code == 401
    r = c.post("/auth/login", json={"email": "del@x.io", "password": PWD})
    assert r.status_code == 401
    assert c.post("/auth/register", json={"email": "del@x.io", "password": PWD, "role": "candidate"}
                  ).status_code == 201  # fmt: skip


def test_delete_requires_confirmation(c):  # noqa: F811
    c.app.state.storage = _Storage()
    h = _user(c, "w@x.io")
    _prep(c, h)
    assert _delete(c, h, {}).status_code == 403
    r = _delete(c, h, {"password": "wrong-password-123"})
    assert r.status_code == 403 and r.json()["code"] == "confirmation_failed"
    assert _delete(c, h, {"confirm": "УДАЛИТЬ"}).status_code == 403  # пароль задан — фраза не нужна
    assert _q(c, lambda s: s.scalar(select(Candidate.deleted_at))) is None


def test_repeat_delete_is_404(c):  # noqa: F811
    c.app.state.storage = _Storage()
    h = _user(c, "r@x.io")
    _prep(c, h)
    assert _delete(c, h).status_code == 204
    r = _delete(c, h)
    assert r.status_code == 404 and r.json()["code"] == "candidate_not_found"
    assert _q(c, lambda s: s.scalar(select(func.count()).select_from(RefreshToken))) == 0
    n = _q(c, lambda s: s.scalar(select(func.count()).select_from(OutboxRecord)
                                 .where(OutboxRecord.type == "candidate.deleted")))  # fmt: skip
    assert n == 1


def test_only_own_profile_and_candidate_role(c):  # noqa: F811
    c.app.state.storage = _Storage()
    a, b = _user(c, "a@x.io"), _user(c, "b@x.io")
    _prep(c, a)
    _prep(c, b)
    assert _delete(c, a).status_code == 204
    # профиль B не затронут
    assert c.get("/candidates/me/profile", headers=b).status_code == 200
    assert _q(c, lambda s: s.scalar(select(func.count()).select_from(Candidate)
                                    .where(Candidate.deleted_at.is_(None)))) == 1  # fmt: skip
    r = c.post("/auth/register", json={"email": "e@x.io", "password": PWD, "role": "employer"})
    he = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert _delete(c, he).status_code == 403
    assert c.request("DELETE", "/candidates/me", json={}).status_code == 401


def test_storage_failure_does_not_block_delete(c):  # noqa: F811
    c.app.state.storage = _Storage(fail=True)
    h = _user(c, "s@x.io")
    _prep(c, h)
    _fill(c, _uid(c))
    assert _delete(c, h).status_code == 204
    assert _q(c, lambda s: s.scalar(select(func.count()).select_from(Resume))) == 0


def test_no_password_account_needs_phrase(c):  # noqa: F811
    c.app.state.storage = _Storage()
    h = _user(c, "t@x.io")
    _prep(c, h)

    async def drop(s):
        (await s.scalars(select(User))).one().password_hash = None

    _q(c, drop)
    assert _delete(c, h, {"password": PWD}).status_code == 403
    assert _delete(c, h, {"confirm": "УДАЛИТЬ"}).status_code == 204
