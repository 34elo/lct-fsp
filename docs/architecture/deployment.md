# Развёртывание

> Требование кейса: «развёрнутый и доступный для демонстрации MVP, инструкция по развёртыванию». Этот документ — архитектура развёртывания. Пошаговая инструкция для жюри появится в `docs/deploy.md`, когда будет код (задача E0 в бэклоге).

## 1. Топология (фактическая)

```mermaid
flowchart LR
  user([Пользователи / жюри]) -->|HTTPS 443| caddy
  subgraph VPS["VPS 2.26.52.44 · Caddy (общий с другим проектом)"]
    caddy[Caddy edge<br/>TLS Let's Encrypt<br/>*.fsp.patissons.tech]
  end
  caddy -->|Tailscale 100.78.22.33:28080<br/>Host сохраняется| gw
  subgraph HOME["Домашний ПК elo · Docker Compose"]
    gw[gateway: Caddy<br/>:28080 · роутинг по Host]
    gw -->|dashboard.fsp| web[web static]
    gw -->|api.fsp| api[core-api]
    gw -->|mock.fsp| mock[fsp-mock]
    gw -->|s3.fsp| s3[(minio)]
    gw -->|api.fsp /integrations/fsp| fspc[fsp-connector]
    mq{{rabbitmq}}
    api --- pg[(postgres)]
    api --- rd[(redis)]
    api --> mlapi[ml-api]
    api --> fspc
    cw[core-worker + core-scheduler] --- pg
    api & cw & mlw & fspc & bot --- mq
    mlw[ml-worker-llm, ml-worker-code]
    bot[bot] --> api
    fspc --> mock
  end
  mlapi & mlw -->|OpenAI API + ключ| llm[общий llama-server<br/>Qwen3-VL-4B · :18090 на хосте]
  bot -->|исходящий HTTPS| tg[(api.telegram.org)]
  mlw -->|исходящий HTTPS| gh[(github.com)]
```

- **VPS** (Caddy, без Docker) делает только TLS и проксирование через Tailscale. На нём же работают сайты другого проекта (`patissons.tech`, `dashboard.`, `api.`, `llm.`, `s3.patissons.tech`) — их не трогаем. Наши сайты лежат в отдельном файле `/etc/caddy/fsp.caddy`.
- **Домашний ПК** (`elo`, Tailscale `100.78.22.33`) держит весь compose. Снаружи доступен **один порт — gateway `28080`**, он роутит по заголовку `Host`. Остальные сервисы торчат только во внутреннюю docker-сеть.
- **Порты на ПК заняты другим проектом**: 3000, 8000, 13000, 15432, 15673, 18000–18007, 18090, 19000–19001, 25672 и др. Наши порты на хосте — диапазон **28xxx**.

### Домены

| Домен | Куда (через gateway) | Зачем |
|---|---|---|
| `fsp.patissons.tech` | редирект на `dashboard.fsp…` | Короткий адрес |
| `dashboard.fsp.patissons.tech` | `web` (SPA) | Весь интерфейс: лендинг, кандидат, работодатель, админка ФСП (`/federation`, `/admin`) |
| `api.fsp.patissons.tech` | `core-api` (+ `/integrations/fsp/*` → `fsp-connector`) | REST, SSE, Swagger `/api/docs`, AsyncAPI, бейджи, OG |
| `mock.fsp.patissons.tech` | `fsp-mock` | Страница «Войти через ФСП» открывается в браузере пользователя |
| `s3.fsp.patissons.tech` | `minio` (S3 API, только GET по presigned-ссылкам) | Скачивание PDF и файлов |

Отдельный поддомен под админку не нужен: это разделы SPA. RabbitMQ UI (`:28672`) и Grafana (`:28300`) доступны только из Tailscale-сети команды, наружу не публикуются.

**Следствия для кода:**
- SPA и API на разных поддоменах одного сайта. CORS разрешает только `https://dashboard.fsp.patissons.tech`, с credentials.
- Refresh-cookie: `Domain=api.fsp.patissons.tech`, `SameSite=Lax`, `Secure`.
- SSE — `EventSource(..., {withCredentials: true})`.
- `VITE_API_URL=https://api.fsp.patissons.tech`.
- Telegram Login Widget: в @BotFather → `/setdomain` → `dashboard.fsp.patissons.tech`.
- OAuth мока: `redirect_uri = https://api.fsp.patissons.tech/api/v1/auth/fsp/callback`.

### Caddy на VPS (`/etc/caddy/fsp.caddy`)

