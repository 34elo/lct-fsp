# fsp-platform

Общая инфраструктура Python-сервисов: всё, что не относится к домену.

| Модуль (`src/fsp_platform/`) | Что |
|---|---|
| `app.py` | Фабрика FastAPI: `/healthz`, Problem Details (`ProblemError`), `X-Request-Id` → `correlation_id` |
| `config.py` | `BaseServiceSettings`: общие переменные окружения |
| `db.py` | Async-движок SQLAlchemy, фабрика сессий, `session_scope` (транзакция) |
| `outbox.py` | Outbox (запись в транзакции, relay с LISTEN/NOTIFY + опрос 0.5 с) и inbox (идемпотентность) |
| `messaging.py` | Топология RabbitMQ, публикация с подтверждением, потребители с ретраями 5 с / 30 с / 2 мин и DLQ |
| `jwt.py` | Выпуск и проверка access-токенов |
| `ratelimit.py` | Лимиты на Redis (скользящее окно), `429` с `Retry-After` |
| `storage.py` | Клиент MinIO/S3 |
| `locks.py` | Распределённые блокировки |
| `logging.py` | structlog в JSON с `correlation_id`, без ПДн |

Тесты — `tests/`; интеграционный тест outbox → RabbitMQ → inbox — `make test-integration` (временные контейнеры).
