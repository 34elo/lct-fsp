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

# Для lite (стенд жюри) отдельный .env не нужен: `make up-lite` сам создаёт .env.demo со случайными секретами.
# Для остальных профилей скопировать пример переменных окружения:
cp .env.example .env

# Для развёртывания на хосте обновить CHANGE_ME:
#   - JWT_SECRET, PII_KEY, PSEUDO_ID_SECRET: любые криптостойкие строки
#   - SERVICE_TOKEN_*: случайные токены сервис-сервис
#   - S3_ACCESS_KEY, S3_SECRET_KEY: для MinIO (можно оставить как есть)
#   - TG_BOT_TOKEN: токен бота из @BotFather (необязателен для `lite`, опционален для `standard`)
#   - LLM_API_KEY: ключ из `~/.llm-keys` если используется локальный llama-server (для `full`)
```

### 2. Запуск (выберите один вариант)

**Для стенда жюри (lite, без GPU и LLM):**
```bash
make up-lite     # сборка, миграции и справочники (сервис core-migrate), без LLM
make seed        # демо-данные и демо-аккаунты
# Приложение доступно на http://localhost:28080
```

**Для разработки с LLM на CPU (standard):**
```bash
LLM_PROFILE=cpu make up
make seed
```

**Для полного стенда с GPU (full):**
```bash
# Убедиться, что llama-server запущен на хосте (см. ниже)
make up
make seed
```

Миграции БД и загрузка справочника (`alembic upgrade head`, `python -m app.taxonomy`) выполняются сервисом `core-migrate` при каждом `make up`/`make up-lite`; отдельных команд не нужно.

### 2a. Windows без make

`make` на Windows обычно нет. Команды выше можно выполнять вручную из **Git Bash** (нужны Docker Desktop, `uv`, Node.js 20+ с pnpm). Из корня репозитория:

```bash
sh infra/scripts/gen-demo-env.sh                      # .env.demo (как make demo-env)
mkdir -p reports/seed
LLM_ENABLED=false ML_FAKE=false EMBEDDING_MODEL=multilingual-e5-small \
  docker compose --env-file .env.demo --profile core --profile ml up -d --build --wait

uv run python -m tools.seed all --env-file .env.demo
uv run python -m tools.seed grades --env-file .env.demo
uv run python -m tools.seed demo2 --env-file .env.demo
docker compose --env-file .env.demo --profile core up -d --build --no-deps --force-recreate fsp-mock
```

Это последовательность `make up-lite` и `make seed` из Makefile (`SEED` по умолчанию берётся из `tools/seed/config.yaml`). Скрипты `*.sh` должны сохраниться с окончаниями LF (правило в `.gitattributes`): если стек падает на `set -eu` в `rabbitmq-init`, проверьте окончания строк и перекачайте репозиторий.

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
Роли и базы создаются при первом старте postgres (`infra/postgres/init.sh`); если том создан со старыми паролями, стенд не подключается. Смотрите `docker compose --env-file .env.demo logs postgres core-migrate`. Чистый перезапуск с удалением данных стенда (осторожно):
```bash
make down
docker compose --env-file .env.demo --profile core down -v   # удаляет тома стенда
make up-lite
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

Конфиг и установка — [infra/vps](../infra/vps/README.md). Caddy на VPS (2.26.52.44) проксирует трафик через Tailscale на домашний ПК (100.78.22.33:28080) с TLS от Let's Encrypt:
```
dashboard.fsp.patissons.tech → caddy → :28080/dashboard.fsp.patissons.tech
api.fsp.patissons.tech → caddy → :28080/api.fsp.patissons.tech
s3.fsp.patissons.tech → caddy → :28080/s3.fsp.patissons.tech
mock.fsp.patissons.tech → caddy → :28080/mock.fsp.patissons.tech
```

## Прод: инфраструктура и CI/CD

