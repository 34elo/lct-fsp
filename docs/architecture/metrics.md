# Метрики, сбор данных и аналитика

> Как мы собираем данные о работе продукта и считаем метрики. Кому какие цифры показываем. Как доказываем жюри, что продукт работает, если реальных пользователей нет.
> Данные для оценки алгоритмов (эталоны, синтетический рынок, демо-наполнение) — [evaluation.md](evaluation.md).

## 1. Четыре контура

| Контур | Вопрос | Откуда данные | Где видно | Кто смотрит |
|---|---|---|---|---|
| **A. Качество алгоритмов** (офлайн) | Насколько хорошо работают разбор резюме, граф навыков, доверие, подбор, тест? Лучше ли мы поиска по ключевым словам? | Эталонные наборы + синтетический рынок → `make eval` | Страница качества в админке, слайд питча | Жюри, команда |
| **B. Продуктовые события** (онлайн) | Что делают кандидаты и работодатели, где воронка теряет людей, как отвечают на офферы? | Трекинг-план: события с сервера и фронта → `analytics_events` | Дашборд ФСП, аналитика работодателя, страница качества | ФСП, работодатель, команда |
| **C. Живые прогоны** | Быстро ли и понятно ли реальному человеку пройти сценарий? | Режим испытаний: события с меткой прогона + анкета SUS | Страница качества → «Живые прогоны» | Жюри, команда |
| **D. Технические метрики** | Держим ли SLO: разбор ≤ 30 с, push ≤ 3 с, поиск ≤ 300 мс? Не забита ли GPU? | Prometheus: FastAPI, FastStream, RabbitMQ, llama-server, PostgreSQL | Grafana (профиль `obs`) + блок «Здоровье» в админке | Команда |

Главный принцип для жюри: **каждая цифра показывается вместе с базовым решением** (поиск по ключевым словам) **и с объяснением, как её считали**.

## 2. Контур B: продуктовые события

### 2.1. Откуда берутся события

```
серверные доменные события (RabbitMQ events) ──► core-worker: очередь core.analytics ──► analytics_events
события интерфейса (web)       ── POST /api/v1/track (батч, sendBeacon) ───────────────► analytics_events
события бота                   ── bot → POST /internal/track ─────────────────────────► analytics_events
```

- **Серверные события надёжнее**: оффер, принятие, разбор резюме, импорт ФСП. Они и так идут через RabbitMQ, отдельная очередь `core.analytics` подписана на `events.#` и переводит их в аналитические **без кода в бизнес-модулях**.
- **С фронта** приходят только то, чего сервер не видит: показ блока, клик по чипсу, правка фильтра, время на карточке, клик по uplift.
- **Батчинг на фронте:** очередь в памяти, отправка раз в 5 с или при `visibilitychange` через `navigator.sendBeacon`. До 50 событий в запросе.

### 2.2. Конверт события

```json
{
  "event": "search_submitted",
  "ts": "2026-10-05T12:00:00.123Z",
  "actor": "a_7f3c…",                 // HMAC(user_id) — псевдоним, не user_id
  "role": "employer",                 // candidate | employer | fsp_admin | anon
  "session_id": "s_…",                // сессия интерфейса (30 мин бездействия = новая)
  "channel": "web",                   // web | tg | system
  "run_id": null,                     // id живого прогона (контур C), если есть
  "app_version": "0.3.1",
  "props": { "query_len": 54, "chips": 4, "parse_source": "llm", "latency_ms": 1830 }
}
```

**В `props` никогда нет ПДн:** ни имён, ни текста резюме, ни текста запроса работодателя (только длина и разобранные фильтры), ни email. Валидация по pydantic-схеме события в `packages/contracts/analytics.py`. Неизвестное событие или лишнее поле отклоняется.

### 2.3. Трекинг-план (MVP)

**Кандидат**

| Событие | Источник | Ключевые `props` |
|---|---|---|
| `signup_completed` | сервер | `channel`, `method` (email/tg/fsp) |
| `consent_granted` / `consent_revoked` | сервер | `type` |
| `resume_uploaded` | сервер | `mime`, `pages` |
| `resume_parsed` | сервер (ml) | `duration_ms`, `skills_found`, `skills_dropped_no_quote`, `new_skills`, `ok` |
| `resume_confirmed` | сервер | `edits_count`, `skills_added`, `skills_removed` |
| `fsp_link_started` / `fsp_link_completed` | сервер | `method`, `verified`, `duration_ms`, `results_imported` |
| `github_analysis_completed` | сервер | `repos`, `deep_repos`, `flags`, `duration_ms` |
| `profile_updated` | сервер | `profile_version`, `skills_up`, `grade_from`, `grade_to`, `trigger` |
| `test_started` / `test_completed` | сервер | `skill`, `questions`, `theta`, `level_from`, `level_to`, `channel` |
| `interview_completed` | сервер | `questions`, `avg_score` |
| `uplift_shown` / `uplift_clicked` | фронт, бот | `skill`, `pct`, `position`, `action` (test/github/competition) |
| `competition_clicked` | фронт, бот | `competition_id`, `skill`, `source` (navigator/uplift) |
| `graph_opened` | фронт | `nodes`, `from` (profile/card) |
| `offer_received` / `offer_opened` | сервер | `offer_id`, `channel`, `score`, `p_accept` |
| `offer_accepted` / `offer_declined` | сервер | `offer_id`, `reason`, `time_to_respond_s`, `channel` |
| `offer_question_asked` | сервер | `offer_id` |
| `skill_request_received` / `skill_request_completed` | сервер | `skill` |

