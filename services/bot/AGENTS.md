# AGENTS.md — bot

Назначение: Telegram-бот на aiogram 3 (long polling), без бизнес-логики: действия идут в core `/internal/tg/*`, исходящие читаются из очереди `bot.telegram` (docs/architecture/telegram.md).

## Команды
- `TG_BOT_TOKEN=… SERVICE_TOKEN_BOT=… uv run --package fsp-bot python -m fsp_bot.main` — запуск (без токена завершится с ошибкой)
- `uv run pytest services/bot -q` — тесты (fakeredis, фейковая сессия aiogram, без сети)
- `uv run ruff check services/bot` — линтер

## Ключевые файлы
- `fsp_bot/main.py` — сборка: Bot, RedisStorage (`fsm:*`, TTL 30 мин), подписчик `bot.telegram`, polling
- `fsp_bot/sender.py` — `notify.telegram` → сообщение: лимиты, `edit_of` (ключ → message_id в Redis `bot:msg:*`), RetryAfter, дедуп по `message_id` (`bot:sent:*`)
- `fsp_bot/limiter.py` — token bucket 25/с глобально и 1/с на чат
- `fsp_bot/core_client.py` — httpx-клиент core с `Authorization: Service <SERVICE_TOKEN_BOT>`
- `fsp_bot/handlers.py` — `/start`, согласия (`c:ok`/`c:no`), меню, резюме файлом (сигнатура и 10 МБ в боте и в core, опрос статуса, `r:ok:<id>`), профиль, офферы (`o:v|a|d|r|q|b:<id>`, причины отказа, вопрос работодателю через FSM `Offer.awaiting_question`); остальное — E9-4 и далее
- `fsp_bot/account.py` — 🏆 ФСП (привязка по ID/email + код, обновление), 🎯 категория и статус теста (заглушка «скоро» до E25-3), 🔥 статус `s:*`, ⚙️ настройки `g:*` (зарплата через FSM `Settings.awaiting_salary`, форматы); GitHub (E10-3) и короткий тест (E25-3) ещё не подключены
- `fsp_bot/templates/` — HTML-шаблоны по `TgTemplate`, клавиатуры; `fsp_bot/states.py` — FSM

## Правила
- Пакет `fsp_bot` (не `app`). Токены только из env, в логах нет ПДн и текстов сообщений.
- Заблокировавший бота пользователь (`Forbidden`) — сообщение снимается с очереди без ретраев.
- Файлы пользователя не сохраняем, стримим в core.
- Документы: telegram.md, messaging.md §2, api.md §2.10 и §5.

## Docker
Образ: `infra/docker/python.Dockerfile` (`PACKAGE=fsp-bot`, `SERVICE_DIR=services/bot`), в compose — сервис `bot`; профиль `bot` включается `make up` только при заданном `TG_BOT_TOKEN` (в сборке не проверялся). Запуск стека: `make up`.
