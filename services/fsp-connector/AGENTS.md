# AGENTS.md — fsp-connector

Назначение: единственная точка работы с ФСП — порт `FspPort`, адаптеры, кеш, публикация `fsp.*` (docs/architecture/fsp.md). Своя БД `fsp_connector`; в БД core не ходит.

## Команды
- `uv run --package fsp-fsp-connector uvicorn fsp_connector.main:app --port 8300` — api (`/healthz`)
- `cd services/fsp-connector && uv run python -m fsp_connector.worker` — relay outbox → RabbitMQ
- `cd services/fsp-connector && uv run alembic upgrade head` — миграции (`-x url=...` или `DATABASE_URL`)
- `uv run pytest services/fsp-connector -q` — тесты (контрактные идут на fsp-mock in-process)
- `uv run ruff check services/fsp-connector` — линтер

## Ключевые файлы
- `fsp_connector/port.py` — `FspPort`; DTO в `packages/contracts/.../fsp.py`
- `fsp_connector/http_adapter.py` — `HttpFspAdapter(base_url, api_key, mapping)`: ретраи, breaker, PKCE
- `fsp_connector/mappings/` — маппинг схемы источника в DTO (`MOCK`); новый источник = новый маппинг
- `fsp_connector/resilience.py` — экспоненциальные ретраи, `CircuitBreaker` (5 сбоев → 30 с)
- `fsp_connector/cache.py` — `CachedFspAdapter`: `c:fsp:part:{id}`, `c:fsp:res:{id}`, TTL 10 мин, `invalidate()`
- `fsp_connector/factory.py` — выбор по `FSP_ADAPTER` (`organizers`/`real` — E5-8)
- `fsp_connector/models.py`, `migrations/` — `fsp_links`, `fsp_link_conflicts`, `raw_responses`, `webhook_log`, outbox/inbox
- `fsp_connector/linking.py` — `LinkService`: OAuth / код / ручной ID, `fsp_link_conflicts`; `api.py` — `/internal/*` (`Service <SERVICE_TOKEN_CORE>`)
- `fsp_connector/sync.py` — `SyncService`: `fsp.sync` / `fsp.sync_all` → `fsp.competitions.updated` + `fsp.results.imported` (полная при `new=true`); `handlers.py` — подписчик очереди `fsp.sync` (замок, inbox); запуск в `worker.py`
- `fsp_connector/publisher.py` — `fsp.linked`, `fsp.results.imported`, `fsp.competitions.updated` в outbox

## Правила
- Пакет `fsp_connector` (не `app`). ПДн участников не логируем и не кладём в события.
- Событие пишется в outbox в той же транзакции, что и данные; обработчики идемпотентны (inbox).
- Вебхук и `fsp_sync_all` по расписанию — E5-6.
- Документы: fsp.md, messaging.md §2 и §6, data-model.md §3.10.
