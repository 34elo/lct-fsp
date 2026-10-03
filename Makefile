.PHONY: synth taxonomy-load up down dev-core compose-config sync lint fmt test test-py test-web test-integration new-service web-install asyncapi api-gen

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
COMPOSE = docker compose --profile core --profile ml --profile llm

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

# Только core-профиль, ML заглушкой
dev-core:
	ML_FAKE=true docker compose --profile core up -d

compose-config:
	docker compose --profile core --profile ml --profile llm --profile dev --profile obs config -q

api-gen:
	cd apps/web && pnpm api:gen

# Загрузить data/taxonomy/*.yaml и data/fsp/discipline_rules.yaml в БД core (идемпотентно, версия растёт при изменениях)
taxonomy-load:
	cd services/core && uv run python -m app.taxonomy

# Синтетический рынок (evaluation.md §3): make synth SPLIT=test → reports/synth/test
SPLIT ?= dev
synth:
	uv run python tools/synth/synth.py --split $(SPLIT) --out reports/synth/$(SPLIT)