```
GitHub (main) ──push──▶ Actions: ci.yml (облачные раннеры) ──▶ cd.yml: deploy (self-hosted раннер на сервере)
Пользователь ──HTTPS──▶ VPS 2.26.52.44 (Caddy, Let's Encrypt) ──Tailscale──▶ сервер :28080 gateway ──▶ стек fsp
Бот платформы ──Tailscale──▶ VPS :28443 (ретранслятор Bot API) ──▶ api.telegram.org   (напрямую с сервера Telegram недоступен)
Сервер: таймер fsp-backup (03:30) ──▶ ~/fsp-backups;  hostwatch (@patissons_alerts_bot) ──▶ алерты команде
VPS: hostwatch-watchdog ──▶ алерт, если сервер пропал > 4 мин
```

**Один стенд — прод** (`STAND_DIR` на сервере, compose-проект `fsp`): `ENV=prod`, реальная LLM на GPU, Telegram-бот, демо-аккаунты жюри (`DEMO_MODE`, `VITE_JURY_MODE`). Почта не подключена.

**LLM** — общий llama-server хоста (`:18090`, Qwen3-VL-4B, OpenAI-совместимый API, 2 слота на одной GPU). Его же использует другой прод на этой машине: наш `ml-worker-llm` берёт из очереди по одному запросу (`prefetch=1`), лишнюю нагрузку не создаём. Ключ — строка `LLM_API_KEY_LINE` файла `LLM_API_KEY_FILE` (`~/hackathon-server-setup/llm/api-keys.txt`), в GitHub не хранится.

### Где что лежит

| Что | Где | Кто меняет |
|---|---|---|
| Конфигурация (не секреты): домены, режимы, LLM, бэкапы | [`infra/env/prod.env`](../infra/env/prod.env) в репо | PR в `main` |
| Внутренние секреты: пароли БД, RabbitMQ, MinIO, JWT, ключи шифрования, сервисные токены | `STAND_DIR/.env.server` (600), создаётся один раз [`gen-server-secrets.sh`](../infra/scripts/gen-server-secrets.sh) | никто: не уходят с сервера |
| Токен бота платформы | GitHub → Settings → Environments → `prod` | владелец репозитория |
| Ключ LLM | файл ключей llama-server на сервере (строка из `prod.env`) | владелец сервера |
| Токен бота алертов | `config.toml` hostwatch на сервере (`HOSTWATCH_DIR`) | владелец сервера |
| Итоговый `.env` | `STAND_DIR/.env`, собирается [`render-env.sh`](../infra/scripts/render-env.sh) при каждом деплое | не править руками |

**Окружение GitHub `prod`:**

| Тип | Имя | Что |
|---|---|---|
| Secret | `TG_BOT_TOKEN` | токен бота платформы из @BotFather |
| Variable | `TG_BOT_USERNAME` | username бота платформы без `@` |

**Переменная репозитория:** `STAND_DIR` — каталог стенда на сервере (Settings → Secrets and variables → Actions → Variables).

### Пайплайн

Pull request → [`ci.yml`](../.github/workflows/ci.yml) на облачных раннерах (ruff, import-linter, сверка OpenAPI, pytest, families/cards-check, фронт). Push в `main` → [`cd.yml`](../.github/workflows/cd.yml): те же проверки → деплой ([`deploy.sh`](../infra/scripts/deploy.sh)):

1. каталог стенда переходит на коммит (забирает его из копии раннера, без своих ключей к GitHub);
2. собирается `.env`; без нужных секретов деплой останавливается с их списком;
3. бэкап (`pre-<коммит>`);
4. `make up` — сборка образов, миграции (`core-migrate`), запуск;
5. проверка API, SPA и справочника до 3 минут;
6. смоук ML ([`smoke-ml.sh`](../infra/scripts/smoke-ml.sh), E42-6): `ml-api /healthz` (embedder не `down`; `fallback` допустим), `POST /v1/embeddings` → 200, короткий запрос к LLM (при `LLM_ENABLED=true`: недоступный llama-server или пустой/неверный `LLM_API_KEY` — сбой), бот запущен и не перезапускается (при заданном `TG_BOT_TOKEN`); поле `llm` из `/healthz` не смотрим — оно отражает режим `ML_FAKE`, а не доступность llama-server;
7. успех — чистка образов, обновление таймеров, сообщение в чат алертов; сбой (в том числе смоука) — откат кода на прежний коммит и сообщение с причиной (`FAIL <проверка>: <причина>`).

