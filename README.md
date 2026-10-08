# ФСП Карьера

ИТ-агрегатор найма с обратной механикой для кейса Федерации спортивного программирования (ФСП). Работодатель не ждёт откликов: он сам находит кандидата нужной категории (специализация × грейд) и приглашает его, сразу указывая вилку зарплаты.

**Категория определяется не резюме, а обязательным путём: опрос → выбор грейда → тест.** Тест устойчив к утечке заданий: каждый кандидат получает свой сгенерированный «мир» (вымышленная компания с кодом, базой, метриками и инцидентом), а правильный ответ вычисляется из этого мира. Сложность семейств заданий измеряется (Rasch, Elo, якорные задания), грейд определяет классификационный тест (SPRT). Для жюри есть экспресс-режим на 3–5 минут.

**Доверие к навыкам — лестница.** Самооценка → резюме → тест → регулярные задания и «объясни ответ» → результаты ФСП. Работодатель видит расхождения вроде «заявлено Senior, подтверждено Middle». Данные ФСП в проекте берутся из имитации API (`fsp-mock`); кандидат без истории ФСП обрабатывается корректно. Подробнее о решении — [docs/solution.md](docs/solution.md), выжимка ТЗ — [docs/case.md](docs/case.md).

Все модели локальные, обязательный путь (регистрация → опрос → тест → категория → приглашение) работает без GPU и LLM. Все люди и компании в демо-данных вымышленные.

## Запуск за 3 команды (без GPU)

Нужны Docker с Compose v2, Python-менеджер [uv](https://docs.astral.sh/uv/) и Node.js 20+ с pnpm. Из корня репозитория:

```bash
make demo-env   # создаёт .env.demo с демо-секретами (отдельный .env не нужен)
make up-lite    # профиль lite: сборка образов, миграции, сервисы без LLM
make seed       # демо-данные: кандидаты, компании, вакансии, офферы
```

Приложение: **http://localhost:28080**. `make up-lite` сам вызывает `make demo-env`, команда указана отдельно для наглядности. Миграции и справочник навыков загружаются при старте стека. Повторный `make seed` безопасен, а `make demo-reset` возвращает витрину к снимку (см. [docs/deploy.md](docs/deploy.md)).

Остановка: `make down`. Профили `standard` (LLM на CPU) и `full` (GPU), порты, типичные ошибки и полный список команд — в [docs/deploy.md](docs/deploy.md). Публичного стенда пока нет.

На Windows без `make` команды Makefile запускайте из Git Bash или WSL, либо вручную по разделу «Windows без make» в [docs/deploy.md](docs/deploy.md).

## Демо-аккаунты

Пароль у всех — тестовый `demo-pass-1234` (из `tools/seed/config.yaml`). Актуальный список логинов `make seed` печатает в конце.

| Роль | Логин |
|---|---|
| Жюри, кандидат (без грейда, проходит экспресс-тест) | `jury-candidate@demo.fsp.test` |
| Жюри, работодатель (проверенная компания) | `jury-hr@demo.fsp.test` |
| Кандидаты | `cand0001@demo.fsp.test` … `cand0400@demo.fsp.test`; герои демо — `anya@`, `dima@`, `olga@demo.fsp.test` |
| Работодатели | `hr01@demo.fsp.test` … `hr25@demo.fsp.test` |
| Администратор | `admin@demo.fsp.test` |

Путь по ТЗ: регистрация (или вход жюри) → опрос → тест (экспресс) → категория → вход работодателя → поиск категории → приглашение → принятие кандидатом. Сценарий показа по минутам — [docs/pitch.md](docs/pitch.md).

## Интерфейсы

| Адрес | Что это |
|---|---|
| http://localhost:28080 | приложение (SPA) |
| http://localhost:28080/api/docs | Swagger UI |
| [docs/asyncapi.json](docs/asyncapi.json) | события и команды (AsyncAPI), `make asyncapi` |
| [docs/openapi.json](docs/openapi.json) | схема REST API (OpenAPI), `make openapi` |

Наружу открыт только gateway на порту 28080; остальные порты на хосте — 28xxx.

## Архитектура

```
web (React SPA) ──┐
bot (aiogram) ────┼─► core (api · worker · scheduler) ─► PostgreSQL + pgvector · Redis · MinIO
                  │        ▲ │
                  │        │ ▼   RabbitMQ: события, команды, задачи ML, уведомления
                  │   fsp-connector ─► API ФСП (сейчас fsp-mock)
                  └──► ml (api · workers) ─► локальные модели (LLM опционально) · GitHub
```

Python 3.12 · FastAPI · SQLAlchemy 2 · FastStream + RabbitMQ · aiogram 3 · React + Vite + TypeScript · PostgreSQL + pgvector · Redis · Docker Compose · Caddy. Подробно — [docs/architecture/system.md](docs/architecture/system.md).

## Документы

- [docs/submission.md](docs/submission.md) — документ сдачи: решение, метрики, как проверить.
- [docs/deploy.md](docs/deploy.md) — развёртывание, профили, команды.
- [docs/pitch.md](docs/pitch.md) — питч и сценарий демо.
- [docs/process/blocks.md](docs/process/blocks.md) — как команда делится на два блока и что лежит на стыке.
- [docs/README.md](docs/README.md) — карта всей документации; [AGENTS.md](AGENTS.md) — правила для ИИ-агентов и людей.

Данные ядра навыков частично получены из Stack Overflow (CC BY-SA 4.0).
