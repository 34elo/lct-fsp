"""Шорт-лист: уточнение фильтров без потери подборки (E23-5)."""

import pytest
import test_search as ts

c = ts.c  # фикстура клиента с БД из test_search
_cand, _employer, _hdr = ts._cand, ts._employer, ts._hdr


@pytest.fixture
def market_with_shortlist(c):
    """Рынок для тестов шорт-листа: работодатель и несколько кандидатов."""
    h = _employer(c, "employer@x.ru", name="Test Corp")
    roles = {
        "backend": {"python": 1.0, "fastapi": 0.8},
        "frontend": {"python": 0.5},
    }
    import sqlite3

    with sqlite3.connect(c.db) as con:
        for role, weights in roles.items():
            con.execute("insert into roles (slug, name) values (?,?)", (role, role.title()))
            for slug, w in weights.items():
                if slug in c.skills:
                    con.execute(
                        "insert into role_skills (role, skill_id, weight, source) values (?,?,?,?)",
                        (role, c.skills[slug], w, "seed"),
                    )
    # Создать кандидатов с подтверждённым грейдом
    _cand(c, 1, [("python", 0.9, 4, ["test"])], grade="senior", salary_min=300_000)
    _cand(c, 2, [("python", 0.8, 3, ["test"])], grade="middle", salary_min=200_000)
    _cand(
        c,
        3,
        [("python", 0.7, 3, ["test"]), ("fastapi", 0.6, 3, ["test"])],
        grade="middle",
        salary_min=220_000,
    )
    return h


def _create_need(c, h, **body):
    """Создать потребность."""
    return c.post("/needs", json=body, headers=_hdr(h))


def _get_categories(c, h, need_id):
    """Получить категории потребности."""
    return c.get(f"/needs/{need_id}/categories", headers=_hdr(h))


def _get_candidates(c, h, profession, grade, need_id=None):
    """Получить кандидатов в категории."""
    url = f"/categories/{profession}/{grade}/candidates"
    if need_id:
        url += f"?need_id={need_id}"
    return c.get(url, headers=_hdr(h))


def test_shortlist_is_shown_in_candidates(c, market_with_shortlist):
    """Флаг is_shortlisted присутствует в выдаче кандидатов (E23-5 критерий)."""
    need_resp = _create_need(
        c, market_with_shortlist, filters={"skills_must": [{"slug": "python"}]}
    )
    assert need_resp.status_code == 201
    need_id = need_resp.json()["id"]
    assert need_resp.json()["shortlist"] == []

    # Получить кандидатов
    cands_resp = _get_candidates(c, market_with_shortlist, "backend", "middle", need_id)
    assert cands_resp.status_code == 200
    candidates = cands_resp.json()["items"]
    assert len(candidates) > 0

    # Все должны иметь флаг is_shortlist (по умолчанию false)
    for cand in candidates:
        assert "is_shortlisted" in cand
        assert cand["is_shortlisted"] is False


def test_shortlist_endpoint_add_returns_204(c, market_with_shortlist):
    """Эндпоинт POST /needs/{id}/shortlist/{pseudo_id} возвращает 204."""
    need_resp = _create_need(
        c, market_with_shortlist, filters={"skills_must": [{"slug": "python"}]}
    )
    need_id = need_resp.json()["id"]

    # Получить кандидата
    cands_resp = _get_candidates(c, market_with_shortlist, "backend", "middle", need_id)
    pseudo_id = cands_resp.json()["items"][0]["pseudo_id"]

    # Добавить в шорт-лист
    add_resp = c.post(
        f"/needs/{need_id}/shortlist/{pseudo_id}", headers=_hdr(market_with_shortlist)
    )
    assert add_resp.status_code == 204


def test_shortlist_endpoint_delete_returns_204(c, market_with_shortlist):
    """Эндпоинт DELETE /needs/{id}/shortlist/{pseudo_id} возвращает 204."""
    need_resp = _create_need(
        c, market_with_shortlist, filters={"skills_must": [{"slug": "python"}]}
    )
    need_id = need_resp.json()["id"]

    # Получить кандидата
    cands_resp = _get_candidates(c, market_with_shortlist, "backend", "middle", need_id)
    pseudo_id = cands_resp.json()["items"][0]["pseudo_id"]

    # Удалить из шорт-листа (даже если не добавлен)
    del_resp = c.delete(
        f"/needs/{need_id}/shortlist/{pseudo_id}", headers=_hdr(market_with_shortlist)
    )
    assert del_resp.status_code == 204


def test_shortlist_not_found_for_nonexistent_candidate(c, market_with_shortlist):
    """Добавление несуществующего кандидата → 404."""
    need_resp = _create_need(
        c, market_with_shortlist, filters={"skills_must": [{"slug": "python"}]}
    )
    need_id = need_resp.json()["id"]

    resp = c.post(f"/needs/{need_id}/shortlist/fake_pseudo_id", headers=_hdr(market_with_shortlist))
    assert resp.status_code == 404
    assert resp.json()["code"] == "candidate_not_found"


def test_shortlist_ownership_check(c, market_with_shortlist):
    """Работодатель не может управлять потребностью другого работодателя."""
    need_resp = _create_need(
        c, market_with_shortlist, filters={"skills_must": [{"slug": "python"}]}
    )
    need_id = need_resp.json()["id"]

    # Получить кандидата
    cands_resp = _get_candidates(c, market_with_shortlist, "backend", "middle", need_id)
    pseudo_id = cands_resp.json()["items"][0]["pseudo_id"]

    # Создать другого работодателя
    other = _employer(c, "other@x.ru", name="Other Corp")

    # Попытаться добавить с другим работодателем
    resp = c.post(f"/needs/{need_id}/shortlist/{pseudo_id}", headers=_hdr(other))
    assert resp.status_code == 404
    assert resp.json()["code"] == "need_not_found"


def test_shortlist_all_merges_needs_without_repeats(c, market_with_shortlist):
    """GET /shortlist собирает отмеченных из всех потребностей компании без повторов (E39-23)."""
    h = market_with_shortlist
    assert c.get("/shortlist", headers=_hdr(h)).json() == {"items": []}
    n1 = _create_need(c, h, filters={"skills_must": [{"slug": "python"}]}).json()["id"]
    n2 = _create_need(c, h, filters={"skills_must": [{"slug": "python"}]}).json()["id"]
    items = _get_candidates(c, h, "backend", "middle", n1).json()["items"]
    first = items[0]["pseudo_id"]
    for need in (n1, n2):
        assert c.post(f"/needs/{need}/shortlist/{first}", headers=_hdr(h)).status_code == 204
    got = c.get("/shortlist", headers=_hdr(h)).json()["items"]
    assert [i["pseudo_id"] for i in got] == [first]
    # чужая компания чужого шорт-листа не видит
    other = _employer(c, "other2@x.ru", name="Other Corp")
    assert c.get("/shortlist", headers=_hdr(other)).json() == {"items": []}
