.PHONY: demo-env logs ps synth taxonomy-load up down dev-core compose-config sync lint fmt test test-py test-web test-integration new-service web-install asyncapi api-gen

sync:
	uv sync --all-packages

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run lint-imports
	cd apps/web && pnpm lint && pnpm typecheck

fmt:
	uv run ruff check --fix .
	uv run ruff format .

test: test-py test-web

test-py:
	uv run pytest -q

# Интеграция outbox → RabbitMQ → inbox на временных контейнерах (project fsp-test, порты 285xx)
TEST_COMPOSE = docker compose -f infra/test/docker-compose.yml
test-integration:
	$(TEST_COMPOSE) up -d --wait
	FSP_TEST_PG_URL=postgresql+asyncpg://test:test@127.0.0.1:28532/test \
	FSP_TEST_AMQP_URL=amqp://guest:guest@127.0.0.1:28572/ \
	uv run pytest -q packages/platform/tests/test_messaging_integration.py services/core/tests/test_events_stream_integration.py; \
	rc=$$?; $(TEST_COMPOSE) down -v; exit $$rc

test-web:
	cd apps/web && pnpm test

web-install:
	cd apps/web && pnpm install

# make new-service NAME=core
new-service:
	uv run python tools/new_service.py $(NAME)

# Каталог AsyncAPI всех событий и команд из packages/contracts
asyncapi:
	uv run python -m fsp_contracts.asyncapi > asyncapi.json

# --- compose ---
# Окружение: .env, если в нём задан JWT_SECRET (то есть он полный); иначе .env.demo (создаётся infra/scripts/gen-demo-env.sh со случайными секретами)
ENV_FILE := $(if $(shell grep -s -E '^JWT_SECRET=.+' .env),.env,.env.demo)
# Профиль bot включается только если в env-файле задан TG_BOT_TOKEN
BOT_PROFILE = $(if $(shell grep -s -E '^TG_BOT_TOKEN=.+' $(ENV_FILE)),--profile bot)
COMPOSE = docker compose --env-file $(ENV_FILE) --profile core --profile ml --profile llm $(BOT_PROFILE)

demo-env:
	sh infra/scripts/gen-demo-env.sh

# Весь стек одной командой: сборка образов, миграции, запуск; gateway на :28080
up: demo-env
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail 50

ps:
	$(COMPOSE) ps

# Только core-профиль, ML заглушкой
dev-core:
	ML_FAKE=true docker compose --env-file $(ENV_FILE) --profile core up -d --build

compose-config:
	docker compose --env-file $(ENV_FILE) --profile core --profile ml --profile bot --profile llm --profile dev --profile obs config -q

api-gen:
	cd apps/web && pnpm api:gen

# Загрузить data/taxonomy/*.yaml и data/fsp/discipline_rules.yaml в БД core (идемпотентно, версия растёт при изменениях)
taxonomy-load:
	cd services/core && uv run python -m app.taxonomy

# Синтетический рынок (evaluation.md §3): make synth SPLIT=test → reports/synth/test
SPLIT ?= dev
synth:
	uv run python tools/synth/synth.py --split $(SPLIT) --out reports/synth/$(SPLIT)
