"""Потребности → категории → кандидаты (assessment.md §9, E23-4)."""

import json
import sqlite3

import pytest
import test_search as ts
from app.matching import needs as n
from fsp_contracts.ml import SearchFilters, SkillRequirement

c = ts.c  # фикстура клиента с БД из test_search
_cand, _employer, _hdr = ts._cand, ts._employer, ts._hdr
CFG = n.NeedsConfig()
ROLES = {
    "backend": {"python": 0.7, "fastapi": 0.5, "kafka": 0.3},
    "frontend": {"python": 0.1},
    "ml": {"python": 1.0},
}


def test_affinity_formula_example():
    """Σ min(w_need, w_prof) / Σ w_need: python 1.0, fastapi 1.0 против backend → 0.6."""
    need = {"python": 1.0, "fastapi": 1.0}
    assert n.affinity(need, ROLES["backend"]) == pytest.approx(0.6)
    assert n.affinity(need, ROLES["ml"]) == pytest.approx(0.5)
    assert n.affinity(need, ROLES["frontend"]) == pytest.approx(0.05)
    assert n.affinity({}, ROLES["backend"]) == 0.0
    assert n.affinity({"python": 0.5}, ROLES["ml"]) == 1.0  # вес профессии выше — потолок 1


def test_recommend_threshold_fallback_and_named_role():
    need = {"python": 1.0, "fastapi": 1.0}
    assert n.recommend(need, ROLES, CFG) == [("backend", 0.6), ("ml", 0.5)]
    # ни одна не дотянула до 0.4 → лучшая с affinity > 0
    assert n.recommend({"kafka": 1.0}, ROLES, CFG) == [("backend", 0.3)]
    assert n.recommend({"cobol": 1.0}, ROLES, CFG) == []
    # названная роль идёт в список при низкой affinity
    assert ("frontend", 0.05) in n.recommend(need, ROLES, CFG, roles=["frontend"])


def test_weights_grades_and_median():
    f = SearchFilters(
        skills_must=[SkillRequirement(slug="python")], skills_nice=["kafka", "python"]
    )
    assert n.need_weights(f, CFG) == {"kafka": 0.5, "python": 1.0}
    assert n.need_grades(SearchFilters()) == ["junior", "middle", "senior"]
    assert n.need_grades(SearchFilters(grade_min="junior", grade_max="middle_plus")) == [
        "junior", "middle",
    ]  # fmt: skip
    assert n.need_grades(SearchFilters(grade_min="lead")) == ["senior"]
    assert n.median_salary([100, 200]) is None  # мало данных
    assert n.median_salary([100, 200, 300, None]) == 200


@pytest.fixture
def market(c):
    h = _employer(c, "e@x.ru")
    with sqlite3.connect(c.db) as con:
        for role, weights in ROLES.items():
            con.execute("insert into roles (slug, name) values (?,?)", (role, role.title()))
            for slug, w in weights.items():
                if slug in c.skills:
                    con.execute(
                        "insert into role_skills (role, skill_id, weight, source) values (?,?,?,?)",
                        (role, c.skills[slug], w, "seed"),
                    )
    _cand(c, 1, [("python", 0.9, 4, ["test", "fsp"]), ("fastapi", 0.6, 3, ["github"])],
          grade="senior", salary_min=300_000)  # fmt: skip
    _cand(c, 2, [("python", 0.8, 3, ["test"])], grade="middle", salary_min=200_000)
    _cand(c, 3, [("python", 0.5, 2, ["test"]), ("fastapi", 0.5, 2, ["test"])], grade="middle",
          salary_min=220_000)  # fmt: skip
    _cand(c, 4, [("python", 0.5, 2, ["test"])], grade="middle", salary_min=240_000)
    _cand(c, 5, [("python", 0.7, 3, ["test"])], grade="middle", primary_role="ml")
    _cand(c, 6, [("python", 0.99, 4, ["github"])], search_status="dnd")  # скрыт
    return h


def _create(c, h, **body):
    return c.post("/needs", json=body, headers=_hdr(h))


def _cats(r):
    assert r.status_code in (200, 201), r.text
    return {(x["profession"], x["grade"]): x for x in r.json()["categories"]}


def test_need_by_filters_gives_categories_with_counters(c, market):
    r = _create(c, market, filters={"skills_must": [{"slug": "python"}, {"slug": "fastapi"}]})
    assert r.status_code == 201
    body = r.json()
    assert body["skills"] == {"python": 1.0, "fastapi": 1.0}
    assert body["grades"] == ["junior", "middle", "senior"]
    cats = _cats(r)
    assert set(cats) == {(p, g) for p in ("backend", "ml") for g in ("junior", "middle", "senior")}
    mid = cats[("backend", "middle")]
    assert mid["affinity"] == pytest.approx(0.6) and mid["title"] == "Backend"
    assert mid["candidates"] == 3 and mid["median_salary"] == 220_000
    assert mid["fsp_share"] == 0.0
    assert cats[("backend", "senior")]["fsp_share"] == 1.0  # у пид 1 результат ФСП
    assert cats[("backend", "senior")]["median_salary"] is None  # одна анкета — не показываем
    assert cats[("backend", "junior")]["candidates"] == 0
    assert cats[("backend", "junior")]["fsp_share"] is None
    assert cats[("ml", "middle")]["candidates"] == 1
    assert all(k[0] != "frontend" for k in cats)  # affinity 0.05 < 0.4
    # повторное чтение даёт то же
    again = c.get(f"/needs/{body['id']}/categories", headers=_hdr(market))
    assert again.status_code == 200 and again.json()["categories"] == body["categories"]


