"""Карточка работодателя по настройкам видимости.

Скрытое поле не уходит в ответ API ни в одной комбинации настроек; контакты — никогда.
"""

import itertools
import json
import sqlite3
import uuid
from datetime import UTC, datetime

import pytest
import test_search as ts
from app.candidates import pii
from app.config import Settings
from test_search import _cand, _card, _search

c = ts.c  # фикстуры поиска: БД с миграциями и рынок
market = ts.market

FULL_NAME = "Иванов Тайный Иван"
COMPANY = "СекретнаяКомпанияХ"
CITY = "СекретныйГородЯ"
FSP_LABEL = "СекретныйКубокФСП"
CONTACT_MARKS = ("tajny@mail.test", "+7 900 111-22-33", "@tajny_tg")
KEYS = ("full_name", "companies", "fsp", "region")
COMBOS = list(itertools.product((False, True), repeat=len(KEYS)))


def _prepare(c, n):
    uid = _cand(c, n, [("python", 0.8, 3, ["fsp", "test"])], city=CITY)
    key = Settings().pii_key
    ev = uuid.uuid4().hex
    day = datetime.now(UTC).date().isoformat()
    with sqlite3.connect(c.db) as con:
        con.execute(
            "insert into evidence (id, candidate_id, skill_id, source, strength, observed_at,"
            " fact_type, fact_id, details, verified, is_active) values (?,?,?,?,?,?,?,?,?,1,1)",
            (ev, uid, c.skills["python"], "fsp", 0.9, day, "fsp_result", uuid.uuid4().hex,
             json.dumps({"label": FSP_LABEL, "level": "federal", "place": 1, "participants": 50})),
        )  # fmt: skip
        con.execute(
            "update candidate_skills set top_evidence=? where candidate_id=?",
            (json.dumps([ev]), uid),
        )
        con.execute(
            "insert into experience (id, candidate_id, company, title, start_date, skill_ids,"
            " is_commercial, source) values (?,?,?,?,?,'[]',1,'resume')",
            (uuid.uuid4().hex, uid, COMPANY, "Dev", "2023-01-01"),
        )
        contacts = pii.encrypt_contacts(
            key,
            {"email": CONTACT_MARKS[0], "phone": CONTACT_MARKS[1], "telegram": CONTACT_MARKS[2]},
        )
        con.execute(
            "update candidates set full_name_enc=?, contacts_enc=? where user_id=?",
            (pii.encrypt_text(key, FULL_NAME), contacts, uid),
        )
    return uid


def _set(c, uid, vis):
    with sqlite3.connect(c.db) as con:
        con.execute("update candidates set visibility=? where user_id=?", (json.dumps(vis), uid))


@pytest.mark.parametrize("combo", COMBOS)
def test_hidden_field_never_in_card_or_search(c, market, combo):
    uid = _prepare(c, 60)
    vis = dict(zip(KEYS, combo, strict=True))
    _set(c, uid, vis)
    full = _card(c, market, "pid0060")
    assert full.status_code == 200, full.text
    texts = {"card": full.text}
    r = _search(c, market)
    (item,) = [i for i in r.json()["items"] if i["pseudo_id"] == "pid0060"]
    texts["search"] = json.dumps(item, ensure_ascii=False)
    body = full.json()
    for where, text in texts.items():
        assert (CITY in text) is vis["region"], where
        assert (FSP_LABEL in text) is vis["fsp"], where
        assert ('"fsp"' in text) is vis["fsp"], where  # источник «fsp» в навыках и доказательствах
        for mark in CONTACT_MARKS:  # контактов нет ни в одной комбинации
            assert mark not in text, where
    assert (COMPANY in full.text) is vis["companies"]
    assert (FULL_NAME in full.text) is vis["full_name"]
    assert body["full_name"] == (FULL_NAME if vis["full_name"] else None)
    assert FULL_NAME not in texts["search"] and COMPANY not in texts["search"]
    assert "contacts" not in body and "email" not in full.text


def test_fsp_hidden_removes_grade_signals_and_strength_term(c, market):
    uid = _prepare(c, 61)
    with sqlite3.connect(c.db) as con:
        con.execute(
            "update candidates set grade_breakdown=? where user_id=?",
            (json.dumps([{"signal": "fsp_achievement", "points": 2.0, "evidence_ids": []},
                         {"signal": "tests", "points": 1.0, "evidence_ids": []}]), uid),
        )  # fmt: skip
    _set(c, uid, {"fsp": True})
    shown = [b["signal"] for b in _card(c, market, "pid0061").json()["grade_info"]["breakdown"]]
    assert shown == ["fsp_achievement", "tests"]
    _set(c, uid, {"fsp": False})
    body = _card(c, market, "pid0061").json()
    assert [b["signal"] for b in body["grade_info"]["breakdown"]] == ["tests"]
    assert all(p["code"] != "F" for p in (body["strength"] or {}).get("top", []))


def test_full_name_owner_roundtrip_and_erase(c):
    r = c.post("/auth/register", json={"email": "cand@x.ru", "password": "correct-horse-battery",
                                       "role": "candidate"})  # fmt: skip
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    body = {"consents": [{"type": "pd_processing", "granted": True}]}
    assert c.put("/me/consents", json=body, headers=h).status_code == 200
    p = c.patch("/candidates/me/profile", json={"full_name": "  Петров   Пётр "}, headers=h)
    assert p.status_code == 200, p.text
    assert p.json()["full_name"] == "Петров Пётр"
    with sqlite3.connect(c.db) as con:
        (blob,) = con.execute("select full_name_enc from candidates").fetchone()
    assert blob and b"\xd0" not in bytes(blob)  # в БД шифртекст, не открытое ФИО
    assert (
        c.patch("/candidates/me/profile", json={"full_name": ""}, headers=h).json()["full_name"]
        is None
    )
