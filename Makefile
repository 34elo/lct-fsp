.PHONY: up-lite demo-snapshot demo-reset demo-warm demo-env logs ps seed seed-plan seed-fsp-mock synth eval eval-quick load taxonomy-load up down dev-core compose-config sync lint fmt test test-py test-web test-integration new-service web-install asyncapi api-gen

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

# Стенд оценки (evaluation.md §5): подбор против BM25 на синтетическом рынке → reports/eval/eval.{md,json}
eval:
	uv run python tools/eval/run.py --split $(SPLIT) --out reports/eval

eval-quick:
	uv run python tools/eval/run.py --quick --out reports/eval-quick

# Все офлайн-метрики одним отчётом (E31-3, metrics.md §9.1): eval-assessment, eval, families-check, load (если был
# прогон) → reports/metrics/report.{md,json} со светофором. make metrics [SEED=42] [ARGS="--skip load"].
# Недоступное без стенда помечается «не измерено». Занимает около двух минут.
.PHONY: metrics
metrics:
	uv run python -m tools.metrics --seed $(or $(SEED),42) --out reports/metrics $(ARGS)

# Нагрузка (E29-2, metrics.md): 50 пользователей против живого стека после make seed.
# make load [LOAD_USERS=50 LOAD_TIME=3m LOAD_HOST=http://127.0.0.1:28080]. Код выхода 1, если p95 search/matches > 1 с.
LOAD_USERS ?= 50
LOAD_TIME ?= 3m
LOAD_HOST ?= http://127.0.0.1:$(or $(GATEWAY_PORT),28080)
load:
	uv run --group load locust -f tools/load/locustfile.py --headless -u $(LOAD_USERS) -r 5 -t $(LOAD_TIME) 		--host $(LOAD_HOST) --csv reports/load/load --only-summary
	uv run python tools/load/report.py reports/load/load_stats.csv --out reports/load/load.md

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
	SEED=$(SEED) uv run python -m tools.seed demo2 --env-file $(ENV_FILE)
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

# >>> block1 (lite)
# Профиль lite (ADR-023): ядро и ML без LLM (LLM_ENABLED=false, ML_FAKE=false), малая модель эмбеддингов, ≤ 1.5 ГБ на сервисы приложения
LITE_ENV = LLM_ENABLED=false ML_FAKE=false EMBEDDING_MODEL=$${EMBEDDING_MODEL:-multilingual-e5-small}
up-lite: demo-env
	$(LITE_ENV) docker compose --env-file $(ENV_FILE) --profile core --profile ml $(BOT_PROFILE) up -d --build --wait
# Автопроверка кодовых семейств заданий (assessment.md §4): ключи, исполнение, ручки, детерминизм
.PHONY: families-check
families-check:
	uv run python -m app.assessment.families.check --seeds 1000
# Майнинг мутаций открытого кода → семейства find_bug (E30-3, assessment.md §4). Код проектов только
# читается (AST + песочница), не импортируется и не запускается. SRC — имя из
# data/questions/mutations/sources.yaml; DIR — локальная копия (без неё нужен MUTMINE_GITHUB=1)
.PHONY: assessment-mutations-mine assessment-mutations-check assessment-mutations-import
assessment-mutations-mine:
	cd services/core && uv run python -m app.assessment.mining mine --source $(SRC) $(if $(DIR),--dir $(abspath $(DIR)))
assessment-mutations-check:
	cd services/core && uv run python -m app.assessment.mining check ../../data/questions/mutations/*.json
# Банк → families (draft); PILOT=1 — сразу в pilot (в active — только админ по статистике пилота)
assessment-mutations-import:
	cd services/core && uv run python -m app.assessment.mining import ../../data/questions/mutations/*.json $(if $(PILOT),--pilot)
# Задачи соревнований ФСП в банке (E32-6, assessment.md §4): проверка и импорт data/questions/fsp/*.yaml
.PHONY: assessment-fsp-check assessment-fsp-import
assessment-fsp-check:
	cd services/core && uv run python -m app.assessment.fsp_bank check
assessment-fsp-import:
	cd services/core && uv run python -m app.assessment.fsp_bank import $(if $(PILOT),--pilot)
# Схема карточек навыков data/skills/cards (assessment.md §2)
.PHONY: cards-check
cards-check:
	cd services/core && uv run python -m app.taxonomy.cards
# Валидация теста на синтетике (E27-1, metrics.md §9.1): make eval-assessment [SEED=42] → reports/eval-assessment/report.{md,json}
.PHONY: eval-assessment
eval-assessment:
	uv run python -m tools.eval_assessment --seed $(or $(SEED),42) --out reports/eval-assessment
# Офлайн-конвейер LLM-заданий (E26-4): генератор → автопроверки → draft в очереди допуска; LLM как
# кандидат → families.ai_solvable. Только через ml-api (ML_API_URL), LLM_ENABLED=false — ничего не делает.
# ARGS — флаги CLI (--skills, --kinds, --levels, --n, --k, --skip-propose, --skip-solve)
.PHONY: assessment-llm-bank
assessment-llm-bank:
	cd services/core && uv run python -m app.assessment.llm_bank --out ../../reports/llm-bank $(ARGS)
# Замер LLM-кандидатов (E32-3, ml.md «Выбор LLM»): сервер поднимает человек, модели не качаются.
# make eval-llm [LLM_MODEL=…] [ARGS="--repeats 5 --server-pid <pid> --vram-file …"] → reports/llm/<модель>.{md,json}
.PHONY: eval-llm
eval-llm:
	uv run python -m tools.eval_llm --env-file $(ENV_FILE) $(ARGS)
# Документ сдачи (E27-4): список библиотек из lock-файлов → docs/libraries.md; PDF из docs/submission.md
# (WeasyPrint из зависимостей core) → reports/submission/submission.pdf (reports/ не коммитим)
.PHONY: submission-libs submission-pdf
submission-libs:
	python3 tools/submission/libs.py --out docs/libraries.md
submission-pdf:
	uv run python tools/submission/build_pdf.py --src docs/submission.md --out reports/submission/submission.pdf
# <<< block1
