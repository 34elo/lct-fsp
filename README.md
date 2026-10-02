# ФСП Карьера

Платформа-агрегатор ИТ-вакансий с обратной механикой подбора и верифицированным профилем достижений Федерации спортивного программирования (ФСП). Хакатон, кейс ФСП. Демо: https://fsp.patissons.tech (появится после первого деплоя).

**«Не резюме, а доказательства».** Профиль кандидата — граф доказательств: проверяемые факты (результаты соревнований ФСП, код, тесты, опыт) подтверждают навыки с разной силой. Из графа автоматически считаются доверие к навыкам (○○○○…●●●●), категория и грейд с объяснением. Работодатель сам находит кандидата и приходит с вакансией и обязательной зарплатной вилкой; оффер приходит в Telegram и принимается в один клик. Кандидат видит, какой навык подтвердить, чтобы подходить под N% больше вакансий, и на каком соревновании ФСП это сделать.

## Статус

Проектирование завершено, код не начат. Что сделать до старта — [docs/process/kickoff.md](docs/process/kickoff.md).

## Архитектура

```
web (React SPA) ──┐
bot (aiogram) ────┼─► core (api · worker · scheduler) ─► PostgreSQL + pgvector (граф) · Redis (кеш) · MinIO
                  │        ▲ │
                  │        │ ▼   RabbitMQ: события, команды, задачи ML с приоритетами, уведомления, SSE
                  │   fsp-connector ─► API ФСП (сейчас fsp-mock)
                  └──► ml (api · worker-llm · worker-code) ─► llama.cpp (Vulkan, RX 5700 XT) · bge-m3 · GitHub
```

Python 3.12 · FastAPI · SQLAlchemy 2 · FastStream + RabbitMQ · aiogram 3 · React 19 + Vite + TS · TanStack Query · Tailwind + shadcn/ui · ECharts · PostgreSQL 16 + pgvector · Redis 7 · llama.cpp · Docker Compose · Caddy.

## Документация

- [docs/README.md](docs/README.md) — структура и что читать под задачу.
- [AGENTS.md](AGENTS.md) — правила для ИИ-агентов и людей, работающих с репозиторием.

## Запуск

Появится вместе с кодом. Целевые команды: `make up`, `make migrate`, `make taxonomy-load`, `make seed`, `make demo-reset`, `make eval` — [deployment.md](docs/architecture/deployment.md#5-makefile-целевые-команды).

Данные ядра навыков частично получены из Stack Overflow (CC BY-SA 4.0).
