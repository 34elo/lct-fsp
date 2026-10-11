"""Вкладка «Данные» профиля и правило ФИО/скрытых навыков в карточке работодателя.

Ссылки и скрытые навыки — `PATCH /candidates/me/profile`; образование и черновик резюме — в
`GET /candidates/me/profile`; ФИО работодателю — после приглашения (или по `visibility.full_name`).
"""

import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import test_search as ts
from app.candidates import pii
from app.config import Settings
from test_search import NOW, _cand, _card, _search

c = ts.c
market = ts.market
FULL_NAME = "Сидоров Скрытый Олег"


def _owner(c, email="owner@x.ru"):
    r = c.post("/auth/register", json={"email": email, "password": ts.PWD, "role": "candidate"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    body = {"consents": [{"type": "pd_processing", "granted": True}]}
    assert c.put("/me/consents", json=body, headers=h).status_code == 200
    assert c.get("/candidates/me/profile", headers=h).status_code == 200  # анкета создана
    with sqlite3.connect(c.db) as con:
        (uid,) = con.execute("select id from users where email=?", (email,)).fetchone()
    return h, uid


def test_links_and_hidden_skills_roundtrip(c):
    h, _ = _owner(c)
    body = {
        "links": ["https://github.com/someone", "https://github.com/someone", "https://x.dev/cv"],
        "hidden_skills": ["kafka", "python", "kafka"],
    }
    r = c.patch("/candidates/me/profile", json=body, headers=h)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["links"] == ["https://github.com/someone", "https://x.dev/cv"]
    assert p["hidden_skills"] == ["kafka", "python"]
    with sqlite3.connect(c.db) as con:
        (blob,) = con.execute("select links_enc from candidates").fetchone()
    assert blob and b"github" not in bytes(blob)  # ссылки в БД зашифрованы
    cleared = c.patch(
        "/candidates/me/profile", json={"links": None, "hidden_skills": []}, headers=h
    )
    assert cleared.json()["links"] == [] and cleared.json()["hidden_skills"] == []


@pytest.mark.parametrize("link", ["javascript:alert(1)", "github.com/x", "https://a b"])
def test_bad_link_is_422(c, link):
    h, _ = _owner(c)
    assert c.patch("/candidates/me/profile", json={"links": [link]}, headers=h).status_code == 422


def test_profile_has_education_and_resume_draft(c):
    h, uid = _owner(c)
    assert c.get("/candidates/me/profile", headers=h).json()["resume_draft_id"] is None
    rid = uuid.uuid4()
    with sqlite3.connect(c.db) as con:
        con.execute(
            "insert into education (id, candidate_id, institution, degree, field, year_end)"
            " values (?,?,?,?,?,?)",
            (uuid.uuid4().hex, uid, "МГТУ", "бакалавр", "ИВТ", 2022),
        )
        con.execute(
            "insert into resumes (id, candidate_id, file_key, sha256, mime, status, created_at)"
            " values (?,?,?,?,?,?,?)",
            (rid.hex, uid, "k", "s", "application/pdf", "parsed", NOW),
        )
    p = c.get("/candidates/me/profile", headers=h).json()
    assert p["education"] == [
        {"institution": "МГТУ", "degree": "бакалавр", "field": "ИВТ", "year_end": 2022}
    ]
    assert p["resume_draft_id"] == str(rid)
    with sqlite3.connect(c.db) as con:  # подтверждённое резюме — уже не черновик
        con.execute("update resumes set status='confirmed'")
    assert c.get("/candidates/me/profile", headers=h).json()["resume_draft_id"] is None


def test_owner_skills_carry_skill_type(c):
    h, uid = _owner(c)
    with sqlite3.connect(c.db) as con:
        con.execute("update skills set skill_type='hard' where slug='python'")
        con.execute(
            "insert into candidate_skills (candidate_id, skill_id, confidence, level, sources,"
            " top_evidence, claimed_only) values (?,?,0.8,3,'[\"test\"]','[]',0)",
            (uid, c.skills["python"]),
        )
    (skill,) = c.get("/candidates/me/profile", headers=h).json()["skills"]
    assert skill["skill"]["type"] == "hard"


def _offer(c, market, uid, *, interest_only=False):
    with sqlite3.connect(c.db) as con:
        (emp,) = con.execute("select id from users where email='e@x.ru'").fetchone()
        now = datetime.now(UTC)
        con.execute(
            "insert into offers (id, company_id, created_by, candidate_id, salary_from, salary_to,"
            " salary_basis, initiator, status, below_candidate_min, expires_at, interest_at,"
            " created_at) values (?,?,?,?,?,?,?,?,?,0,?,?,?)",
            (uuid.uuid4().hex, market["company_id"].replace("-", ""), emp, uid, 200_000, 300_000,
             "gross", "employer", "interest" if interest_only else "sent",
             (now + timedelta(days=1)).isoformat(sep=" "),
             now.isoformat(sep=" ") if interest_only else None, now.isoformat(sep=" ")),
        )  # fmt: skip


def test_full_name_hidden_from_employer_until_invitation(c, market):
    uid = _cand(c, 70, [("python", 0.8, 3, ["test"])])
    with sqlite3.connect(c.db) as con:
        con.execute(
            "update candidates set full_name_enc=? where user_id=?",
            (pii.encrypt_text(Settings().pii_key, FULL_NAME), uid),
        )
    r = _card(c, market, "pid0070")
    assert r.status_code == 200 and r.json()["full_name"] is None and FULL_NAME not in r.text
    _offer(c, market, uid, interest_only=True)  # интерес — ещё не приглашение
    assert _card(c, market, "pid0070").json()["full_name"] is None
    _offer(c, market, uid)
    assert _card(c, market, "pid0070").json()["full_name"] == FULL_NAME
    other = ts._employer(c, "other@x.ru", name="Other Co")  # другая компания ФИО не видит
    assert _card(c, other, "pid0070").json()["full_name"] is None
    item = next(i for i in _search(c, market).json()["items"] if i["pseudo_id"] == "pid0070")
    assert FULL_NAME not in json.dumps(item, ensure_ascii=False)  # в выдаче ФИО нет никогда


def test_hidden_skill_not_shown_to_employer(c, market):
    uid = _cand(c, 71, [("python", 0.8, 3, ["test"]), ("kafka", 0.6, 2, ["resume"])])
    with sqlite3.connect(c.db) as con:
        con.execute(
            "update candidates set hidden_skills=?, primary_stack=? where user_id=?",
            (json.dumps(["kafka"]), json.dumps(["python", "kafka"]), uid),
        )
    card = _card(c, market, "pid0071").json()
    assert [s["skill"]["slug"] for s in card["skills"]] == ["python"]
    item = next(i for i in _search(c, market).json()["items"] if i["pseudo_id"] == "pid0071")
    assert [s["slug"] for s in item["top_skills"]] == ["python"]
    assert item["primary_stack"] == ["python"]


class _Storage:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    async def ensure_bucket(self):
        return None

    async def put(self, key, data, content_type="application/octet-stream"):
        self.files[key] = data

    async def get(self, key):
        return self.files[key]

    async def delete(self, key):
        self.files.pop(key, None)


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_candidate_avatar_hidden_until_invitation(c, market):
    """Аватар работодателю — только после приглашения; подпись в адресе, чужой 404."""
    c.app.state.storage = _Storage()
    h, uid = _owner(c, "ava@x.ru")
    with sqlite3.connect(c.db) as con:
        con.execute(
            "update candidates set pseudo_id='pid0080', pseudonym='Backend #80',"
            " primary_role='backend', grade='middle', search_status='open',"
            " primary_stack='[\"python\"]' where user_id=?",
            (uid,),
        )
        con.execute(
            "insert into consents (user_id, type, version, granted_at) values (?,?,?,?)",
            (uid, "profile_publication", "2025-09-01", NOW),
        )
        ts._grade(con, uid, "backend", ts.TEST_GRADE["middle"])
    # проверка по сигнатуре, а не по имени и типу
    bad = {"file": ("a.png", b"<svg onload=alert(1)>", "image/png")}
    assert c.put("/candidates/me/avatar", files=bad, headers=h).status_code == 415
    big = {"file": ("b.png", PNG + b"\x00" * (2 * 1024 * 1024), "image/png")}
    assert c.put("/candidates/me/avatar", files=big, headers=h).status_code == 413
    r = c.put("/candidates/me/avatar", files={"file": ("a.png", PNG, "image/png")}, headers=h)
    assert r.status_code == 200, r.text
    url = r.json()["avatar_url"]
    assert url.startswith("/candidates/pid0080/avatar?v=") and "&sig=" in url
    assert c.get(url).content == PNG
    assert c.get(url.split("&sig=")[0] + "&sig=" + "0" * 32).status_code == 404
    assert c.get("/candidates/pid0080/avatar?sig=x").status_code == 404
    assert c.get("/me", headers=h).json()["avatar_url"] == url

    # работодатель: до приглашения аватара нет (ни в карточке, ни в выдаче)
    assert _card(c, market, "pid0080").json()["avatar_url"] is None
    item = [i for i in _search(c, market).json()["items"] if i["pseudo_id"] == "pid0080"]
    assert not item or "avatar_url" not in item[0]
    _offer(c, market, uid, interest_only=True)
    assert _card(c, market, "pid0080").json()["avatar_url"] is None
    _offer(c, market, uid)
    shown = _card(c, market, "pid0080").json()["avatar_url"]
    assert shown == url and c.get(shown).status_code == 200
    other = ts._employer(c, "other2@x.ru", name="Other Co")  # другая компания не видит
    assert _card(c, other, "pid0080").json()["avatar_url"] is None

    # замена: старая ссылка перестаёт работать, файл один
    jpg = b"\xff\xd8\xff\xe0" + b"\x01" * 32
    r2 = c.put("/candidates/me/avatar", files={"file": ("p.jpg", jpg, "image/jpeg")}, headers=h)
    assert r2.json()["avatar_url"] != url and len(c.app.state.storage.files) == 1
    assert c.get(url).status_code == 404
    assert c.delete("/candidates/me/avatar", headers=h).json()["avatar_url"] is None
    assert c.app.state.storage.files == {}