```caddyfile
fsp.patissons.tech {
	redir https://dashboard.fsp.patissons.tech{uri}
}

dashboard.fsp.patissons.tech, mock.fsp.patissons.tech, s3.fsp.patissons.tech {
	encode zstd gzip
	reverse_proxy 100.78.22.33:28080
	log {
		output file /var/log/caddy/fsp.log
	}
}

api.fsp.patissons.tech {
	request_body {
		max_size 25MB
	}
	reverse_proxy 100.78.22.33:28080 {
		flush_interval -1
		transport http {
			read_timeout 600s
			write_timeout 600s
		}
	}
	log {
		output file /var/log/caddy/fsp-api.log
	}
}
```

**Статус (2026-10-02):** `fsp.caddy` подключён через `import` в основном Caddyfile. Сертификаты Let's Encrypt выданы для `dashboard.`, `api.`, `s3.fsp`. Пока на домашнем ПК не запущен gateway на `:28080`, они отвечают 502. Блоки `mock.fsp` и `fsp.patissons.tech` закомментированы до появления A-записей: раскомментировать и выполнить `systemctl reload caddy`.

- Проверка и применение: `caddy validate --config /etc/caddy/Caddyfile && systemctl reload caddy`. Reload атомарный: при ошибке остаётся старый конфиг.
- Новые лог-файлы в `/var/log/caddy` нужно создать заранее с владельцем `caddy` (`touch … && chown caddy:caddy …`), иначе reload падает с «opening log writer».
- Бэкапы рядом: `Caddyfile.bak-<дата>-fsp`, `fsp.caddy.bak-<дата>`.
- На `api.fsp` нет сжатия и есть `flush_interval -1`, иначе SSE буферизуется.

## 2. Compose-сервисы

| Сервис | Образ / сборка | Порты (внутр.) | Ресурсы (ориентир) | Профиль |
|---|---|---|---|---|
| `gateway` | caddy:2, роутинг по `Host` для `dashboard.`, `api.`, `mock.`, `s3.fsp.patissons.tech` | 80 → **хост 28080** | — | core |
| `web` | сборка `apps/web` → статика в gateway (multi-stage) | — | — | core |
| `core-api` | `services/core` | 8000 | 1 CPU, 512 МБ | core |
| `core-worker` | `services/core` (FastStream-подписчики) | — | 1 CPU, 512 МБ | core |
| `core-scheduler` | `services/core` (APScheduler → команды в RabbitMQ) | — | 128 МБ | core |
| `fsp-connector` | `services/fsp-connector` (API + подписчик, своя БД `fsp_connector`) | 8300 | 256 МБ | core |
| `bot` | `services/bot` | — | 256 МБ | core |
| `rabbitmq` | rabbitmq:3.13-management (или 4.x) | 5672, 15672 (веб-интерфейс только через WG) | 512 МБ, volume `rabbitdata` | core |
| `fsp-mock` | `services/fsp-mock` | 8200 | 256 МБ | core |
| `postgres` | pgvector/pgvector:pg16 | 5432 | 2 ГБ, volume `pgdata` | core |
| `redis` | redis:7 (+ `redis.conf`: `allkeys-lru`) | 6379 | 1 ГБ maxmemory, без персистентности | core |
| `minio` | quay.io/minio/minio (на Docker Hub образа нет) | 9000, 9001 | volume `minio` | core |
| `ml-api` | `services/ml` (+ модель эмбеддингов в volume) | 8100 | 2 CPU, 4 ГБ | ml |
| `ml-worker-llm` | `services/ml` (очередь `ml.llm`, `prefetch=1`) | — | 1 CPU, 2 ГБ | ml |
| `ml-worker-code` | `services/ml` (очередь `ml.code`, tmpfs 1 ГБ, ограничения из security §6) | — | 2 CPU, 2 ГБ | ml |
| `llm-chat` | **уже запущен отдельно** на ПК: `llama-server` с Qwen3-VL-4B Q4 (общий с другим проектом, хостовый порт 18090, ключ API). В наш compose не входит, сервисы ml ходят по `LLM_BASE_URL` | — | GPU | — |
| `dozzle` | amir20/dozzle | 8888 (только через WG) | — | dev |
| `mailpit` | axllent/mailpit | 28025 (UI, 127.0.0.1) | — | dev |
| `prometheus` | prom/prometheus (+ `infra/prometheus.yml`: core, ml, fsp-connector, rabbitmq:15692, llm-chat, exporters) | 9090 (через WG) | 512 МБ | obs |
| `grafana` | grafana/grafana (+ дашборды `infra/grafana/*.json`) | 3000 (через WG) | 256 МБ | obs |
| `postgres-exporter`, `redis-exporter` | prometheuscommunity/postgres-exporter, oliver006/redis_exporter | — | 64 МБ | obs |

**Профили:** `docker compose --profile core --profile ml --profile llm up -d`. Фронтендер может запускать только `core` + мок ML (`ML_FAKE=true` отдаёт заготовленные ответы), чтобы не зависеть от GPU.

