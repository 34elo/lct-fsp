# Инструкция по развёртыванию

## Требования

### Для разработки и тестирования (стенд команды)
- **ОС:** Linux (Ubuntu 20.04+) или macOS с Docker
- **Процессор:** 4+ ядра  
- **ОЗУ:** 16+ ГБ (рекомендуется 32 ГБ для профиля `full`)
- **Хранилище:** 20+ ГБ свободного места (для образов, БД, моделей ML)
- **Сеть:** интернет-соединение для загрузки образов и моделей
- **Docker:** Docker Engine 24+ и Docker Compose v2.20+
- **Node.js:** 20+ (для `make api-gen` и фронтенда)
- **Python:** 3.12+ с `uv` (входит в состав)

**GPU (опционально):** AMD Radeon RX 5700 XT (RADV) или другая совместимая с Vulkan для ускорения LLM (`LLM_PROFILE=gpu`).

### Для стенда жюри
- **ОС:** Linux или другая ОС с Docker
- **Процессор:** ~8 ядер
- **ОЗУ:** 32–64 ГБ  
- **Хранилище:** 10+ ГБ
- **GPU:** не требуется
- **Docker Compose:** v2.20+
- **Node.js:** 20+ (необходимо для сборки фронтенда, но выполняется один раз)

Обязательный путь (регистрация → опрос → тест → категория → приглашение) работает без GPU и LLM, используя правила и кеш.

## Профили запуска

| Профиль | Команда | Для чего | LLM | ОЗУ прил.* |
|---|---|---|---|---|
| **`lite`** | `make up-lite` | Стенд жюри, разработка без GPU | отключена | ~1.2–1.5 ГБ |
| **`standard`** | `make up` + `LLM_PROFILE=cpu` | Стенд без GPU, демонстрация с LLM на CPU | CPU-фолбэк | ~4 ГБ |
| **`full`** | `make up` | Основной стенд с GPU | GPU (Vulkan) | ≈ 5–8 ГБ |

\* без БД, редиса, RabbitMQ, MinIO (они ~1–2 ГБ, лимитируются отдельно)

## Быстрый старт

### 1. Подготовка окружения

```bash
# Клонировать репозиторий (если ещё не клонировано)
git clone <repo-url> lct-fsp
cd lct-fsp

# Скопировать пример переменных окружения
cp .env.example .env

# Для развёртывания на хосте обновить CHANGE_ME:
#   - JWT_SECRET, PII_KEY, PSEUDO_ID_SECRET: любые криптостойкие строки
#   - SERVICE_TOKEN_*: случайные токены сервис-сервис
#   - S3_ACCESS_KEY, S3_SECRET_KEY: для MinIO (можно оставить как есть)
#   - TG_BOT_TOKEN: токен бота из @BotFather (необязателен для `lite`, опционален для `standard`)
#   - LLM_API_KEY: ключ из `~/.llm-keys` если используется локальный llama-server (для `full`)
```

### 2. Запуск (выберите один вариант)

**Для стенда жюри (lite, без GPU):**
```bash
make up-lite
make migrate
make taxonomy-load
make seed
# Приложение доступно на http://localhost:28080
```

**Для разработки с LLM на CPU (standard):**
```bash
LLM_PROFILE=cpu make up
make migrate
make taxonomy-load
make seed
```

**Для полного стенда с GPU (full):**
```bash
# Убедиться, что llama-server запущен на хосте (см. ниже)
make up
make migrate
make taxonomy-load
make seed
```

### 3. Проверка здоровья

```bash
# Статус контейнеров
make ps

# Логи приложения
make logs

# Проверка точек доступа (требует доступа из-под localhost):
curl http://localhost:28080/                       # шлюз (должна открыться SPA)
curl http://localhost:28080/api/docs               # Swagger OpenAPI (должен ответить 307)
curl http://localhost:28080/api/v1/healthz         # healthcheck (должен ответить 200)
curl http://localhost:28080/api/v1/taxonomy/professions  # справочник
```

## Инфраструктура и компоненты

### Docker Compose сервисы

Профиль **`core`** (всегда):
- `gateway` — маршрутизатор Caddy (порт 28080)
- `postgres` — база данных (порт 28432 на localhost, только 127.0.0.1)
- `redis` — кеш (порт 28379 на localhost, только 127.0.0.1)
- `rabbitmq` — очереди событий (порт 28672 UI, только WireGuard)
- `minio` — S3-хранилище (внутренний порт 9000)
- `core-api` — REST API и SSE
- `core-worker` — обработчик событий
- `core-scheduler` — планировщик cron-команд
- `fsp-connector` — интеграция с ФСП (своя БД)
- `bot` — Telegram-бот (если `TG_BOT_TOKEN` в `.env`)
- `fsp-mock` — имитация API ФСП

