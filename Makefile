.PHONY: sync lint docs-links deadcode fmt test test-py test-web test-integration e2e web-install \
	asyncapi openapi api-gen libraries demo-env up up-lite down logs ps dev-core compose-config \
	taxonomy-load seed seed-fsp-mock seed-plan demo-snapshot demo-reset demo-warm \
	synth eval eval-quick eval-assessment metrics load families-check cards-check \
	assessment-mutations-mine assessment-mutations-check assessment-mutations-import \
	assessment-fsp-check assessment-fsp-import assessment-llm-bank

# --- разработка ---------------------------------------------------------------------------------

sync:
	uv sync --all-packages

web-install:
	pnpm install

lint: docs-links
	uv run ruff check .
	uv run ruff format --check .
	uv run lint-imports
	pnpm -r lint && pnpm -r typecheck

# Относительные ссылки и якоря в Markdown, без сети
docs-links:
	PYTHONUTF8=1 uv run python tools/check_links.py

# Мёртвый код: knip по фронту (белый список — knip.json), vulture по Python
deadcode:
	npx -y knip@5
	uvx vulture services packages/platform packages/contracts tools --min-confidence 80 --exclude "*/tests/*,*/test_*,*/.venv/*,*/node_modules/*"

fmt:
	uv run ruff check --fix .
	uv run ruff format .

test: test-py test-web

test-py:
	uv run pytest -q -n auto

test-web:
	pnpm -r test

# Интеграция outbox → RabbitMQ → inbox на временных контейнерах (project fsp-test, порты 285xx)
TEST_COMPOSE = docker compose -f infra/test/docker-compose.yml
test-integration:
	$(TEST_COMPOSE) up -d --wait
	FSP_TEST_PG_URL=postgresql+asyncpg://test:test@127.0.0.1:28532/test \
	FSP_TEST_AMQP_URL=amqp://guest:guest@127.0.0.1:28572/ \
	uv run pytest -q packages/platform/tests/test_messaging_integration.py services/core/tests/test_events_stream_integration.py; \
	rc=$$?; $(TEST_COMPOSE) down -v; exit $$rc

# e2e Playwright на стенде с демо-данными (make up && make seed); нужен Node >= 20
e2e:
	cd apps/web && pnpm e2e

# --- контракты и документация ---------------------------------------------------------------------

# AsyncAPI всех событий и команд из packages/contracts
asyncapi:
	mkdir -p docs
	PYTHONUTF8=1 uv run python -m fsp_contracts.asyncapi > docs/asyncapi.json

# OpenAPI REST API core (CI сверяет файл с кодом)
openapi:
	mkdir -p docs
	cd services/core && PYTHONUTF8=1 uv run python export_openapi.py > ../../docs/openapi.json

# Клиент фронта (orval) из apps/web/openapi.json
api-gen:
	pnpm --filter fsp-web api:gen

# Список библиотек с версиями и лицензиями из lock-файлов
libraries:
	PYTHONUTF8=1 uv run python tools/libraries.py --out docs/libraries.md

# --- стек в Docker -------------------------------------------------------------------------------

# Окружение: .env, если в нём задан JWT_SECRET; иначе .env.demo со случайными секретами
ENV_FILE := $(if $(shell grep -s -E '^JWT_SECRET=.+' .env),.env,.env.demo)
# Профиль bot включается только при заданном TG_BOT_TOKEN
BOT_PROFILE = $(if $(shell grep -s -E '^TG_BOT_TOKEN=.+' $(ENV_FILE)),--profile bot)
COMPOSE = docker compose --env-file $(ENV_FILE) --profile core --profile ml --profile llm $(BOT_PROFILE)
# Профиль lite: ядро и ML без LLM, малая модель эмбеддингов на CPU
LITE_ENV = LLM_ENABLED=false ML_FAKE=false EMBEDDING_MODEL=$${EMBEDDING_MODEL:-multilingual-e5-small}

demo-env:
	sh infra/scripts/gen-demo-env.sh

# Весь стек: сборка образов, миграции, запуск; gateway на :28080
up: demo-env
	$(COMPOSE) up -d --build --wait

up-lite: demo-env
	$(LITE_ENV) docker compose --env-file $(ENV_FILE) --profile core --profile ml $(BOT_PROFILE) up -d --build --wait

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail 50

ps:
	$(COMPOSE) ps

# Только профиль core, ML на заглушках
dev-core:
	ML_FAKE=true docker compose --env-file $(ENV_FILE) --profile core up -d --build

compose-config:
	docker compose --env-file $(ENV_FILE) --profile core --profile ml --profile bot --profile llm --profile dev --profile obs config -q

# --- данные --------------------------------------------------------------------------------------

# Справочник навыков и правила дисциплин ФСП в БД core (идемпотентно)
taxonomy-load:
	cd services/core && uv run python -m app.taxonomy

