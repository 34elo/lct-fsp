"""Шорт-лист: уточнение фильтров без потери подборки (E23-5)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories.hiring import factory_need


@pytest.mark.asyncio
class TestShortlist:
    """Шорт-лист потребности: добавление, удаление, персистентность (E23-5)."""

    async def test_add_to_shortlist(
        self, client: AsyncClient, session: AsyncSession, employer_user, company
    ) -> None:
        """Добавить кандидата в шорт-лист."""
        need = await factory_need(session, company.id)
        await session.commit()

        # Выполнить поиск, чтобы получить pseudo_id кандидата
        search_resp = await client.post(
            "/search/candidates",
            json={"filters": {}, "limit": 5},
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )
        assert search_resp.status_code == 200
        data = search_resp.json()
        assert len(data["items"]) > 0
        pseudo_id = data["items"][0]["pseudo_id"]

        # Добавить в шорт-лист
        resp = await client.post(
            f"/needs/{need.id}/shortlist/{pseudo_id}",
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )
        assert resp.status_code == 204

        # Проверить, что добавлено
        await session.refresh(need)
        assert pseudo_id in need.shortlist

    async def test_remove_from_shortlist(
        self, client: AsyncClient, session: AsyncSession, employer_user, company
    ) -> None:
        """Удалить кандидата из шорт-листа."""
        need = await factory_need(session, company.id)
        await session.commit()

        # Получить pseudo_id
        search_resp = await client.post(
            "/search/candidates",
            json={"filters": {}, "limit": 5},
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )
        pseudo_id = search_resp.json()["items"][0]["pseudo_id"]

        # Добавить в шорт-лист
        add_resp = await client.post(
            f"/needs/{need.id}/shortlist/{pseudo_id}",
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )
        assert add_resp.status_code == 204

        # Удалить из шорт-листа
        del_resp = await client.delete(
            f"/needs/{need.id}/shortlist/{pseudo_id}",
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )
        assert del_resp.status_code == 204

        # Проверить, что удалено
        await session.refresh(need)
        assert pseudo_id not in need.shortlist

    async def test_shortlist_persists_in_need_categories(
        self, client: AsyncClient, session: AsyncSession, employer_user, company
    ) -> None:
        """Шорт-лист возвращается в GET /needs/{need_id}/categories."""
        need = await factory_need(session, company.id)
        await session.commit()

        # Получить pseudo_id
        search_resp = await client.post(
            "/search/candidates",
            json={"filters": {}, "limit": 5},
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )
        pseudo_id = search_resp.json()["items"][0]["pseudo_id"]

        # Добавить в шорт-лист
        await client.post(
            f"/needs/{need.id}/shortlist/{pseudo_id}",
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )

        # Проверить, что в GET /needs/{need_id}/categories есть shortlist
        resp = await client.get(
            f"/needs/{need.id}/categories",
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert pseudo_id in data["shortlist"]

    async def test_shortlist_marked_in_category_candidates(
        self, client: AsyncClient, session: AsyncSession, employer_user, company
    ) -> None:
        """Фильтр не сбрасывает отмеченных: is_shortlisted флаг в выдаче (E23-5, критерий)."""
        need = await factory_need(session, company.id, text="Python")
        await session.commit()

        # Получить категории
        cats_resp = await client.get(
            f"/needs/{need.id}/categories",
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )
        assert cats_resp.status_code == 200
        categories = cats_resp.json()["categories"]
        assert len(categories) > 0

        prof, grade = categories[0]["profession"], categories[0]["grade"]

        # Получить кандидатов в категории
        cands_resp = await client.get(
            f"/categories/{prof}/{grade}/candidates",
            params={"need_id": str(need.id)},
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )
        assert cands_resp.status_code == 200
        items = cands_resp.json()["items"]
        assert len(items) > 0
        pseudo_id = items[0]["pseudo_id"]

        # Добавить первого кандидата в шорт-лист
        await client.post(
            f"/needs/{need.id}/shortlist/{pseudo_id}",
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )

        # Снова получить кандидатов (эмулируем изменение фильтра)
        cands_resp2 = await client.get(
            f"/categories/{prof}/{grade}/candidates",
            params={"need_id": str(need.id), "limit": 30},
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )
        assert cands_resp2.status_code == 200
        items2 = cands_resp2.json()["items"]

        # Проверить, что первый кандидат помечен как в шорт-листе
        marked = next((c for c in items2 if c["pseudo_id"] == pseudo_id), None)
        assert marked is not None, "Отмеченный кандидат потерялся после смены фильтров"
        assert marked.get("is_shortlisted") is True, "Флаг is_shortlisted не установлен"

    async def test_shortlist_not_found_for_nonexistent_candidate(
        self, client: AsyncClient, session: AsyncSession, employer_user, company
    ) -> None:
        """Добавление несуществующего кандидата в шорт-лист → 404."""
        need = await factory_need(session, company.id)
        await session.commit()

        resp = await client.post(
            f"/needs/{need.id}/shortlist/fake_pseudo_id",
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "candidate_not_found"

    async def test_shortlist_ownership_check(
        self,
        client: AsyncClient,
        session: AsyncSession,
        employer_user,
        other_employer_user,
        company,
    ) -> None:
        """Работодатель не может добавить кандидата в потребность другой компании."""
        need = await factory_need(session, company.id)
        await session.commit()

        # Получить pseudo_id
        search_resp = await client.post(
            "/search/candidates",
            json={"filters": {}, "limit": 5},
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )
        pseudo_id = search_resp.json()["items"][0]["pseudo_id"]

        # Попробуать добавить с другим пользователем
        resp = await client.post(
            f"/needs/{need.id}/shortlist/{pseudo_id}",
            headers={"Authorization": f"Bearer {other_employer_user.token}"},
        )
        assert resp.status_code == 404

    async def test_add_duplicate_to_shortlist(
        self, client: AsyncClient, session: AsyncSession, employer_user, company
    ) -> None:
        """Добавление дубликата в шорт-лист идёмпотентно."""
        need = await factory_need(session, company.id)
        await session.commit()

        # Получить pseudo_id
        search_resp = await client.post(
            "/search/candidates",
            json={"filters": {}, "limit": 5},
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )
        pseudo_id = search_resp.json()["items"][0]["pseudo_id"]

        # Добавить дважды
        await client.post(
            f"/needs/{need.id}/shortlist/{pseudo_id}",
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )
        resp2 = await client.post(
            f"/needs/{need.id}/shortlist/{pseudo_id}",
            headers={"Authorization": f"Bearer {employer_user.token}"},
        )
        assert resp2.status_code == 204

        # Проверить, что в шорт-листе только один экземпляр
        await session.refresh(need)
        assert need.shortlist.count(pseudo_id) == 1
