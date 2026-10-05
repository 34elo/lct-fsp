.PHONY: demo-snapshot demo-reset demo-warm demo-env logs ps seed seed-plan seed-fsp-mock synth taxonomy-load up down dev-core compose-config sync lint fmt test test-py test-web test-integration new-service web-install asyncapi api-gen

sync:
	uv sync --all-packages

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run lint-imports
	pnpm -r lint && pnpm -r typecheck

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
	pnpm -r test

# e2e Playwright на стенде с сидом (make up && make seed); нужен Node >= 20
e2e:
	cd apps/web && pnpm e2e

web-install:
	pnpm install

# make new-service NAME=core
new-service:
	uv run python tools/new_service.py $(NAME)

# Каталог AsyncAPI всех событий и команд из packages/contracts
asyncapi:
	uv run python -m fsp_contracts.asyncapi > asyncapi.json

# OpenAPI схема REST API
openapi:
	mkdir -p docs
	cd services/core && PYTHONUTF8=1 uv run python export_openapi.py > ../../docs/openapi.json

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
	pnpm --filter fsp-web api:gen

# Загрузить data/taxonomy/*.yaml и data/fsp/discipline_rules.yaml в БД core (идемпотентно, версия растёт при изменениях)
taxonomy-load:
	cd services/core && uv run python -m app.taxonomy

# Синтетический рынок (evaluation.md §3): make synth SPLIT=test → reports/synth/test
SPLIT ?= dev
synth:
	uv run python tools/synth/synth.py --split $(SPLIT) --out reports/synth/$(SPLIT)

# Демо-витрина (evaluation.md §4): make seed [SEED=42]. Пишет данные fsp-mock в reports/seed/fsp-mock.json
# (compose монтирует каталог в fsp-mock, сервис пересоздаётся), наполняет БД core сервисными слоями
# (секреты и порт Postgres берёт из $(ENV_FILE)), печатает демо-аккаунты. Повторный запуск безопасен.
# Нужны поднятый стек (make up) и справочник навыков (его грузит core-migrate).
seed:
	mkdir -p reports/seed
	SEED=$(SEED) uv run python -m tools.seed all --env-file $(ENV_FILE)
# >>> block1 (assessment, taxonomy, identity, candidates, graph, resumes)
	SEED=$(SEED) uv run python -m tools.seed grades --env-file $(ENV_FILE)
# <<< block1
# >>> block2 (matching, offers, vacancies, companies, consents, fsp, telegram, analytics)
# <<< block2
	$(COMPOSE) up -d --build --no-deps --force-recreate fsp-mock
seed-fsp-mock:
	mkdir -p reports/seed
	SEED=$(SEED) uv run python -m tools.seed fsp-mock
seed-plan:
	SEED=$(SEED) uv run python -m tools.seed plan

# Снапшот витрины (evaluation.md §4): make demo-snapshot (после make seed) -> make demo-reset (≤ 1 мин) -> make demo-warm
# Файлы в infra/snapshots/ (в git не идут): core.dump, fsp_connector.dump, fsp-mock.json
demo-snapshot:
	COMPOSE="$(COMPOSE)" sh infra/scripts/demo.sh snapshot
demo-reset:
	COMPOSE="$(COMPOSE)" sh infra/scripts/demo.sh reset
demo-warm:
	GATEWAY_PORT=$$(sed -n 's/^GATEWAY_PORT=//p' $(ENV_FILE)) COMPOSE="$(COMPOSE)" sh infra/scripts/demo.sh warm
