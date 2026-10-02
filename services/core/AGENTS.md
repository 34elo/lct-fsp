# AGENTS.md — core

Назначение: основной бэкенд — домен, граф доказательств, подбор, офферы (api, worker, scheduler).

## Команды
- `uv run --package fsp-core uvicorn app.main:app --reload` — запуск api
- `cd services/core && uv run python -m app.worker` — core-worker (очереди core.* + relay outbox)
- `cd services/core && uv run python -m app.scheduler` — core-scheduler (cron-команды)
- `make test-integration` — outbox → RabbitMQ → inbox на временных контейнерах
- `uv run pytest services/core -q` — тесты
- `uv run ruff check services/core` — линтер
- `cd services/core && uv run alembic upgrade head` — миграции (`-x url=...` или `DATABASE_URL`)
- `cd services/core && uv run alembic revision --autogenerate -m "..."` — новая миграция

## Ключевые файлы
- `app/main.py` — фабрика приложения, `/healthz`, `/readyz`, lifespan
- `app/deps.py` — зависимости: сессия (транзакция на запрос), Redis, лимитер, S3
- `app/models.py` — реестр моделей для Alembic
- `app/events_stream.py` — SSE `/events/stream`, `UiHub` (очередь `ui.<instance>`, `ui.user.*`); публикация — `fsp_platform.messaging.publish_ui`
- `app/identity/` — users, refresh-семьи, `/auth/*`, `/me`; зависимости `get_current_user`, `require_roles`
- `app/consents/` — согласия, `/me/consents`; зависимость `require_consent(type)` → 403 `consent_required`
- `app/candidates/` — анкета: `/candidates/me/{profile,preferences,visibility,stoplist}`, `pseudo_id`, псевдоним
- `app/taxonomy/` — граф навыков: `loader.py` (YAML → проверка), `service.py` (sync в БД, версия, снимок, `taxonomy.updated`), `router.py` (`GET /taxonomy`, `/internal/taxonomy/snapshot`); `make taxonomy-load`
- `app/worker.py` — `Worker.consumers[<очередь>].on(type)` + `idempotent()` для обработчиков
- `app/scheduler.py` — `SCHEDULE` (messaging.md §4)
- `migrations/` — Alembic (async), `versions/`
- `app/config.py` — настройки (из env)
- `tests/` — тесты

## Правила
- Общий код только из `packages/platform` и `packages/contracts`.
- В чужую БД не ходим: события, команды, internal API.
- Документы: docs/architecture/services.md, messaging.md.