def test_need_grade_range_and_attribute_filters(c, market):
    r = _create(c, market, filters={"skills_must": [{"slug": "python"}], "grade_min": "middle",
                                    "grade_max": "senior", "salary_max": 210_000})  # fmt: skip
    cats = _cats(r)
    assert {g for _, g in cats} == {"middle", "senior"}
    # бюджет 210к отсекает ожидания 220к и 240к (и 300к)
    assert cats[("backend", "middle")]["candidates"] == 1
    assert cats[("backend", "senior")]["candidates"] == 0


def test_need_by_text_has_at_least_one_category(c, market):
    r = _create(c, market, text="Нужен разработчик на Python и FastAPI")
    assert r.status_code == 201, r.text
    assert r.json()["categories"], r.text
    # слабое совпадение — всё равно хотя бы одна категория (fallback)
    r = _create(c, market, filters={"skills_nice": ["kafka"]})
    assert {p for p, _ in _cats(r)} == {"backend"}


def test_empty_need_is_rejected(c, market):
    assert _create(c, market).status_code == 422
    r = _create(c, market, filters={})
    assert r.status_code == 422 and r.json()["code"] == "need_empty"
    assert _create(c, market, text="что-то совсем непонятное").status_code == 422


def test_foreign_need_is_404(c, market):
    nid = _create(c, market, filters={"skills_must": [{"slug": "python"}]}).json()["id"]
    other = _employer(c, "o@x.ru", name="Other Co")
    assert c.get(f"/needs/{nid}/categories", headers=_hdr(other)).status_code == 404
    r = c.get(f"/categories/backend/middle/candidates?need_id={nid}", headers=_hdr(other))
    assert r.status_code == 404 and r.json()["code"] == "need_not_found"
    assert (
        c.get(
            "/needs/00000000-0000-0000-0000-000000000000/categories", headers=_hdr(market)
        ).status_code
        == 404
    )


def test_roles_are_checked(c, market):
    cand = c.post("/auth/register", json={"email": "k@x.ru", "password": "correct-horse-battery",
                                          "role": "candidate"})  # fmt: skip
    h = {"Authorization": f"Bearer {cand.json()['access_token']}"}
    assert c.post("/needs", json={"text": "python"}, headers=h).status_code == 403
    assert c.get("/categories/backend/middle/candidates", headers=h).status_code == 403
    assert c.post("/needs", json={"text": "python"}).status_code == 401


def test_category_candidates_ranked_anonymous_with_explanation(c, market):
    nid = _create(
        c, market, filters={"skills_must": [{"slug": "python"}, {"slug": "fastapi"}]}
    ).json()["id"]
    r = c.get(f"/categories/backend/middle/candidates?need_id={nid}", headers=_hdr(market))
    assert r.status_code == 200, r.text
    body = r.json()
    pids = [i["pseudo_id"] for i in body["items"]]
    assert sorted(pids) == ["pid0002", "pid0003", "pid0004"] and body["total"] == 3
    assert pids[0] == "pid0003"  # покрывает оба навыка потребности: match выше
    top = body["items"][0]
    assert top["strength"]["rank"] is not None and len(top["strength"]["top"]) == 3
    assert top["match"] is None  # вакансии нет; объяснение — в strength.top
    assert [x["rank"] for x in (i["strength"] for i in body["items"])] == sorted(
        (i["strength"]["rank"] for i in body["items"]), reverse=True
    )
    text = json.dumps(body)
    assert "user_id" not in text and "@" not in text
    # без need_id — вся категория
    r = c.get("/categories/backend/senior/candidates", headers=_hdr(market))
    assert [i["pseudo_id"] for i in r.json()["items"]] == ["pid0001"]
    # пагинация по курсору
    p1 = c.get(f"/categories/backend/middle/candidates?need_id={nid}&limit=2", headers=_hdr(market))
    assert len(p1.json()["items"]) == 2 and p1.json()["next_cursor"]
    p2 = c.get(
        f"/categories/backend/middle/candidates?need_id={nid}&limit=2"
        f"&cursor={p1.json()['next_cursor']}", headers=_hdr(market),
    )  # fmt: skip
    assert [i["pseudo_id"] for i in p2.json()["items"]] == [pids[2]]


def test_invalid_category_is_422(c, market):
    assert c.get("/categories/backend/god/candidates", headers=_hdr(market)).status_code == 422
    assert c.get("/categories/Bad-Slug/middle/candidates", headers=_hdr(market)).status_code == 422


def test_category_page_returns_session_and_feedback_works(c, market):
    r = c.get("/categories/backend/middle/candidates?limit=2", headers=_hdr(market))
    sid = r.json()["session_id"]
    pid = r.json()["items"][0]["pseudo_id"]
    f = c.post(
        "/recs/feedback",
        json={"session_id": sid, "candidate_pseudo_id": pid, "event": "dismiss"},
        headers=_hdr(market),
    )
    assert f.status_code == 200, f.text
    assert f.json()["tuning"]["session_id"] == sid
    # вторая страница продолжает ту же сессию
    p2 = c.get(
        f"/categories/backend/middle/candidates?limit=2&session_id={sid}", headers=_hdr(market)
    )
    assert p2.json()["session_id"] == sid
    # чужой кандидат вне показов — 404
    f = c.post(
        "/recs/feedback",
        json={"session_id": sid, "candidate_pseudo_id": "pid0001", "event": "open"},
        headers=_hdr(market),
    )
    assert f.status_code == 404