**Работодатель**

| Событие | Источник | Ключевые `props` |
|---|---|---|
| `company_registered` / `company_verified` | сервер | — |
| `vacancy_published` | сервер | `role`, `grade`, `required_skills`, `salary_range_ratio`, `qualities` |
| `salary_range_warning_shown` | фронт | `ratio` |
| `market_cell_clicked` | фронт | `role`, `grade`, `metric` |
| `search_submitted` | сервер | `query_len`, `chips`, `parse_source` (rule/llm/cache), `latency_ms`, `refining` |
| `chip_edited` / `chip_removed` | фронт | `key`, `source` (rule/llm) — **косвенная ошибка разбора запроса** |
| `results_shown` | сервер | `n`, `latency_ms`, `context` (search/vacancy/similar), `session_id` (связь с `impressions`) |
| `card_opened` | сервер | `position`, `score`, `context` |
| `card_dwell` | фронт | `seconds` |
| `shortlisted` / `dismissed` | сервер | `position`, `reason` |
| `rec_adjustment_applied` | сервер | `features_changed` |
| `graph_path_highlighted` | фронт | `requirement` |
| `salary_hint_shown` | сервер | `below_min`, `vs_median`, `p_accept_bucket` |
| `offer_sent` | сервер | `score`, `p_accept`, `below_min` |
| `interview_kit_generated` | сервер | `questions` |
| `skill_test_requested` | сервер | `skill` |

**Админ и система**

| Событие | Источник | Ключевые `props` |
|---|---|---|
| `skill_node_created` | сервер | `kind`, `decision`, `context` |
| `skill_decision_by_admin` | сервер | `decision` (merge/distinct/approve/reject), `auto_suggestion` — **совпало ли с решением конвейера** |
| `skill_promoted` | сервер | `support` |
| `recompute_done` | сервер | `duration_ms`, `evidence`, `trigger` |
| `matches_computed` | сервер | `vacancy_id`, `candidates`, `duration_ms` |

### 2.4. Хранение

```sql
CREATE TABLE analytics_events (
  id          bigserial,
  ts          timestamptz NOT NULL,
  event       text NOT NULL,
  actor       text,                 -- псевдоним HMAC(user_id, ANALYTICS_SALT)
  role        text,
  session_id  text,
  channel     text,
  run_id      uuid,
  app_version text,
  props       jsonb NOT NULL DEFAULT '{}',
  PRIMARY KEY (id, ts)
) PARTITION BY RANGE (ts);          -- партиция на месяц, создаёт core-scheduler
CREATE INDEX ON analytics_events (event, ts);
CREATE INDEX ON analytics_events (actor, ts);
CREATE INDEX ON analytics_events (run_id) WHERE run_id IS NOT NULL;
```

- Отдельная схема `analytics` в базе core: та же база, другие права. Пишет только core-worker и `/track`.
- **ClickHouse не нужен:** на хакатоне это десятки тысяч событий, у пилота — миллионы, PostgreSQL с партициями справится.
- **Агрегаты** — материализованные представления, обновляются core-scheduler раз в 5 минут: `mv_candidate_funnel_daily`, `mv_employer_funnel_daily`, `mv_offer_outcomes`, `mv_fsp_dashboard`, `mv_search_quality_daily`, `mv_skills_graph_daily`.
- **Хранение:** сырые события — 180 дней, агрегаты — бессрочно. При удалении профиля сырые события по псевдониму удаляются (соль известна только серверу).

### 2.5. Определения метрик

**Кандидат**