Профиль **`ml`** (если не `ML_FAKE=true`):
- `ml-api` — REST API для эмбеддингов и разбора
- `ml-worker-llm` — обработчик задач LLM (приоритет, `prefetch=1`)
- `ml-worker-code` — обработчик анализа кода (песочница)
- `web` — фронтенд (статика, собирается в `build/`)

Профиль **`llm`** (если LLM включена):
- `llm-chat` — локальный llama-server (контейнер с Vulkan). **Примечание:** в стенде разработчика используется общий `llama-server` на хосте, вне Compose.

Профиль **`dev`** (опционально):
- `dozzle` — UI логов (порт 8888, только WireGuard)
- `mailpit` — SMTP-сервис для тестирования почты (порт 28025, UI на http://127.0.0.1:28025)

### Порты на localhost

| Сервис | Порт | Доступ | Для чего |
|---|---|---|---|
| gateway | 28080 | WireGuard / localhost | HTTP-шлюз (http://localhost:28080) |
| RabbitMQ UI | 28672 | только WireGuard | Мониторинг очередей |
| PostgreSQL | 28432 | только 127.0.0.1 | Подключение `psql` |
| Redis | 28379 | только 127.0.0.1 | Подключение `redis-cli` |
| Mailpit UI | 28025 | только 127.0.0.1 | Просмотр писем |

### Внешние требования

**Общий llama-server (для профиля `full`):**
```bash
# На хосте вне Docker; обычно уже запущен для других проектов
llama-server -m <path-to-model> -ngl 99 -c 16384 --parallel 2 \
  -fa --host 127.0.0.1 --port 18090
# Сервисы подключаются через LLM_BASE_URL=http://host.docker.internal:18090/v1
```

## Типичные ошибки и решение

### 1. `EADDRINUSE: port 28080 already in use`
Другой процесс занял порт. Либо изменить `GATEWAY_PORT` в `.env`, либо:
```bash
make down
```

### 2. `failed to authenticate with 'postgres/postgres'`
Базы ещё не инициализированы. Выполнить инициализацию и миграции:
```bash
docker compose exec -T postgres /init.sh  # инициализация ролей и БД
make migrate
```

### 3. `reports/seed от root после первого запуска Docker`
На Linux Docker создаёт файлы от `root` при запуске из `docker compose exec`. Решение:
```bash
sudo chown -R $(id -u):$(id -g) reports/
```
Или использовать вместо `docker compose exec` команду `docker compose run --rm`.

### 4. `Node.js >= 20 required for pnpm`
При попытке запустить фронтенд проверить версию и обновить:
```bash
node --version  # должно быть v20+
# Если старше, обновить Node.js (см. requirements)
```

### 5. `pango or fonts library not found` при сборке PDF
Нужны системные пакеты для рендеринга PDF:
```bash
# Ubuntu/Debian
sudo apt-get install -y libpango1.0-dev fonts-dejavu fonts-noto

# Fedora/RHEL
sudo dnf install pango-devel liberation-fonts google-noto-fonts
```

### 6. Mailpit не запускается в профиле `dev`
Mailpit поднимается отдельно при `docker compose --profile dev up`. Чтобы включить по умолчанию:
```bash
# В Makefile или вручную:
docker compose --profile core --profile ml --profile dev up -d
```

## Внешние домены и HTTPS

### На стенде разработчика

Приложение доступно через docker-сеть (внутренние имена хостов):
- `http://gateway:80/` → маршруты по `Host: dashboard.fsp.patissons.tech` и т.д.
- Снаружи: `http://localhost:28080/`

TLS на стенде разработчика не обязателен.

### На production (через VPS и Tailscale)

Caddy на VPS (2.26.52.44) проксирует трафик через Tailscale на домашний ПК (100.78.22.33:28080) с TLS от Let's Encrypt:
```
dashboard.fsp.patissons.tech → caddy → :28080/dashboard.fsp.patissons.tech
api.fsp.patissons.tech → caddy → :28080/api.fsp.patissons.tech
s3.fsp.patissons.tech → caddy → :28080/s3.fsp.patissons.tech
mock.fsp.patissons.tech → caddy → :28080/mock.fsp.patissons.tech
```

## Основные команды

```bash
# Поднять весь стек (по умолчанию full с GPU)
make up

# Альтернативы
make up-lite        # lite: без LLM
make dev-core       # только core + ML_FAKE=true

# Остановить
make down

# Инициализация данных
make migrate         # миграции Alembic
make taxonomy-load   # загрузка справочников (skills, professions, rules)
make seed            # генерация 400 кандидатов, 25 компаний и т.д. (детерминировано, SEED=20261003)

# Снимок и восстановление демо-данных
make demo-snapshot   # сохранить текущее состояние в infra/snapshots/
make demo-reset      # восстановить из снимка + теплый старт

# Мониторинг и отладка
make ps              # список контейнеров
make logs            # live логи (последние 50 строк)
make compose-config  # вывести итоговый compose-файл

# Тесты и качество
make test            # pytest + vitest
make lint            # ruff + eslint
make eval            # метрики качества теста/подбора

# Экспорт
make openapi         # сгенерировать docs/openapi.json
make asyncapi        # сгенерировать docs/asyncapi.json

# Генерация кода
make api-gen         # orval: генерировать hooks из OpenAPI для фронта
```

## Работа с данными

### Демо-аккаунты

Автоматически создаются при `make seed`. По умолчанию (см. `tools/seed/config.yaml`):

| Роль | Логин | Пароль | Для чего |
|---|---|---|---|
| Кандидат | `cand0001@demo.fsp.test` … `cand0400@demo.fsp.test` | `demo-pass-1234` | Профиль, тест, резюме |
| Работодатель | `hr01@demo.fsp.test` … `hr25@demo.fsp.test` | `demo-pass-1234` | Вакансии, подборка, офферы |
| ФСП участник | `participant0001@example.test` … | `demo-pass-1234` | Результаты соревнований (fsp-mock) |
| Админист. | `admin@demo.fsp.test` | `demo-pass-1234` | Модерация, справочники, метрики |

Все 400 кандидатов и 25 компаний вымышленные.

### Изменение семени данных

```bash
# Другое семя (влияет на имена, профили, результаты)
SEED=12345 make seed

# Очистить и пересоздать (осторожно: удаляет данные!)
make demo-reset
```

### Снимок БД

```bash
# Сохранить текущее состояние
make demo-snapshot
# Создаст infra/snapshots/demo.sql.gz и загрузит MinIO в infra/snapshots/minio/

# Восстановить
make demo-reset
# Восстановит из снимков и выполнит make demo-warm
```

## Масштабирование и производительность

### Лимиты ресурсов

В `docker-compose.yml` установлены лимиты:
- **core-api / core-worker / core-scheduler:** 512 МБ каждый
- **ml-api:** 4 ГБ (с моделью)
- **postgres:** 2 ГБ
- **redis:** 1 ГБ (`maxmemory=1g`, `allkeys-lru`)

Для стенда жюри эти лимиты остаются, но общее ОЗУ должно быть ≥ 32 ГБ.

### Если не хватает памяти

1. Использовать `make up-lite` (отключить LLM, меньше моделей)
2. Уменьшить количество семей и профилей в `tools/seed/config.yaml`
3. Увеличить лимиты в `docker-compose.yml` (осторожно: может привести к свопу)

## Здоровье и диагностика

### Проверка компонентов

```bash
# API живо?
curl -s http://localhost:28080/api/v1/healthz | jq .

# Граница доступна?
curl -s http://localhost:28080/ | head -1

# PgSQL?
psql postgresql://core:core@127.0.0.1:28432/core -c "SELECT 1"

# Redis?
redis-cli -p 28379 PING

# RabbitMQ?
curl -s http://guest:guest@127.0.0.1:28672/api/overview | jq .management_version
```

### Логи

```bash
# Последние 100 строк от core-api
docker compose logs -n 100 core-api

# Follow core-api и core-worker
docker compose logs -f core-api core-worker

# Только ошибки
docker compose logs --tail 50 core-api | grep -i error
```

### Профилирование

Prometheus и Grafana доступны через профиль `obs`:
```bash
docker compose --profile obs up -d
# Prometheus: http://localhost:28090 (через WireGuard)
# Grafana: http://localhost:28300 (через WireGuard)
```

## Нюансы и оговорки

1. **LLM-модели:** допустимы облачные, в том числе зарубежные, предпочтительны открытые модели адекватного размера; инференс-серверы и оплату API организует участник. У нас — локальная открытая модель (ADR-027).
2. **ML заглушки:** при `LLM_ENABLED=false` функции ML работают по правилам (разбор резюме, запросов, скоринг); LLM-команды отвечают заглушками.
3. **Параллелизм:** `ml-worker-llm` с `prefetch=1` обрабатывает одну задачу за раз (LLM не параллелится без GPU).
4. **Демо-мод:** с флагом `DEMO_MODE=true` на лендинге появляются кнопки для сброса и загрузки нового результата ФСП (E13-3).

## Дополнительные ссылки

- [Архитектура развёртывания](../architecture/deployment.md) — топология, Compose-сервисы, переменные
- [OpenAPI](../openapi.json) — справочник REST API
- [AsyncAPI](../asyncapi.json) — каталог событий и команд
- [Вопросы жюри](../notes/qa-2026.md) — критерии оценки, требования к стенду