**Профили запуска (ADR-023, E20-8):**

| Профиль | Команда | LLM | Эмбеддинги | RAM сервисов приложения* |
|---|---|---|---|---|
| `lite` | `make up-lite` | нет: `LLM_ENABLED=false`, `ML_FAKE=false`; каждая функция идёт правилами ([solution.md §3](../solution.md)) | `multilingual-e5-small` (384, ml-api добивает нулями до 1024) | ≈ 1.2–1.5 ГБ: core-api/worker/scheduler ~0.9, ml-api ~0.4 (с малой моделью), ml-worker-* ~0.15 |
| `standard` | `make up` + малая LLM на CPU (`LLM_PROFILE=cpu`) | да, CPU | bge-m3 | ≈ 4 ГБ |
| `full` | `make up` | да, GPU (общий `llama-server`) | bge-m3 | наш стенд |

**Стенд жюри** (ADR-025, [notes/qa-2026.md](../notes/qa-2026.md) §6): ориентир 32–64 ГБ RAM, ~8 CPU, **без GPU**. Обязательный путь (регистрация → опрос → тест → категория → приглашение) от GPU и LLM не зависит; на таком стенде работает `standard` с российской открытой моделью на CPU (выбор — E32-3) или `lite`. Проверяют на нашем стенде после дедлайна: упавший контейнер можно поднять, менять идею нельзя (E32-8).

\* без postgres/redis/rabbitmq/minio (≈ 1–2 ГБ, настраиваются лимитами). Цифры ориентировочные, замер — при первом запуске lite. Без LLM: разбор резюме идёт словарём графа (`resume-rules-v2`: навык только с цитатой из текста; опыт, образование, периоды и город — правила по разделам и датам, Natasha как запасной путь, E30-4), разбор запроса работодателя — правилами, остальные LLM-команды отвечают заглушкой до своих правиловых реализаций. Переменные: `LLM_ENABLED`, `EMBEDDING_MODEL`, `EMBEDDING_MODEL_PATH`.

**Состояние (E0-2):** `docker-compose.yml` в корне содержит инфраструктуру профиля `core` (gateway, postgres, redis, rabbitmq, minio) и `dozzle` (`dev`); сервисы приложения добавляются своими задачами. Разовая инициализация: `infra/postgres/init.sh` (роли `core`, `fspc`, базы `core`, `fsp_connector`, расширения `vector`, `pg_trgm`), `rabbitmq-init` (vhost `fsp`, пользователи `core`, `ml`, `fspc`, `bot`), `minio-init` (бакет). Порты на хосте: gateway 28080, RabbitMQ UI 28672, Postgres 28432, Redis 28379 (последние три только на 127.0.0.1). Маршруты gateway — `infra/caddy/Caddyfile`. Первый запуск: `cp .env.example .env`, заменить `CHANGE_ME`, `make up`.

## 3. GPU: RX 5700 XT + Vulkan

1. На хосте: Mesa с RADV (`mesa-vulkan-drivers`), проверка `vulkaninfo --summary` — видна `AMD Radeon RX 5700 XT (RADV NAVI10)`.
2. **Вариант A (контейнер):** `ghcr.io/ggml-org/llama.cpp:server-vulkan`, `devices: ["/dev/dri:/dev/dri"]`, `group_add: [video, render]`.
   **Вариант B (нативно, если контейнер капризничает):** собрать llama.cpp с `-DGGML_VULKAN=ON`, systemd-юнит, слушает `0.0.0.0:8080` в docker-сети через `host.docker.internal`.
3. Команда запуска (ориентир):
   ```
   llama-server -m /models/<chat-model>-Q4_K_M.gguf -ngl 99 -c 16384 --parallel 2 \
     -fa --cache-type-k q8_0 --cache-type-v q8_0 --host 0.0.0.0 --port 8080 --metrics
   ```
