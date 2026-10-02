.PHONY: up down dev-core compose-config sync lint fmt test test-py test-web new-service web-install asyncapi

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
