# RabbitMQ, события и кеш

> Межсервисное взаимодействие идёт через **RabbitMQ**: доменные события, команды сервисам, задачи для ML и уведомления. **Redis** остаётся только для короткоживущего состояния: кеш, лимиты, состояния бота, одноразовые токены, сессии тестов и рекомендаций (ADR-012).
> Библиотека — **FastStream** (поверх aio-pika). Схемы сообщений — pydantic-модели из `packages/contracts`. FastStream генерирует **AsyncAPI**-документацию событий (`/asyncapi` у каждого сервиса), это часть «документированного API».

## 1. Кто с кем говорит

```
                 ┌──────────── exchange events (topic) ────────────┐
core ──publish──►│ offer.* · vacancy.* · skills.* · candidate.*    │──► core.handlers (реакции core на свои события)
fsp-connector ──►│ fsp.results.imported · fsp.competitions.updated │──► core.ingest
ml ──publish────►│ ml.*.completed · ml.*.failed                    │──► core.ingest
                 └──────────────────────────────────────────────────┘
                 ┌──────────── exchange commands (direct) ──────────┐
core ──────────► │ ml.llm (приоритеты) · ml.code                    │──► ml-worker
core ──────────► │ fsp.sync                                         │──► fsp-connector
core ──────────► │ notify.telegram                                  │──► bot
core ──────────► │ core.recompute · core.match · core.jobs          │──► core-worker
scheduler ─────► │ core.jobs (cron)                                 │──► core-worker
                 └──────────────────────────────────────────────────┘
                 ┌──────────── exchange ui (topic) ──────────────────┐
core-worker ───► │ ui.user.<user_id>                                 │──► core-api (SSE-соединения)
ml-worker ─────► │ ui.user.<user_id> (прогресс задач)                │
                 └──────────────────────────────────────────────────┘
```

Правило: **событие** («что-то случилось») публикуется в `events`, и подписаться может кто угодно. **Команда** («сделай это») идёт в `commands` конкретному исполнителю.

Синхронный HTTP остаётся только там, где нужен ответ сразу: web/бот → core; core → ml-api (разбор текстового запроса, эмбеддинг); core → fsp-connector (URL авторизации ФСП, обмен кода); ml → core (снимок справочника, с кешем).

## 2. Обменники и очереди

### 2.1. `events` (topic, durable)

| Ключ маршрутизации | Публикует | Payload (`contracts/events.py`) |
|---|---|---|
| `candidate.registered` | core | `{candidate_id, channel}` |
| `candidate.preferences.updated` | core | `{candidate_id, fields[]}` |
| `candidate.deleted` | core | `{candidate_id}` |
| `resume.parsed` / `resume.confirmed` | core | `{resume_id, candidate_id}` |
| `evidence.changed` | core | `{candidate_id, sources[]}` |
| `skills.profile.updated` | core | `{candidate_id, profile_version, diff: {skills_up, skills_new, grade, category}}` |
| `taxonomy.updated` | core | `{version, changed_skill_ids[]}` |
| `vacancy.published` / `vacancy.updated` / `vacancy.closed` | core | `{vacancy_id, version}` |
| `offer.sent` / `offer.viewed` / `offer.accepted` / `offer.declined` / `offer.expired` / `offer.withdrawn` / `offer.message` / `offer.status_changed` | core | `{offer_id, candidate_id, company_id, …}` |
| `matches.ready` | core | `{vacancy_id, count}` |
| `fsp.linked` | fsp-connector | `{candidate_id, participant_id, verified, method}` |
| `fsp.results.imported` | fsp-connector | `{candidate_id, participant_id, results: FspResult[], ranks: FspRank[], teams: FspTeam[], new: bool}`. `new=true` — полная выгрузка: результаты, которых в ней нет, core деактивирует; иначе инкремент (`since`), ничего не гасим |
| `fsp.competitions.updated` | fsp-connector | `{competitions: FspCompetition[]}` |
| `ml.resume.completed` / `ml.resume.failed` | ml | `{resume_id, candidate_id, parsed?, error?}` |
| `ml.code.completed` / `ml.code.failed` | ml | `{analysis_id, candidate_id, result?, error?}` |
| `ml.interview.generated` / `ml.interview.graded` | ml | `{interview_id, candidate_id, questions[] | grades[] + total, error?}` |
| `ml.matches.explained` | ml | `{vacancy_id, vacancy_version, items[]}` |
| `ml.interview_kit.generated` | ml | `{kit_id, vacancy_id, vacancy_version, candidate_id, profile_version, questions[], error?}` |
| `ml.skills.resolved` | ml | `{request_id, taxonomy_version, items[]}` (ответ на `ml.skills.resolve`) |
| `ml.questions.generated` | ml | `{skill_slug, questions[]}` — черновики, `status=draft` |