4. Проверка: `curl :8080/health`, `tools/eval/bench_llm.py` (скорость и качество, [ml.md §1.2](ml.md#12-выбор-моделей)).
5. **CPU-фолбэк:** `LLM_PROFILE=cpu` → маленькая модель (3–4B Q4) в отдельном `llama-server` на CPU. Медленно, но демо не встанет.

## 4. Переменные окружения (`.env.example`)

```dotenv
# общие
ENV=dev                         # dev | demo | prod
DOMAIN=fsp.patissons.tech
WEB_ORIGIN=https://dashboard.fsp.patissons.tech
API_ORIGIN=https://api.fsp.patissons.tech
GATEWAY_PORT=28080
DEMO_MODE=false                 # включает /admin/demo/*, кнопку сброса
# core
DATABASE_URL=postgresql+asyncpg://fsp:fsp@postgres:5432/fsp
REDIS_URL=redis://redis:6379/0
RABBITMQ_URL=amqp://core:…@rabbitmq:5672/fsp     # свой пользователь на сервис, vhost fsp
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=…
S3_SECRET_KEY=…
S3_BUCKET=fsp
JWT_SECRET=…
PII_KEY=…                       # Fernet
PSEUDO_ID_SECRET=…
SERVICE_TOKEN_BOT=…
SERVICE_TOKEN_ML=…
SERVICE_TOKEN_MOCK=…
ML_API_URL=http://ml-api:8100
# ФСП
# fsp-connector
FSP_CONNECTOR_URL=http://fsp-connector:8300      # для core-api (OAuth, привязка)
FSP_CONNECTOR_DATABASE_URL=postgresql+asyncpg://fspc:…@postgres:5432/fsp_connector
FSP_ADAPTER=mock                # mock | organizers | real
FSP_BASE_URL=http://fsp-mock:8200
FSP_PUBLIC_URL=https://mock.fsp.patissons.tech   # для OAuth-редиректа в браузере
S3_PUBLIC_URL=https://s3.fsp.patissons.tech       # presigned-ссылки
FSP_API_KEY=…
FSP_WEBHOOK_SECRET=…
FSP_OAUTH_CLIENT_ID=platform
FSP_OAUTH_CLIENT_SECRET=…
# Telegram
TG_BOT_TOKEN=…
TG_BOT_USERNAME=…
# ML
LLM_PROFILE=gpu                 # gpu | cpu
LLM_BASE_URL=http://host.docker.internal:18090/v1   # общий llama-server на ПК (снаружи — llm.patissons.tech)
LLM_API_KEY=…                   # ключ из ~/hackathon-server-setup/llm/api-keys.txt (общий с другим проектом)
LLM_MODEL=qwen3-vl-4b
EMBED_MODEL=BAAI/bge-m3
EMBED_DIM=1024
GITHUB_TOKEN=…                  # fine-grained, только public read
ML_FAKE=false                   # заглушки ML для фронта
# аналитика и бейджи
ANALYTICS_SALT=…
OB_SIGNING_KEY=…                # Ed25519, Open Badge 3.0
OB_ISSUER_DID=did:web:fsp.patissons.tech
```

## 5. Makefile (целевые команды)

| Команда | Что делает |
|---|---|
| `make up` / `make down` | Поднять / остановить все профили |
| `make up-lite` | Профиль lite: ядро и ML без LLM (ADR-023) |
| `make dev-core` | Только core-профиль + `ML_FAKE=true` |
| `make migrate` | `alembic upgrade head` |
| `make taxonomy-load` | Загрузить `data/taxonomy/*.yaml`, `data/fsp/discipline_rules.yaml`, банк вопросов |
| `make seed` | Сгенерировать демо-витрину и данные мока (детерминированно, `SEED=42`) |
| `make demo-snapshot` | `pg_dump` + выгрузка MinIO → `infra/snapshots/demo.*` |
| `make demo-reset` | Восстановить снапшот, `FLUSHDB` кешей (очереди не трогаем), перезапуск воркеров, `demo-warm` |
| `make demo-warm` | Прогрев кешей героев демо ([messaging.md §7](messaging.md#6-кеши)) |
| `make eval` | Пересчёт метрик → отчёт → страница качества |
| `make api-gen` | OpenAPI → клиент фронта |
| `make test` / `make lint` | Тесты и линтеры всех сервисов |
| `make backup` | `pg_dump` с ротацией 7 дней |

## 6. Демо-надёжность

| Риск | Подстраховка |
|---|---|
| Пропал домашний интернет или электричество | Записанное видео демо. Заранее проверить, можно ли поднять облегчённую копию на VPS: core + CPU-модель + предпрогретые кеши (`LLM_PROFILE=cpu`) |
| GPU зависла | `restart: unless-stopped`, healthcheck llm-chat. При провале — `LLM_PROFILE=cpu` |
| LLM медленно отвечает в моменте | `demo-warm`: разбор резюме героев и запросы работодателя уже в кеше |
| Telegram недоступен | Офферы видны на сайте + SSE. В демо показываем оба канала |
| Сломали данные на репетиции | `make demo-reset` (≤ 1 мин) |
| GitHub rate limit | Токен + ETag-кеш, анализ репозитория героя прогрет |

## 7. CI/CD

- **GitHub Actions на PR:** ruff, mypy (мягко), pytest (testcontainers), фронт: tsc, eslint, vitest, проверка сгенерированного клиента, diff OpenAPI (комментарий в PR).
- **main:** сборка образов → GHCR.
- **Деплой:** `make deploy` на домашнем сервере (`git pull && docker compose pull && up -d && make migrate`). 🚀 self-hosted runner на сервере для автодеплоя main.
