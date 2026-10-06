"""E16-7: REST `/admin/skills/*` — очередь слияний, откат, «точно разные», стоп-лист, рост."""

import json
import sqlite3
import uuid
from pathlib import Path

import pytest
from app.taxonomy import decisions, service
from app.taxonomy.loader import load_taxonomy
from app.taxonomy.models import ScoringConfig, Skill, SkillCardDraftRow
from core_helpers import PASSWORD, register
from fsp_platform.db import make_engine, make_session_factory, session_scope
from sqlalchemy import select

TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"
PG = {
    "raw": "Postgres SQL",
    "norm": "postgres sql",
    "kind": "hard",
    "decision": "same_pending",
    "skill_slug": "postgres-sql",
    "relation": {"type": "same", "to_slug": "postgresql", "confidence": 0.8},
}
CARD = {
    "schema_version": 1,
    "skill": "postgres-sql",
    "type": "hard",
    "summary": "Диалект SQL для PostgreSQL.",
    "levels": {
        "junior": ["Пишет запросы", "Делает JOIN"],
        "middle": ["Читает план", "Подбирает индексы"],
        "senior": ["Проектирует схему", "Разбирает блокировки"],
    },
    "concepts": [
        {"term": "Индекс", "note": "структура поиска"},
        {"term": "План", "note": "порядок выполнения"},
        {"term": "JOIN", "note": "соединение таблиц"},
    ],
    "misconceptions": [
        {"claim": "Больше индексов быстрее", "truth": "каждый замедляет запись"},
        {"claim": "NULL равен NULL", "truth": "сравнение неизвестно"},
    ],
}


@pytest.fixture
async def seeded(db_url):
    engine = make_engine(db_url)
    async with session_scope(make_session_factory(engine)) as s:
        await service.sync(s, load_taxonomy(TAXONOMY))
        await decisions.apply_decisions(s, [PG])
        sk = await s.scalar(select(Skill).where(Skill.slug == "postgres-sql"))
        s.add(SkillCardDraftRow(skill_id=sk.id, card=CARD, model="fake"))
    await engine.dispose()


def _admin(api) -> dict[str, str]:
    email = f"root-{uuid.uuid4().hex[:6]}@example.test"
    r = api.post("/auth/register", json={"email": email, "password": PASSWORD, "role": "candidate"})
    with sqlite3.connect(api.db_path) as con:
        con.execute("update users set role='fsp_admin' where email=?", (email,))
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _versions(api) -> list[int]:
    with sqlite3.connect(api.db_path) as con:
        rows = con.execute("select payload from outbox where type='taxonomy.updated'").fetchall()
    return [json.loads(p)["payload"]["version"] for (p,) in rows]


def test_roles_required(api, seeded):
    cand = register(api)
    for method, url in [
        ("get", "/admin/skills/queue"),
        ("post", "/admin/skills/queue/postgres-sql/approve"),
        ("get", "/admin/skills/merges"),
        ("post", f"/admin/skills/merges/{uuid.uuid4()}/revert"),
        ("get", "/admin/skills/distinct"),
        ("get", "/admin/skills/blocklist"),
        ("get", "/admin/skills/provisional"),
        ("get", "/admin/skills/hints"),
    ]:
        assert getattr(api, method)(url).status_code == 401
        assert getattr(api, method)(url, headers=cand).status_code == 403


def test_queue_preview_approve_and_revert(api, seeded):
    adm = _admin(api)
    q = api.get("/admin/skills/queue", headers=adm).json()
    assert [i["skill"] for i in q] == ["postgres-sql"]
    assert q[0]["into"] == "postgresql" and q[0]["from"]["status"] == "provisional"
    assert "postgres sql" in q[0]["preview"]["aliases"]

    before = len(_versions(api))
    r = api.post("/admin/skills/queue/postgres-sql/approve", headers=adm)
    assert r.status_code == 200, r.text
    mid = r.json()["id"]
    assert len(_versions(api)) > before
    assert api.get("/admin/skills/queue", headers=adm).json() == []
    # повторно — в очереди уже нет
    assert api.post("/admin/skills/queue/postgres-sql/approve", headers=adm).status_code == 404

    rows = api.get("/admin/skills/merges", headers=adm).json()
    assert rows[0]["id"] == mid and rows[0]["reverted_at"] is None
    assert rows[0]["into_skill"] == "postgresql" and rows[0]["actor"].startswith("admin:")

    v = _versions(api)
    assert api.post(f"/admin/skills/merges/{mid}/revert", headers=adm).status_code == 200
    assert len(_versions(api)) > len(v)
    assert api.get("/admin/skills/merges", headers=adm).json()[0]["reverted_at"]
    assert api.post(f"/admin/skills/merges/{mid}/revert", headers=adm).status_code == 409
    assert api.post(f"/admin/skills/merges/{uuid.uuid4()}/revert", headers=adm).status_code == 404


