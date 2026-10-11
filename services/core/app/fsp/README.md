# ФСП (сторона core) — `app/fsp`

Клиент internal API `fsp-connector`: привязка через реестр и заявка, OAuth и код (бэкенд), синхронизация по кнопке, обзор ФСП кандидата; администрирование реестра ФСП; демо-ручки.

| Файл | Что |
|---|---|
| `client.py` | HTTP-клиент fsp-connector |
| `router.py` | `/candidates/me/fsp/*`, `/auth/fsp/*`, `/admin/demo/*` |
| `registry_router.py` | `/candidates/me/fsp/registry-link`, `/admin/fsp/*` |
| `service.py` | обзор ФСП кандидата |

Подробнее: [fsp.md](../../../../docs/mechanics/fsp.md).