| Метрика | Формула | Где |
|---|---|---|
| Активация | доля зарегистрированных, у кого за 24 ч появилась категория и ≥ 1 навык с уровнем ≥ 3 | дашборд ФСП |
| Время до профиля | медиана `profile_updated(первый с категорией).ts − signup_completed.ts` | страница качества, живые прогоны |
| Задержка разбора резюме | p50 / p95 `resume_parsed.duration_ms` | качество, Grafana |
| Правок после разбора | медиана `resume_confirmed.edits_count` (цель ≤ 2) | качество |
| Привязка ФСП / GitHub | доля активированных с `fsp_link_completed` / `github_analysis_completed` | дашборд ФСП |
| CTR uplift | `uplift_clicked / uplift_shown` | дашборд ФСП |
| **Конверсия навигатор → соревнование** | `competition_clicked(source ∈ navigator, uplift)` / уникальные кандидаты с показом | **дашборд ФСП — главная метрика для заказчика** |
| Время до первого оффера | медиана `offer_received(первый).ts − активация` | дашборд ФСП |
| Ответ / принятие | `(accepted + declined) / received`, `accepted / received` | дашборд ФСП, работодателю |

**Работодатель и подбор**

| Метрика | Формула | Где |
|---|---|---|
| Время до шорт-листа | медиана от `search_submitted` до третьего `shortlisted` в той же сессии | качество, живые прогоны |
| Шагов до оффера | число событий работодателя от входа до `offer_sent` | живые прогоны |
| Ошибка разбора запроса (косвенная) | доля поисков, где был `chip_edited` или `chip_removed` для LLM-чипса | качество |
| CTR по позиции | `card_opened / impressions` по позициям 1–20 | качество (кривая позиционного смещения) |
| Доля шорт-листа | `shortlisted / card_opened` | качество |
| **Калибровка скора** | доля `offer_accepted` по корзинам `score` и `p_accept` | качество (на демо-истории офферов) |
| **Ошибка подбора (косвенная)** | доля отказов с причиной `wrong_stack` | работодателю («уточните навыки»), качество |
| Офферы ниже ожиданий | доля `offer_sent.below_min` | дашборд ФСП |
| Эффект подстройки в сессии | CTR после `rec_adjustment_applied` против до | качество |

**Граф навыков**

| Метрика | Формула |
|---|---|
| Рост графа | новые вершины и рёбра в день по источникам (`skill_node_created`) |
| Автономность | доля упоминаний, разобранных без админа |
| **Точность конвейера (онлайн)** | доля `skill_decision_by_admin`, где админ согласился с предложением конвейера |
| Нагрузка на админа | размер очереди и медианное время решения |

**Справедливость** (контур A на синтетике и контур B на демо-показах)

| Метрика | Формула |
|---|---|
| Impact ratio группы | `доля группы в топ-10 / доля группы в пуле кандидатов`, делённая на то же для наиболее представленной группы |
| Правило четырёх пятых | группы с impact ratio < 0.8 подсвечиваются красным |
| Группы | без ФСП / с ФСП · без вуза / с вузом · без GitHub / с GitHub · по регионам (если есть). Пол и возраст не храним, поэтому не считаем |

**LLM и ML**

| Метрика | Формула |
|---|---|
| Задержка и скорость | p50 / p95 по задачам, токенов/с (`llama-server --metrics`) |
| Валидность JSON | доля ответов, прошедших pydantic с первой попытки |
| Отброшено без цитаты | `skills_dropped_no_quote / skills_found` |
| Ожидание GPU | время в очереди `ml.llm` по приоритетам |

## 3. Контур C: живые прогоны

**Режим испытаний** — способ измерить удобство без реальных пользователей (5–8 человек не из команды).

1. Админ создаёт прогон: сценарий (`candidate` или `employer`), список заданий, ссылка-приглашение.
2. Испытатель открывает ссылку. Все его события получают `run_id`, таймер стартует на первом действии.
3. **Задания засчитываются автоматически по событиям**, без кнопки «готово»:

| Сценарий | Задание | Считается выполненным по событию |
|---|---|---|
| Кандидат | Создать профиль из резюме | `resume_confirmed` |
| Кандидат | Подтвердить достижения ФСП | `fsp_link_completed` |
| Кандидат | Узнать, какой навык подтвердить | `uplift_clicked` или `competition_clicked` |
| Кандидат | Ответить на оффер | `offer_accepted` или `offer_declined` |
| Работодатель | Найти 5 подходящих кандидатов | 5 × `shortlisted` |
| Работодатель | Понять, почему кандидат подходит | `graph_path_highlighted` или `card_dwell ≥ 20 с` |
| Работодатель | Отправить оффер | `offer_sent` |

4. В конце — **анкета SUS** (10 стандартных вопросов, шкала 1–5) и вопрос «Согласны ли вы со своей категорией и грейдом?». Балл SUS: `(Σ_нечётные(x − 1) + Σ_чётные(5 − x)) × 2.5`, цель ≥ 75.
5. На странице качества: успешность заданий (цель ≥ 80%), медианное время, шаги, SUS, согласие с категорией, список затыков (задание, на котором дольше всего стояли).