def test_queue_reject_optionally_marks_distinct(api, seeded):
    adm = _admin(api)
    r = api.post(
        "/admin/skills/queue/postgres-sql/reject", json={"mark_distinct": True}, headers=adm
    )
    assert r.status_code == 200
    assert api.get("/admin/skills/queue", headers=adm).json() == []
    pairs = api.get("/admin/skills/distinct", headers=adm).json()
    assert frozenset(("postgres-sql", "postgresql")) in {frozenset((p["a"], p["b"])) for p in pairs}
    # слить такую пару нельзя
    r = api.post(
        "/admin/skills/merge", json={"from": "postgres-sql", "into": "postgresql"}, headers=adm
    )
    assert r.status_code == 409 and r.json()["code"] == "merge_forbidden_distinct"
    assert api.post("/admin/skills/queue/ghost/reject", headers=adm).status_code == 404


def test_manual_merge_and_guards(api, seeded):
    adm = _admin(api)
    r = api.post("/admin/skills/merge", json={"from": "nope", "into": "sql"}, headers=adm)
    assert r.status_code == 404
    r = api.post("/admin/skills/merge", json={"from": "sql", "into": "sql"}, headers=adm)
    assert r.status_code == 422
    r = api.post(
        "/admin/skills/merge", json={"from": "postgres-sql", "into": "postgresql"}, headers=adm
    )
    assert r.status_code == 201 and r.json()["taxonomy_version"] >= 1


def test_distinct_crud(api, seeded):
    adm = _admin(api)
    body = {"a": "python", "b": "postgresql"}
    v0 = len(_versions(api))
    r = api.post("/admin/skills/distinct", json=body, headers=adm)
    assert r.status_code == 200 and r.json()["changed"] is True
    assert api.post("/admin/skills/distinct", json=body, headers=adm).json()["changed"] is False
    pairs = api.get("/admin/skills/distinct", headers=adm).json()
    assert frozenset(("postgresql", "python")) in {frozenset((p["a"], p["b"])) for p in pairs}
    assert (
        api.post(
            "/admin/skills/distinct", json={"a": "python", "b": "python"}, headers=adm
        ).status_code
        == 422
    )
    assert (
        api.post(
            "/admin/skills/distinct", json={"a": "python", "b": "ghost"}, headers=adm
        ).status_code
        == 404
    )
    assert (
        api.delete("/admin/skills/distinct?a=python&b=postgresql", headers=adm).status_code == 200
    )
    assert (
        api.delete("/admin/skills/distinct?a=postgresql&b=python", headers=adm).status_code == 404
    )
    pairs = api.get("/admin/skills/distinct", headers=adm).json()
    assert frozenset(("postgresql", "python")) not in {frozenset((p["a"], p["b"])) for p in pairs}
    assert len(_versions(api)) > v0  # правки версию поднимают как в decisions.py


def test_blocklist_crud(api, seeded):
    adm = _admin(api)
    r = api.post(
        "/admin/skills/blocklist", json={"norm": "Ёлки  Палки", "reason": "мусор"}, headers=adm
    )
    assert r.status_code == 200 and r.json()["norm"] == "елки палки"
    assert (
        api.post("/admin/skills/blocklist", json={"norm": "елки палки"}, headers=adm).status_code
        == 409
    )
    assert [b["norm"] for b in api.get("/admin/skills/blocklist", headers=adm).json()] == [
        "елки палки"
    ]
    assert api.delete("/admin/skills/blocklist?norm=елки палки", headers=adm).status_code == 204
    assert api.delete("/admin/skills/blocklist?norm=елки палки", headers=adm).status_code == 404


def test_provisional_list_approve_reject_and_hints(api, seeded, db_url):
    adm = _admin(api)
    rows = api.get("/admin/skills/provisional", headers=adm).json()
    assert [r["slug"] for r in rows] == ["postgres-sql"]
    assert rows[0]["draft"]["summary"].startswith("Диалект")
    assert api.post("/admin/skills/ghost/approve", headers=adm).status_code == 404
    assert api.post("/admin/skills/postgres-sql/approve", headers=adm).json()["status"] == "active"
    assert api.post("/admin/skills/postgres-sql/reject", headers=adm).status_code == 409
    assert api.get("/admin/skills/provisional", headers=adm).json() == []

    assert api.get("/admin/skills/hints", headers=adm).json() == {
        "updated_at": None,
        "discipline_rules": [],
        "profession_candidates": [],
    }
    hints = {
        "updated_at": "2026-10-01T00:00:00+00:00",
        "discipline_rules": [
            {
                "discipline": "algo",
                "discipline_name": "Алгоритмы",
                "skill": "sql",
                "lift": 2.5,
                "support": 12,
            }
        ],
        "profession_candidates": [
            {"skills": ["sql", "python"], "support": 7, "covered_by_professions": 0.1}
        ],
    }
    with sqlite3.connect(api.db_path) as con:
        con.execute(
            "insert into scoring_config(key, value, version, updated_at) "
            "values('taxonomy_hints', ?, 1, '2026-10-01')",
            (json.dumps(hints),),
        )
    assert api.get("/admin/skills/hints", headers=adm).json() == hints
    assert ScoringConfig  # модель подключена
