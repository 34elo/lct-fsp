# fsp-connector

Единственная точка работы с данными ФСП: порт `FspPort`, адаптеры источников, реестр ФСП, привязка кандидатов, синхронизация, вебхук. Своя база `fsp_connector`; в БД core не ходит — публикует события `fsp.*` и отвечает на internal API ([fsp.md](../../docs/mechanics/fsp.md)).

| Процесс | Команда |
|---|---|
| API (`:8300`) | `uvicorn fsp_connector.main:app --port 8300` |
| Воркер (очередь `fsp.sync`, relay outbox) | `python -m fsp_connector.worker` |
| Миграции | `alembic upgrade head` |

## Ключевые файлы (`fsp_connector/`)

| Файл | Что |
|---|---|
| `port.py` | Протокол `FspPort`: участник, результаты, разряды, соревнования, команды, код, OAuth |
| `http_adapter.py`, `mappings/` | REST-источник с маппингом схемы; повторы и автомат размыкания (`resilience.py`), кеш (`cache.py`) |
| `registry.py`, `registry_api.py`, `registry_import.py` | Реестр: мероприятия, участники, результаты, CSV, заявки; `RegistryAdapter` поверх источника |
| `linking.py` | Привязка: реестр, OAuth + PKCE, код, ручной ID; конфликты |
| `sync.py`, `handlers.py` | `fsp.sync` / `fsp.sync_all` → события в outbox |
| `webhook.py` | `POST /integrations/fsp/webhook` с HMAC-подписью |
| `publisher.py` | События `fsp.linked`, `fsp.results.imported`, `fsp.competitions.updated` |
| `api.py` | `/internal/*` для core (сервисный токен) |
| `factory.py` | Выбор адаптера по `FSP_ADAPTER` |
| `demo.py` | Снапшот и сброс демо-привязок |

```bash
cd services/fsp-connector && uv run --package fsp-fsp-connector --with-editable ../fsp-mock pytest -q tests
```

Контрактные тесты гоняют адаптер против `fsp-mock` в процессе. ПДн участников не логируются и не попадают в события.