### 2.2. Очереди

| Очередь | Потребитель | Привязки / команды | prefetch | Особенности |
|---|---|---|---|---|
| `core.ingest` | core-worker | `fsp.results.imported`, `fsp.competitions.updated`, `fsp.linked`, `ml.#` | 8 | Внешние факты → узлы и рёбра графа |
| `core.handlers` | core-worker | `evidence.changed`, `skills.profile.updated`, `vacancy.#`, `offer.#`, `candidate.#`, `taxonomy.updated`, `matches.ready` | 8 | Реакции на свои события: пересчёт, матчинг, уведомления |
| `core.recompute` | core-worker | команда `core.recompute {candidate_id, requested_at}` | 4 | Слияние пересчётов по `recomputed_at ≥ requested_at` ([graph.md §4.4](graph.md#44-целостность-и-версии)) |
| `core.match` | core-worker | команды `core.match.vacancy`, `core.match.candidate` | 4 | Пропуск устаревших версий |
| `core.jobs` | core-worker | cron-команды и фоновые задачи (удаление, `recompute_all`) | 2 | — |
| `core.analytics` | core-worker | все `events.#` | 20 | Доменные события → `analytics_events` ([metrics.md](metrics.md)) |
| **`ml.llm`** | ml-worker-llm | `ml.resume.parse` (приоритет 9), `ml.interview.grade` (8), `ml.interview.generate` (7), `ml.interview_kit.generate` (5), `ml.skills.resolve` (3), `ml.matches.explain` (2), `ml.questions.generate` (1) | **1** | `x-max-priority: 10`. Одна GPU: строго одна задача за раз, срочное первым |
| `ml.code` | ml-worker-code | `ml.code.analyze` | 2 | CPU и сеть, GPU не нужен |
| `fsp.sync` | fsp-connector | `fsp.sync {candidate_id, reason, since?}`, `fsp.sync_all` | 4 | Ретраи с паузой (внешний API) |
| `bot.telegram` | bot | `notify.telegram {chat_id, template, data, buttons, edit_of?}` | 10 | Отправка с учётом лимитов Telegram |
| `ui.<instance>` | core-api | `ui.user.*` | 50 | Эксклюзивная, удаляется при отключении. core-api раздаёт сообщения своим SSE-соединениям |

> **GPU-дисциплина.** У `llama-server` два слота. Слот 1 — синхронные вызовы ml-api (разбор запроса работодателя). Слот 2 — очередь `ml.llm` с `prefetch=1` и приоритетами: разбор резюме, которого человек ждёт, обгоняет фоновые обоснования. Решение встроено в брокер, костылей не нужно.

### 2.3. Надёжность

| Механизм | Как |
|---|---|
| **Outbox** (у сервисов с БД: core, fsp-connector) | Событие или команда пишется в таблицу `outbox` в той же транзакции, что и данные. Relay в core-worker (триггер `outbox_notify` → LISTEN + опрос раз в 500 мс, `FOR UPDATE SKIP LOCKED`) публикует его с **publisher confirms** и только после подтверждения ставит `published_at`. Маршрут по реестру: команда → `commands` (ключ = очередь, приоритет), иначе → `events` (ключ = `type`) |
| **Inbox** (идемпотентность у core) | Перед обработкой `INSERT INTO inbox(event_id, handler) ON CONFLICT DO NOTHING`. Если строка уже была — сообщение пропускается. Повторная доставка не шлёт второй push и не дублирует факты |
| **Ретраи** | При ошибке копия сообщения уходит в очередь задержки `<queue>.retry.<5s|30s|2m>` (TTL + dead-letter обратно в основную), счётчик в заголовке `x-retry`, оригинал подтверждается. Обработчик с эффектом в БД оборачивается в `idempotent()`: эффект и строка inbox в одной транзакции, при ошибке откатываются вместе |
| **DLQ** | После 3 повторов (4-я неудача) или при битом конверте — `nack` → обменник `dlx` → `<queue>.dlq`. Видно в веб-интерфейсе RabbitMQ, можно переотправить руками |
| **Устойчивость** | durable-обменники и очереди, persistent-сообщения, `quorum`-очереди не нужны (один узел) |
| **Порядок** | Гарантии порядка не нужны: обработчики идемпотентны и сверяют версии (`profile_version`, `vacancy.version`) |

### 2.4. Конверт сообщения

```json
{
  "message_id": "0192f0c4-…",
  "type": "offer.sent",
  "schema_version": 1,
  "occurred_at": "2026-10-05T12:00:00Z",
  "correlation_id": "…",
  "producer": "core",
  "payload": { }
}
```
`correlation_id` = `X-Request-ID` исходного HTTP-запроса: по нему цепочка ищется в логах всех сервисов.

Команды идут в обменник `commands` с routing key = имя очереди (`ml.llm`, `fsp.sync`, `bot.telegram`, …), `type` = имя команды, приоритет AMQP — из реестра. Реестры `EVENTS` / `COMMANDS` / `UI_EVENTS` и сборка конвертов (`new_event`, `new_command`, `parse_payload`) — в `packages/contracts`. Топология (`QUEUES`, `declare_topology`), публикация (`publish_envelope`), подписчик с ретраями (`Consumer`) и `idempotent` — в `fsp_platform.messaging`; интеграционный тест — `make test-integration`. Общий каталог AsyncAPI 3.0 всех сообщений: `make asyncapi` → `asyncapi.json`.

## 3. Цепочки (как это работает вместе)

**Привязка ФСП → профиль обновился**
```
core-api ──cmd fsp.sync──► fsp-connector ──(HTTP к API ФСП)──► нормализация
fsp-connector ──evt fsp.results.imported──► core.ingest: узлы-факты + рёбра evidence → cmd core.recompute
core.recompute: пересчёт графа → evt skills.profile.updated
core.handlers: cmd core.match.candidate · ui.user.<id> «точки загорелись» · cmd notify.telegram «🏆 навыки обновлены»
```

**Оффер → Telegram → принятие**
```
core-api: offer + outbox (одна транзакция) → evt offer.sent
core.handlers: notifications + ui.user.<cand> + cmd notify.telegram (кнопки)
bot: отправка → кандидат жмёт «Принять» → HTTP POST core /internal/tg/offers/{id}/accept
core-api: accepted + contact_reveal + outbox → evt offer.accepted → ui.user.<hr> «принято, контакты открыты»
```

**Резюме → разбор**
```
core-api: файл в MinIO → cmd ml.resume.parse (приоритет 9) → 202
ml-worker-llm: прогресс → ui.user.<id> · результат → evt ml.resume.completed
core.ingest: resumes.parsed → ui.user.<id> «вот что я понял»
```

## 4. Расписание

`core-scheduler` (APScheduler в отдельном маленьком процессе) публикует cron-команды в `core.jobs`:

| Команда | Период |
|---|---|
| `offers.expire` | 5 мин |
| `active_status.expire` | 1 ч |
| `market.refresh` | 2 мин, если были изменения |
| `fsp.sync_all` (в `fsp.sync`) | 1 ч, фолбэк для вебхуков + календарь соревнований |
| `company.rating` | 1 ч |
| `candidate_links.refresh` | 10 мин, если были импорты |
| `cleanup` | сутки |

## 5. Redis: что в нём осталось

`maxmemory 1gb`, `allkeys-lru`. Всё в Redis — с TTL и может пропасть без потери данных.

| Префикс | Назначение | TTL |
|---|---|---|
| `c:*` | Кеши (§6) | по таблице |
| `rl:*` | Лимиты (§7) | окно лимита |
| `s:magic:*`, `s:tglink:*`, `s:oauth:*`, `s:fspcode:*` | Одноразовые токены, OAuth state, коды ФСП | 5–10 мин |
| `s:test:*` | Сессии адаптивных тестов | 30 мин |
| `s:rec:*` | Подстройка рекомендаций в сессии работодателя | 24 ч |
| `fsm:*` | Состояния aiogram | 24 ч |
| `lock:*` | Блокировки: `lock:fsp_sync:{cid}`, `lock:code:{cid}`, `lock:market_refresh`, `lock:outbox_relay` | 10 с – 5 мин |
| `idem:*` | Не используется: ключ `POST /offers` хранится в `offers.idempotency_key` (UNIQUE с компанией) — переживает рестарт Redis | — |

## 6. Кеши

| Что | Ключ | TTL | Инвалидация |
|---|---|---|---|
| Граф навыков в памяти core | версия `taxonomy_version` | — | событие `taxonomy.updated` |
| Снимок справочника для ml | `c:tax:{version}` | 24 ч | версия в ключе |
| Разбор текстового запроса | `c:qparse:{tax_v}:{sha}` | 24 ч | версия справочника |
| Эмбеддинг запроса | `c:emb:q:{model}:{sha}` | 7 д | модель в ключе |
| Эмбеддинг профиля | `c:emb:p:{model}:{sha}` | 7 д | модель в ключе (E4-5; основной «кеш» — `candidates.profile_text_sha`) |
| Страница выдачи | `c:search:{catalog_v}:{sha(filters)}:{cursor}` | 60 с | `catalog_version` растёт при пересчёте профилей |
| Карточка / подграф кандидата | `c:card:{cid}:{profile_v}`, `c:graph:{cid}:{profile_v}:{view}` | 10 мин | версия в ключе |
| Uplift и навигатор | `c:uplift:{cid}:{profile_v}:{vac_v}` | 10 мин | версии в ключе |
| Карта рынка | `c:market:{metric}:{sha}` | 2 мин | `market.refresh` |
| Разбор резюме | `c:resume:{sha256}:{parser_v}` | 30 д | версия парсера |
| GitHub API | `c:gh:etag:{url}`, `c:gh:body:{url}` | 6 ч | условные запросы |
| Анализ репозитория | `c:gh:repo:{name}:{head_sha}:{analyzer_v}` | 7 д | новый коммит |
| Ответы API ФСП (в fsp-connector) | `c:fsp:part:{id}`, `c:fsp:res:{id}` | 10 мин | вебхук |
| Бейдж, счётчики лендинга | `c:badge:{slug}:{v}`, `c:stats` | 1 ч / 60 с | — |

`make demo-warm` прогревает кеши героев демо: разбор их резюме, анализ GitHub, подготовленные запросы работодателя.

## 7. Лимиты

| Что | Лимит |
|---|---|
| Вход | 10/мин на IP, 5/мин на email |
| Загрузка резюме | 10/сутки |
| Анализ GitHub | 3/сутки |
| Ручная синхронизация ФСП | 1 / 10 мин |
| Попытки кода ФСП | 5 на код |
| Поиск текстом (LLM) | 30/мин на пользователя |
| Выдача кандидатов | 120/мин |
| Открытие карточек | 300/сутки на компанию (антискрейпинг) |
| Офферы | 20/сутки на компанию, 10 входящих в сутки на кандидата (скользящие 24 ч по БД; `offer_company_per_day`, `offer_candidate_per_day`) |
| Тест по навыку | раз в 30 дней (в `DEMO_MODE` без ограничения) |
| ИИ-интервью | 2/сутки |
| Отправка в Telegram | 25/с всего, 1/с в один чат (в боте) |

Числа — в `scoring_config.limits`, меняются без деплоя.
