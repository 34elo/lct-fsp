# core

Основной бэкенд: доменная логика, тест, граф доказательств, подбор, контакт. Модульный монолит — три процесса из одного образа:

| Процесс | Команда | Что делает |
|---|---|---|
| `core-api` | `uvicorn app.main:app` | REST API и SSE |
| `core-worker` | `python -m app.worker` | Очереди `core.*` и ретранслятор outbox |
| `core-scheduler` | `python -m app.scheduler` | Команды по расписанию в `core.jobs` |

## Модули

Каждый модуль `app/<имя>/` — `router.py` (HTTP), `service.py` (публичное API модуля для других модулей), `models.py` (таблицы), `handlers.py` (подписчики очередей). Модули обращаются друг к другу только через `service.py`. Описание каждого — в его `README.md`:

[identity](app/identity/README.md) · [consents](app/consents/README.md) · [candidates](app/candidates/README.md) · [resumes](app/resumes/README.md) · [taxonomy](app/taxonomy/README.md) · [graph](app/graph/README.md) · [assessment](app/assessment/README.md) · [companies](app/companies/README.md) · [vacancies](app/vacancies/README.md) · [matching](app/matching/README.md) · [offers](app/offers/README.md) · [recommendations](app/recommendations/README.md) · [notifications](app/notifications/README.md) · [telegram](app/telegram/README.md) · [fsp](app/fsp/README.md) · [credentials](app/credentials/README.md) · [views](app/views/README.md) · [analytics](app/analytics/README.md) · [jobs](app/jobs/README.md) · [demo](app/demo/README.md)

Общие файлы: `main.py` (сборка приложения, `/readyz`), `config.py` (настройки из окружения), `deps.py` (сессия БД, Redis, лимитер, S3), `events_stream.py` (SSE), `models.py` (реестр моделей для Alembic), `openapi_errors.py` (описание ошибок в OpenAPI).

## Команды

```bash
uv run --package fsp-core uvicorn app.main:app --reload       # API локально
cd services/core && uv run alembic upgrade head               # миграции
cd services/core && uv run python -m app.taxonomy             # загрузить справочник навыков
PYTHONUTF8=1 uv run pytest services/core -q -n auto           # тесты (SQLite из миграций)
```

Тесты — `tests/`: формулы на примерах, права «чужой ресурс → 404», идемпотентность обработчиков; фабрики данных — `tests/factories/`.

Документация: [архитектура](../../docs/architecture/overview.md), [API](../../docs/architecture/api.md), [модель данных](../../docs/architecture/data-model.md).