Операции идут строго по одной (`concurrency: stand`). Откат возвращает код, но не миграции: миграция в `main` должна быть совместима с прежним кодом (добавляем, не удаляем и не переименовываем в том же релизе).

**Ручные действия** — Actions → `cd` → Run workflow (ветка `main`):

| Действие | Что делает |
|---|---|
| `deploy` | Проверки и деплой текущего `main` |
| `backup` | Внеочередной бэкап |
| `demo-reset` | Только демо-данные (`is_demo`: герои, жюри, их приглашения) из снапшота за секунды и прогрев — перед показом жюри; реальные регистрации не трогаются (E40-1) |
| `demo-reseed` | Заново наполнить демо (`make seed`) и снять снапшот (после обновления до E40-1 — один раз обязательно: старый `pg_dump`-снапшот не подходит) |
| `demo-e2e` | e2e демо-сценария против прода (`apps/web/e2e/b2-prod-demo.spec.ts`, только демо-аккаунты) на раннере GitHub; адрес — переменная репозитория `E2E_PROD_URL` |
| `prod-init` | **Один раз**, поле `confirm` = `ПЕРЕСОЗДАТЬ`: бэкап старого стенда → удаление томов → новые внутренние секреты → запуск → демо-данные (при сбое шага хвост вывода уходит в алерт, шаг повторяем) → снапшот → таймеры |

### Бэкапы и восстановление

[`backup.sh`](../infra/scripts/backup.sh): `pg_dump` баз `core` и `fsp_connector` (проверяются `pg_restore --list`), архив тома MinIO, коммит стенда → `BACKUP_DIR/<время>-<метка>/`. Ночью в 03:30 (таймер `fsp-backup`), перед каждым деплоем и по кнопке; хранение `BACKUP_KEEP_DAYS` (7 дней). Восстановление (из каталога стенда):

```bash
sh infra/scripts/restore.sh ~/fsp-backups/<каталог> --yes
```

### Мониторинг и алерты

Мониторинг сервера — бот **hostwatch** (`@patissons_alerts_bot`, `~/everything/develop/hostwatch-bot`, своё README): раз в минуту ресурсы, GPU, Docker-контейнеры, HTTP-адреса; тревога после двух неудач подряд, «Поднялось» при починке. Стенд в нём: проект `fsp` в `important_projects` (упавший или unhealthy контейнер — красная тревога), адреса «ФСП: сайт», «ФСП: API» снаружи и локально. Пропажу всей машины ловит `hostwatch-watchdog` на VPS.

Деплои, откаты, сброс демо — сообщения тем же ботом всем его подписчикам ([`notify.sh`](../infra/scripts/notify.sh): токен из `config.toml` hostwatch, чаты из `state.json`, через ретранслятор). Команды бота: `/status`, `/docker`, `/web`, `/logs <контейнер>`.

### Настройка с нуля

1. Раннер: `sh infra/scripts/install-runner.sh` на сервере (токен: Settings → Actions → Runners → New self-hosted runner).
2. Переменная репозитория `STAND_DIR`, окружение `prod` с секретами и переменными из таблицы выше.
3. VPS: DNS, Caddy и ретранслятор Telegram — [infra/vps/README.md](../infra/vps/README.md).
4. hostwatch: проект `fsp` в `important_projects`, адреса стенда в `[web].urls`, `./restart.sh`.
5. Влить `dev` в `main` → первый `deploy`; затем Run workflow → `prod-init` с `ПЕРЕСОЗДАТЬ`.

## Основные команды

