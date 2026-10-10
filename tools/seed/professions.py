"""Демо-предложение новой профессии (E41-17): «Разработчик 1С» в админке «Новая профессия?».

Навыки ядра (1С, MS SQL Server, SQL, форматы данных) не покрыты ни одной профессией справочника
больше чем наполовину. Примеры вакансий вымышленные, без id. Идемпотентно по ядру навыков.
"""

from __future__ import annotations

from app.taxonomy import profession_suggest
from fsp_platform.db import session_scope
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

DEMO = {
    "title": "Разработчик 1С",
    "skills": ["1c", "mssql", "sql", "xml_json"],
    "examples": [
        {"vacancy_id": None, "title": "Программист 1С (учёт и склад)"},
        {"vacancy_id": None, "title": "Разработчик 1С: интеграции"},
        {"vacancy_id": None, "title": "Middle 1С-разработчик"},
    ],
    "support_vacancies": 7,
    "support_needs": 3,
}


async def seed_profession_suggestion(factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    async with session_scope(factory) as s:
        row = await profession_suggest.seed(s, **DEMO)
        return {"profession_suggestion": 1 if row.status == "open" else 0}


__all__ = ["DEMO", "seed_profession_suggestion"]
