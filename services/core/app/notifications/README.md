# Уведомления — `app/notifications`

По событиям `offer.*`, ФСП, регулярных заданий и профиля создаёт уведомления, отправляет их в UI по SSE и в Telegram командой `notify.telegram` (при привязке и согласии).

| Файл | Что |
|---|---|
| `handlers.py` | обработчики событий |
| `service.py` | создание и раздача по каналам |

Подробнее: [messaging.md](../../../../docs/architecture/messaging.md).