# Демо-данные: make seed [SEED=42]. Нужен поднятый стек. Повторный запуск безопасен.
# Данные мока ФСП пишутся в reports/seed/fsp-mock.json (каталог смонтирован в fsp-mock).
seed:
	mkdir -p reports/seed
	SEED=$(SEED) uv run python -m tools.seed all --env-file $(ENV_FILE)
	SEED=$(SEED) uv run python -m tools.seed grades --env-file $(ENV_FILE)
	SEED=$(SEED) uv run python -m tools.seed families --env-file $(ENV_FILE)
	SEED=$(SEED) uv run python -m tools.seed demo2 --env-file $(ENV_FILE)
	SEED=$(SEED) uv run python -m tools.seed fsp-registry --env-file $(ENV_FILE)
	$(COMPOSE) up -d --build --no-deps --force-recreate fsp-mock

seed-fsp-mock:
	mkdir -p reports/seed
	SEED=$(SEED) uv run python -m tools.seed fsp-mock

seed-plan:
	SEED=$(SEED) uv run python -m tools.seed plan

# Снапшот демо после make seed → сброс демо-данных к снапшоту (≤ 1 мин) → прогрев кешей
demo-snapshot:
	COMPOSE="$(COMPOSE)" sh infra/scripts/demo.sh snapshot
demo-reset:
	COMPOSE="$(COMPOSE)" sh infra/scripts/demo.sh reset
demo-warm:
	GATEWAY_PORT=$$(sed -n 's/^GATEWAY_PORT=//p' $(ENV_FILE)) COMPOSE="$(COMPOSE)" sh infra/scripts/demo.sh warm

# --- оценка качества -----------------------------------------------------------------------------

# Синтетический рынок: make synth SPLIT=test → reports/synth/test
SPLIT ?= dev
synth:
	uv run python tools/synth/synth.py --split $(SPLIT) --out reports/synth/$(SPLIT)

# Подбор против BM25 на синтетическом рынке и полнота разбора резюме → reports/eval
eval:
	uv run python tools/eval/run.py --split $(SPLIT) --out reports/eval

eval-quick:
	uv run python tools/eval/run.py --quick --out reports/eval-quick

# Валидация теста на синтетических кандидатах с известным θ → reports/eval-assessment
eval-assessment:
	uv run python -m tools.eval_assessment --seed $(or $(SEED),42) --out reports/eval-assessment

# Все офлайн-метрики одним отчётом со светофором → reports/metrics. make metrics [SEED=42] [ARGS="--skip load"]
metrics:
	uv run python -m tools.metrics --seed $(or $(SEED),42) --out reports/metrics $(ARGS)

# Нагрузка против живого стека после make seed. Код выхода 1, если p95 поиска > 1 с.
LOAD_USERS ?= 50
LOAD_TIME ?= 9m
LOAD_HOST ?= http://127.0.0.1:$(or $(GATEWAY_PORT),28080)
load:
	uv run --group load locust -f tools/load/locustfile.py --headless -u $(LOAD_USERS) -r 0.15 -t $(LOAD_TIME) --host $(LOAD_HOST) --csv reports/load/load --only-summary
	uv run python tools/load/report.py reports/load/load_stats.csv --out reports/load/load.md

# --- банк заданий --------------------------------------------------------------------------------

# Автопроверка кодовых семейств: ключи, исполнение, ручки сложности, детерминизм, покрытие профессий
families-check:
	uv run python -m app.assessment.families.check --seeds 1000

# Схема карточек навыков data/skills/cards
cards-check:
	cd services/core && uv run python -m app.taxonomy.cards

# Мутации открытого кода → семейства find_bug. Код проектов только читается (AST + песочница).
# SRC — имя из data/questions/mutations/sources.yaml; DIR — локальная копия (без неё нужен MUTMINE_GITHUB=1)
assessment-mutations-mine:
	cd services/core && uv run python -m app.assessment.mining mine --source $(SRC) $(if $(DIR),--dir $(abspath $(DIR)))
assessment-mutations-check:
	cd services/core && uv run python -m app.assessment.mining check ../../data/questions/mutations/*.json
# PILOT=1 — сразу в pilot (в active переводит только админ по статистике пилота)
assessment-mutations-import:
	cd services/core && uv run python -m app.assessment.mining import ../../data/questions/mutations/*.json $(if $(PILOT),--pilot)

# Задачи соревнований ФСП: проверка и импорт data/questions/fsp/*.yaml
assessment-fsp-check:
	cd services/core && uv run python -m app.assessment.fsp_bank check
assessment-fsp-import:
	cd services/core && uv run python -m app.assessment.fsp_bank import $(if $(PILOT),--pilot)

# Офлайн-генерация заданий LLM → черновики в очереди допуска. Нужен ml-api (ML_API_URL) и LLM_ENABLED=true.
assessment-llm-bank:
	cd services/core && uv run python -m app.assessment.llm_bank --out ../../reports/llm-bank $(ARGS)
