# Демо и песочница жюри — `app/demo`

`POST /auth/jury` (только при `DEMO_MODE`): пара «кандидат без грейда + работодатель с проверенной компанией» на каждый вход жюри; снапшот и сброс демо-данных (`python -m app.demo snapshot|reset`).

| Файл | Что |
|---|---|
| `router.py` | `/auth/jury` |
| `service.py` | песочница жюри |
| `snapshot.py` | снапшот и восстановление демо-данных |

Подробнее: [running.md](../../../../docs/operations/running.md#демо-данные).
