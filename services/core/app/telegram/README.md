# Telegram — `app/telegram`

Привязка Telegram к аккаунту, вход по виджету и magic-ссылке, internal API для бота: профиль, категория, ФСП, настройки, приглашения, короткий токен кандидата для теста.

| Файл | Что |
|---|---|
| `router.py` | `/me/telegram/link`, `/internal/tg/*`, `/internal/auth/magic-link` |
| `service.py` | проверка подписи виджета, одноразовые токены, привязка |

Подробнее: [bot](../../../bot/README.md).
