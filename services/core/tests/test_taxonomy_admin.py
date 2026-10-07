"""E13-1a: admin справочника — профессии, веса, карточки навыков."""

import sqlite3
import uuid
from pathlib import Path

import pytest
import yaml
from app.taxonomy import service
from app.taxonomy.cards import CARDS_DIR
from app.taxonomy.loader import load_taxonomy
from core_helpers import PASSWORD, register
from fsp_platform.db import make_engine, make_session_factory, session_scope

TAXONOMY = Path(__file__).resolve().parents[3] / "data" / "taxonomy"


@pytest.fixture
async def seeded(db_url):
    engine = make_engine(db_url)
    async with session_scope(make_session_factory(engine)) as s:
        await service.sync(s, load_taxonomy(TAXONOMY))
    await engine.dispose()


def _admin(api) -> dict[str, str]:
    email = f"root-{uuid.uuid4().hex[:6]}@example.test"
    r = api.post("/auth/register", json={"email": email, "password": PASSWORD, "role": "candidate"})
    with sqlite3.connect(api.db_path) as con:
        con.execute("update users set role='fsp_admin' where email=?", (email,))
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _events(api) -> list[int]:
    with sqlite3.connect(api.db_path) as con:
        rows = con.execute("select payload from outbox where type='taxonomy.updated'").fetchall()
    import json

    return [json.loads(p)["payload"]["version"] for (p,) in rows]


def test_roles_required(api, seeded):
    cand = register(api)
    for method, url in [
        ("get", "/admin/professions"),
        ("post", "/admin/professions"),
        ("get", "/admin/skill-cards"),
        ("put", "/admin/skill-cards/sql"),
    ]:
        assert getattr(api, method)(url).status_code == 401
        assert getattr(api, method)(url, headers=cand).status_code == 403


def _weights(api, adm, slug="backend") -> dict[str, float]:
    return api.get(f"/admin/professions/{slug}", headers=adm).json()["skill_weights"]


def test_profession_crud_bumps_version(api, seeded):
    adm = _admin(api)
    profs = api.get("/admin/professions", headers=adm).json()
    assert "backend" in {p["slug"] for p in profs}
    assert api.get("/admin/professions/nope", headers=adm).status_code == 404
    assert api.patch("/admin/professions/nope", json={"title": "X"}, headers=adm).status_code == 404

    w = _weights(api, adm)
    # неизвестный навык, вес вне диапазона, нет типов — отказ без изменений
    r = api.post(
        "/admin/professions",
        json={"slug": "ghost", "title": "Ghost", "skill_weights": {"no-such": 0.5}},
        headers=adm,
    )
    assert r.status_code == 422 and r.json()["code"] == "unknown_skill"
    bad = dict(w, **{next(iter(w)): 1.5})
    r = api.post(
        "/admin/professions",
        json={"slug": "ghost", "title": "G", "skill_weights": bad},
        headers=adm,
    )
    assert r.json()["code"] == "invalid_weight"
    one = {next(iter(w)): 0.5}
    r = api.post(
        "/admin/professions",
        json={"slug": "ghost", "title": "G", "skill_weights": one},
        headers=adm,
    )
    assert r.json()["code"] == "missing_skill_types"
    r = api.post(
        "/admin/professions",
        json={"slug": "Bad Slug", "title": "G", "skill_weights": w},
        headers=adm,
    )
    assert r.status_code == 422
    assert [p["slug"] for p in api.get("/admin/professions", headers=adm).json()].count(
        "ghost"
    ) == 0

    before = len(_events(api))
    r = api.post(
        "/admin/professions",
        json={"slug": "ghost", "title": "Призрак", "skill_weights": w},
        headers=adm,
    )
    assert r.status_code == 201 and r.json()["skill_weights"] == w
    v1 = r.json()["taxonomy_version"]
    assert len(_events(api)) == before + 1 and _events(api)[-1] == v1
    r = api.post(
        "/admin/professions", json={"slug": "ghost", "title": "G", "skill_weights": w}, headers=adm
    )
    assert r.status_code == 409 and r.json()["code"] == "profession_exists"
    assert (
        api.post(  # непрофессиональная роль тоже занята
            "/admin/professions",
            json={"slug": "backend", "title": "G", "skill_weights": w},
            headers=adm,
        ).status_code
        == 409
    )

    # публичный каталог видит новую профессию
    assert "ghost" in {p["slug"] for p in api.get("/taxonomy/professions").json()["professions"]}

    # правка веса и названия
    slug0 = next(iter(w))
    w2 = dict(w, **{slug0: 0.11})
    r = api.patch(
        "/admin/professions/ghost", json={"title": "Новое", "skill_weights": w2}, headers=adm
    )
    assert r.status_code == 200 and r.json()["title"] == "Новое"
    assert r.json()["skill_weights"][slug0] == 0.11 and r.json()["taxonomy_version"] == v1 + 1
    # повтор без изменений — версия не растёт
    r = api.patch("/admin/professions/ghost", json={"skill_weights": w2}, headers=adm)
    assert r.json()["taxonomy_version"] == v1 + 1 and len(_events(api)) == before + 2
    assert api.get("/taxonomy/professions").json()["professions"]  # не сломан

    # снятие профессии
    r = api.delete("/admin/professions/ghost", headers=adm)
    assert r.status_code == 200 and r.json()["taxonomy_version"] == v1 + 2
    assert api.delete("/admin/professions/ghost", headers=adm).status_code == 404
    assert "ghost" not in {p["slug"] for p in api.get("/admin/professions", headers=adm).json()}


