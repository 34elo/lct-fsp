# AGENTS.md — core

Назначение: основной бэкенд — домен, граф доказательств, подбор, офферы (api, worker, scheduler).

## Команды
- `uv run --package fsp-core uvicorn app.main:app --reload` — запуск api
- `cd services/core && uv run python -m app.worker` — core-worker (очереди core.* + relay outbox)
- `cd services/core && uv run python -m app.scheduler` — core-scheduler (cron-команды)
- `make test-integration` — outbox → RabbitMQ → inbox на временных контейнерах
- `uv run pytest services/core -q` — тесты
- `uv run ruff check services/core` — линтер
- `cd services/core && uv run alembic upgrade head` — миграции (`-x url=...` или `DATABASE_URL`)
- `cd services/core && uv run alembic revision --autogenerate -m "..."` — новая миграция

## Ключевые файлы
- `app/main.py` — фабрика приложения, `/healthz`, `/readyz`, lifespan
- `app/deps.py` — зависимости: сессия (транзакция на запрос), Redis, лимитер, S3
- `app/models.py` — реестр моделей для Alembic
- `app/events_stream.py` — SSE `/events/stream`, `UiHub` (очередь `ui.<instance>`, `ui.user.*`); публикация — `fsp_platform.messaging.publish_ui`
- `app/identity/` — users, refresh-семьи, `/auth/*`, `/me`; зависимости `get_current_user`, `require_roles`
- `app/consents/` — согласия, `/me/consents`; зависимость `require_consent(type)` → 403 `consent_required`
- `app/candidates/` — анкета: `/candidates/me/{profile,preferences,visibility,stoplist}`, `pseudo_id`, псевдоним
- `app/taxonomy/` — граф навыков: `loader.py` (YAML → проверка), `service.py` (sync в БД, версия, снимок, `taxonomy.updated`), `router.py` (`GET /taxonomy`, `/internal/taxonomy/snapshot`); `make taxonomy-load`
- `app/graph/` — `embedding.py` (`profile_text` из графа, `MlEmbedder` → ml-api `/v1/embeddings`, вектор только при смене sha; `ML_API_URL` пусто — не считаем); evidence: `models.py`, `service.py` (`upsert_evidence` идемпотентно, `deactivate`, `list_active`, `candidates_by_skills`; изменение → `evidence.changed` + команда `core.recompute` в outbox), `trust.py` (формулы доверия по scoring.yaml), `category.py` (роли, мульти-метки, `primary_stack`, объяснение; ml.md §4), `grade.py` (сигналы, пороги, ограничения, уверенность, `next_grade`; ml.md §5), `team_signals.py` (L/T/R/G из фактов, `k_soft`; skills.md §8), `recompute.py` (`recompute_profile` → `candidate_skills`, категория, грейд, `profile_version`, `skills.profile.updated`), `handlers.py` (`core.recompute`, `taxonomy.updated`, `fsp.*`), `fsp_ingest.py` (события ФСП → `fsp_*` → evidence; ml.md §3.2, fsp.md §6), `fsp_strength.py` (сила доказательства ФСП), `fsp_models.py`
- `app/resumes/` — резюме: `router.py` (`/candidates/me/resumes[/{id}[/confirm]]`), `service.py` (сигнатура файла, MinIO, команда `ml.resume.parse`, confirm → evidence `resume`/`self` по ml.md §2.7, опыт, образование, стаж, `claimed_soft`), `handlers.py` (`ml.resume.completed|failed` → статус, `resume.parsed`, SSE)
- `app/telegram/` — Telegram: `telegram_accounts`, `service.py` (проверка Login Widget, magic-ссылки и deep link через Redis `GETDEL`, привязка с вливанием заготовки бота), `router.py` (`/me/telegram/link`, `/internal/tg/{start,consents,link}`, `/internal/auth/magic-link`; `Service`-токен бота); `/auth/telegram` и `/auth/magic` — в `identity/router.py`
- `app/companies/` — компании: `/companies`, `/companies/me[/members]`, модерация `/admin/companies/*` (pending → verified|rejected)
- `app/vacancies/` — вакансии: `/vacancies[/{id}]`, `publish`, `close`; публиковать может только `verified` компания; события `vacancy.published|updated|closed`
- `app/matching/` — подбор (ml.md §6, matching.md §3–4): `scoring.py` (жёсткие фильтры, скоринг, `K_soft`, объяснения шаблонами со ссылками на доказательства), `service.py` (`match_vacancy_candidates`: отбор SQL → скоринг; `match_vacancy` / `match_candidate` пишут `matches` и `matches.ready`), `models.py` (`matches`), `handlers.py` (`vacancy.*`, `skills.profile.updated` → `core.match.*`), `search.py` + `router.py` (`POST /search/candidates`: анонимные `CandidateCard`, курсор, кеш `c:search:*`)
- `app/worker.py` — `Worker.consumers[<очередь>].on(type)` + `idempotent()` для обработчиков
- `app/scheduler.py` — `SCHEDULE` (messaging.md §4)
- `migrations/` — Alembic (async), `versions/`
- `app/config.py` — настройки (из env)
- `tests/` — тесты

## Правила
- Общий код только из `packages/platform` и `packages/contracts`.
- В чужую БД не ходим: события, команды, internal API.
- Документы: docs/architecture/services.md, messaging.md.