Таблица: `live_runs(id, scenario, tasks jsonb, invited_at, started_at, finished_at, sus_answers jsonb, sus_score, category_agree, notes)`.

## 4. Контур D: технические метрики

| Источник | Как | Что смотрим |
|---|---|---|
| core-api, ml-api, fsp-connector | `prometheus-fastapi-instrumentator` → `/metrics` | RPS, p95 по эндпоинтам, 5xx |
| core-worker, ml-worker, bot | FastStream Prometheus middleware | время обработки, ошибки, ретраи по очередям |
| RabbitMQ | встроенный плагин `rabbitmq_prometheus` (порт 15692) | глубина очередей, DLQ, скорость публикации |
| llama-server | `--metrics` | токены/с, занятость слотов, очередь |
| PostgreSQL | `postgres_exporter` | соединения, медленные запросы |
| Redis | `redis_exporter` | память, попадания в кеш |

**SLO** (цвет в блоке «Здоровье» админки и в Grafana):

| SLO | Цель |
|---|---|
| Разбор резюме, p95 | ≤ 30 с |
| От «Отправить оффер» до push в Telegram, p95 | ≤ 3 с |
| Поиск кандидатов, p95 | ≤ 300 мс |
| Разбор текстового запроса, p95 | ≤ 4 с |
| Пересчёт профиля, p95 | ≤ 200 мс |
| DLQ | 0 сообщений |

Профиль compose `obs`: Prometheus + Grafana с готовыми дашбордами (`infra/grafana/*.json`). На демо можно открыть живую картинку очередей и GPU.

**Сквозная трассировка:** `correlation_id` в каждом логе и сообщении. OpenTelemetry + Jaeger — по желанию.

## 5. Контур A: офлайн-оценка (кратко)

Полностью — [evaluation.md](evaluation.md).

- `make eval` запускает все раннеры на эталонах и синтетическом рынке → JSON-метрики + `reports/eval-<дата>.md` → `POST /admin/quality/runs`.
- Каждый раннер сравнивает нас с базовым решением и абляциями (без ФСП, без GitHub, без тестов).
- `make eval-quick` — уменьшенный набор для CI (≤ 2 мин). Падение ключевой метрики больше чем на 5 п.п. помечает PR.

## 6. Где что показываем

| Экран | Метрики |
|---|---|
| **Страница качества** (админка, для жюри) | Таблица «метод × метрика» (BM25 / эмбеддинги / наш подбор / абляции), главная цифра — доля приукрашенных резюме в топ-10, точность графа навыков, калибровка скора и `p_accept`, панель справедливости, живые прогоны (SUS, время, успешность), параметры синтетики, ограничения |
| **Дашборд ФСП** | Участники на платформе, активация, офферы, принятия, наймы, конверсия навигатор → соревнование, востребованные навыки, навыки «спрос > подтверждённого предложения», карта регионов |
| **Работодателю** | Ответы на офферы, распределение причин отказа с подсказкой («40% — не тот стек: уточните обязательные навыки»), рейтинг ответственности |
| **Кандидату** | «Вас смотрели N компаний», ответы на офферы, рост доверия по навыкам во времени |
| **Админка «Здоровье»** | SLO, очереди, DLQ, GPU |
| **Grafana** (команда) | Всё техническое |

## 7. Приватность аналитики

- Только псевдонимы: `actor = HMAC(user_id, ANALYTICS_SALT)`. Соль — только на сервере.
- В `props` нет ПДн и свободного текста. Проверяется схемой и тестом.
- Цель «улучшение сервиса и статистика для ФСП» явно указана в согласии на обработку ПДн (152-ФЗ, отдельный документ).
- Дашборд ФСП показывает только агрегаты, ячейки меньше 5 человек скрываются.
- Удаление профиля удаляет сырые события по псевдониму.

## 8. Как реализуем (задачи)

| Задача | Где |
|---|---|
| Схемы событий в `packages/contracts/analytics.py`, валидация | contracts |
| Очередь `core.analytics`: домен → аналитика | core-worker |
| `POST /api/v1/track`, `POST /internal/track`, трекер на фронте (батч + sendBeacon) | core-api, web, bot |
| `analytics_events` с партициями, материализованные представления, обновление по расписанию | core |
| Режим испытаний: `live_runs`, приглашение, автозасчёт заданий, анкета SUS | core, web |
| Prometheus-метрики во всех сервисах, профиль `obs`, дашборды Grafana | все, infra |
| Страница качества, дашборд ФСП, блок «Здоровье» | web |
| Бэкфилл демо-событий за 2 недели (`tools/seed`), чтобы дашборды не были пустыми, с пометкой «демо-данные» | tools |
