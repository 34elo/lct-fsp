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

## Быстрый старт

### Требования
- Docker и Docker Compose (v2.20+)
- Node.js 20+
- Python 3.12 (в составе репозитория с `uv`)
- Linux / macOS (или WSL на Windows)
- Минимум 16 ГБ ОЗУ (рекомендуется 32+ для полного стенда с GPU)

### Запуск (2 минуты)

```bash
# 1. Первый запуск — копируем конфиг
cp .env.example .env

# 2. Для стенда жюри без GPU (lite)
make up-lite && make migrate && make taxonomy-load && make seed
# → http://localhost:28080

# 3. Для разработки с GPU (full)
make up && make migrate && make taxonomy-load && make seed

# 4. Остановка
make down
```

Подробная инструкция: [docs/deploy.md](docs/deploy.md)

Целевые команды: `make up`, `make up-lite`, `make migrate`, `make taxonomy-load`, `make seed`, `make demo-reset`, `make eval` — полный список в [docs/deploy.md](docs/deploy.md#основные-команды).

## Демо-аккаунты

Все тестовые данные создаются автоматически при `make seed`. Пароль: `demo-pass-1234`

| Роль | Логины | Пароль | Где |
|---|---|---|---|
| **Кандидат** | `cand0001@demo.fsp.test` … `cand0400@demo.fsp.test` | `demo-pass-1234` | Профиль, тест, резюме |
| **Работодатель** | `hr01@demo.fsp.test` … `hr25@demo.fsp.test` | `demo-pass-1234` | Вакансии, подборка, офферы |
| **Админист.** | `admin@demo.fsp.test` | `demo-pass-1234` | Модерация, справочники, метрики |

Все данные вымышленные и генерируются детерминировано по семени (`SEED=20261003`).

## Доступ к интерфейсам

| Адрес | Назначение |
|---|---|
| **http://localhost:28080** | Основное приложение (SPA) |
| **http://localhost:28080/api/docs** | API документация (Swagger UI) |
| **http://localhost:28080/api/asyncapi** | События и команды (AsyncAPI) |

## Профили запуска

- **`lite`** (для жюри): без GPU, без LLM, ~1.5 ГБ ОЗУ
- **`standard`**: с LLM на CPU, ~4 ГБ ОЗУ
- **`full`**: с GPU и LLM, ~8 ГБ ОЗУ (обязательно наличие GPU)

Данные ядра навыков частично получены из Stack Overflow (CC BY-SA 4.0).