def _card_doc(slug: str) -> dict:
    return yaml.safe_load((CARDS_DIR / f"{slug}.yaml").read_text(encoding="utf-8"))


def test_cards_list_get_put(api, seeded):
    adm = _admin(api)
    refs = {c["skill"]: c for c in api.get("/admin/skill-cards", headers=adm).json()}
    assert refs, "в data/skills/cards есть карточки"
    slug = next(s for s, c in refs.items() if c["source"] == "file")
    got = api.get(f"/admin/skill-cards/{slug}", headers=adm).json()
    assert got["source"] == "file" and got["version"] == 0 and got["card"]["skill"] == slug
    assert api.get("/admin/skill-cards/no-such", headers=adm).status_code == 404

    doc = got["card"]
    doc["summary"] = "Обновлённое описание навыка для проверки."
    before = len(_events(api))
    r = api.put(f"/admin/skill-cards/{slug}", json=doc, headers=adm)
    assert r.status_code == 200 and r.json()["source"] == "admin" and r.json()["version"] == 1
    v = r.json()["taxonomy_version"]
    assert len(_events(api)) == before + 1 and _events(api)[-1] == v
    assert (
        api.get(f"/admin/skill-cards/{slug}", headers=adm).json()["card"]["summary"]
        == doc["summary"]
    )
    # то же содержимое — без новой версии
    r = api.put(f"/admin/skill-cards/{slug}", json=doc, headers=adm)
    assert r.json()["version"] == 1 and r.json()["taxonomy_version"] == v
    assert len(_events(api)) == before + 1
    doc["summary"] = "Ещё одно описание навыка, версия два."
    assert api.put(f"/admin/skill-cards/{slug}", json=doc, headers=adm).json()["version"] == 2

    # отказы
    other = dict(doc, skill="python")
    r = api.put(f"/admin/skill-cards/{slug}", json=other, headers=adm)
    assert r.json()["code"] == "card_skill_mismatch"
    wrong = dict(doc, type="soft" if doc["type"] != "soft" else "hard")
    assert api.put(f"/admin/skill-cards/{slug}", json=wrong, headers=adm).json()["code"] == (
        "card_type_mismatch"
    )
    assert (
        api.put(f"/admin/skill-cards/{slug}", json=dict(doc, concepts=[]), headers=adm).status_code
        == 422
    )
    assert api.put("/admin/skill-cards/no-such", json=doc, headers=adm).status_code == 404


def test_hidden_professions_admin_sees_all_and_toggles(api, seeded):
    """E36-2 (ADR-027 п. 1): скрытые профессии — у админа с `active=false`, публично их нет."""
    adm = _admin(api)
    profs = {p["slug"]: p["active"] for p in api.get("/admin/professions", headers=adm).json()}
    assert {s for s, a in profs.items() if not a} == {"ml", "mobile", "devops", "qa"}

    def public() -> set[str]:
        return {p["slug"] for p in api.get("/taxonomy/professions").json()["professions"]}

    assert public() == {"backend", "frontend", "ai_engineer"}
    r = api.patch("/admin/professions/ml", json={"active": True}, headers=adm)
    assert r.status_code == 200 and r.json()["active"] is True
    assert "ml" in public()
    r = api.patch("/admin/professions/ml", json={"active": False}, headers=adm)
    assert r.json()["active"] is False and "ml" not in public()
    assert api.get("/admin/professions/ml", headers=adm).json()["skill_weights"]  # данные целы
