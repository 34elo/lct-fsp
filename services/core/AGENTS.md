# AGENTS.md — core

Назначение: основной бэкенд — домен, граф доказательств, подбор, офферы (api; worker и scheduler — позже, E0-6).

## Команды
- `uv run --package fsp-core uvicorn app.main:app --reload` — запуск
- `uv run pytest services/core -q` — тесты
- `uv run ruff check services/core` — линтер
- `cd services/core && uv run alembic upgrade head` — миграции (`-x url=...` или `DATABASE_URL`)
- `cd services/core && uv run alembic revision --autogenerate -m "..."` — новая миграция

## Ключевые файлы
- `app/main.py` — фабрика приложения, `/healthz`, `/readyz`, lifespan
- `app/deps.py` — зависимости: сессия (транзакция на запрос), Redis, лимитер, S3
- `app/models.py` — реестр моделей для Alembic
- `migrations/` — Alembic (async), `versions/`
- `app/config.py` — настройки (из env)
- `tests/` — тесты

## Правила
- Общий код только из `packages/platform` и `packages/contracts`.
- В чужую БД не ходим: события, команды, internal API.
- Документы: docs/architecture/services.md, messaging.md.