```bash
# Поднять весь стек (профили core, ml, llm; нужен LLM-сервер или LLM_ENABLED=false)
make up

# Альтернативы
make up-lite        # lite: без LLM (миграции и справочники — в core-migrate)
make dev-core       # только core + ML_FAKE=true

# Остановить
make down

# Инициализация данных
make seed            # генерация 400 кандидатов, 25 компаний и т.д. (детерминировано, SEED=20261003)

# Снимок и восстановление демо-данных
make demo-snapshot   # снапшот только демо-строк (таблицы demo_snap__* в БД core и fsp_connector)
make demo-reset      # вернуть только демо к снапшоту (реальные регистрации не трогаются)

# Мониторинг и отладка
make ps              # список контейнеров
make logs            # live логи (последние 50 строк)
make compose-config  # вывести итоговый compose-файл

# Тесты и качество
make test            # pytest + vitest
make lint            # ruff + eslint + проверка ссылок в docs (make docs-links)
make deadcode        # мёртвый код: knip (фронт) и vulture (Python)
make eval            # метрики качества теста/подбора
cd apps/web && pnpm e2e   # Playwright на поднятом стеке с сидом (см. ниже)

# Экспорт (не требует запущенного стека)
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
| Жюри, кандидат (без грейда, экспресс-тест) | `jury-candidate@demo.fsp.test` | `demo-pass-1234` | Путь по ТЗ за 3–5 минут |
| Жюри, работодатель (проверенная компания) | `jury-hr@demo.fsp.test` | `demo-pass-1234` | Поиск категории, приглашение |
| Герои демо | `anya@`, `dima@`, `olga@demo.fsp.test` | `demo-pass-1234` | Сценарии из `tools/seed/heroes/` (Ольга — работодатель «Северный код») |
| Кандидаты | `cand0001@demo.fsp.test` … `cand0400@demo.fsp.test` | `demo-pass-1234` | Профиль, тест, резюме |
| Работодатели | `hr01@demo.fsp.test` … `hr25@demo.fsp.test` | `demo-pass-1234` | Вакансии, подборка, офферы |
| ФСП участник | `participant0001@example.test` … | `demo-pass-1234` | Результаты соревнований (fsp-mock) |
| Администратор | `admin@demo.fsp.test` | `demo-pass-1234` | Модерация, справочники, метрики |

Пароль — тестовый, из `tools/seed/config.yaml`. Все люди и компании вымышленные. Актуальный список логинов печатает `make seed` в конце.

### E2E-тесты (Playwright)

На поднятом стенде с сидом (`make up-lite && make seed`):
```bash
cd apps/web
pnpm install          # при первом запуске; нужен Node.js 20+
pnpm e2e              # по умолчанию E2E_BASE_URL=http://localhost:28080
```
- Системный Chrome вместо скачанного Chromium: `E2E_CHANNEL=chrome pnpm e2e` (без `playwright install`).
- Лимит входа на сервере — 5 попыток в минуту на email и 10 на IP. Хелперы `apiLogin` кешируют токен и при 429 ждут окно (до 4 раз по 20 с), поэтому полный прогон может идти несколько минут; это ожидание, а не зависание.
- Аккаунты и пути героев — в `apps/web/e2e/fixtures.ts`; без `make seed` тесты не найдут данные.

### Изменение семени данных

```bash
# Другое семя (влияет на имена, профили, результаты)
SEED=12345 make seed

# Вернуть демо к снапшоту (реальные регистрации не трогаются)
make demo-reset
```

### Снимок БД

```bash
# Снять снапшот демо (сразу после make seed)
make demo-snapshot
# Демо-строки (is_demo) -> таблицы demo_snap__* в БД core и fsp_connector, fsp-mock.json -> infra/snapshots/

# Вернуть демо к снапшоту
make demo-reset
# Удалит всё, что касается демо (в т.ч. песочницы жюри), и вернёт строки снапшота; стек не останавливается
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

- [Архитектура развёртывания](architecture/deployment.md) — топология, Compose-сервисы, переменные
- [OpenAPI](openapi.json) — справочник REST API
- [AsyncAPI](asyncapi.json) — каталог событий и команд
- [Вопросы жюри](notes/qa-2026.md) — критерии оценки, требования к стенду
