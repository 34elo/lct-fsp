# Сервисы и зоны ответственности

> Пять своих сервисов, у каждого понятный смысл и владелец: **web**, **core**, **ml**, **fsp-connector**, **bot**. Плюс **fsp-mock** вместо настоящего ФСП. Шина между ними — **RabbitMQ** ([messaging.md](messaging.md)). Центральная модель данных — **граф доказательств** в core ([graph.md](graph.md)).

## 1. Правила границ

- **Данными владеет один сервис.** PostgreSQL физически один, но у сервисов отдельные базы и пользователи: `core`, `fsp_connector`. В чужую базу никто не ходит.
- **Синхронно — только когда нужен ответ сразу**, всё остальное — события и команды через RabbitMQ. У каждого синхронного вызова есть таймаут и фолбэк.
- **Контракты лежат в одном месте:** `packages/contracts` — pydantic-схемы событий, команд и DTO. Ломающее изменение — новый `schema_version` или новое имя.
- **Общая платформа:** `packages/platform` — конфиг, подключение к БД, outbox и inbox, публикация и подписка (FastStream), проверка JWT, логи с `correlation_id`, healthcheck. Новый сервис = шаблон + свои модули.
- **Внутри core** модули общаются через `service.py` друг друга, не через чужие таблицы. Границы проверяет `import-linter`.

## 2. Сервисы

### 2.1. `web` — интерфейс
- React + Vite + TS, один SPA с разделами по ролям: лендинг, кандидат (mobile-first), работодатель, админ ФСП, публичный профиль.
- Ходит только в core (REST + SSE). Клиент генерируется из OpenAPI.
- Подробно: [frontend.md](frontend.md). **Владелец:** Frontend.

### 2.2. `core` — основной бэкенд и граф
Один код, три процесса:
- `core-api` — FastAPI: REST, SSE, internal API для бота;
- `core-worker` — FastStream-потребитель: импорт фактов, пересчёт графа, матчинг, уведомления, фоновые задачи;
- `core-scheduler` — cron, публикует команды.

**Модули** (`services/core/app/modules/<name>/`):

| Модуль | Ответственность | Ключевые таблицы |
|---|---|---|
| `auth` | Аккаунты, вход (email, Telegram Login, одноразовая ссылка из бота, «Войти через ФСП» через fsp-connector), JWT, роли | `users`, `refresh_tokens`, `telegram_accounts` |
| `consents` | Согласия, проверка перед обработкой | `consents` |
| `candidates` | Анкета, предпочтения, видимость, стоп-лист, псевдоним, удаление | `candidates`, `experience`, `education`, `category_disputes` |
| `resumes` | Файлы в MinIO, постановка разбора, приём результата, подтверждение | `resumes` |
| `graph` | **Граф доказательств:** факты, доказательства, пересчёт доверия с наследованием по иерархии, командные сигналы, категория, грейд, эмбеддинг профиля, связи людей, API подграфа | `evidence`, `candidate_skills`, `fsp_participants`, `fsp_results`, `fsp_ranks`, `fsp_competitions`, `fsp_teams`, `fsp_team_members`, `code_repos`, `repo_contributors`, `candidate_links` |
| `taxonomy` | **Граф навыков:** ядро и рост (применяет решения конвейера: новые вершины, синонимы, связи, слияния), смежность и иерархия, роли, дисциплины, правила, веса, ночной рост связей, очередь админа. Держит граф навыков в памяти ([skills.md](skills.md)) | `skills`, `skill_aliases`, `skill_relations`, `skill_distinct`, `skill_blocklist`, `skill_mentions`, `skill_merges`, `roles`, `role_skills`, `disciplines`, `discipline_skill_rules`, `scoring_config` |
| `code` | Привязка GitHub, постановка анализа, приём результата → факты-репозитории | `github_accounts`, `code_analyses` |
| `assessment` | v2 ([assessment.md](assessment.md)): опрос, семейства заданий и мир, попытки, Rasch + SPRT, грейды и кулдауны, жизненный цикл семейств, конструктор | `surveys`, `families`, `attempts`, `responses`, `grades` |
| `companies` | Компании, участники, модерация, рейтинг ответственности | `companies`, `company_members` |
| `vacancies` | Вакансии на профессиональном языке | `vacancies`, `vacancy_skills` |
| `matching` | **Рекомендации:** отбор, скоринг, переранжирование, объяснения, подборки под вакансии, похожие кандидаты, подстройка в сессии, uplift для кандидата, подсказка по вилке | `matches`, `impressions`, `rec_feedback` |
| `search` | Текст → фильтры (правила + ml-api), каталог анонимных карточек, подписки | `saved_searches` |
| `market` | Карта рынка, медианы, навыки рынка | `mv_market_cells` |
| `navigator` | Путь к следующему грейду, uplift, соревнования | `navigator_clicks` |
| `offers` | Офферы, лимиты, статусы, истечение, раскрытие контактов, переписка, жалобы | `offers`, `offer_events`, `offer_messages`, `contact_reveals`, `complaints` |
| `notifications` | События → уведомления: БД, SSE (`ui.user.*`), Telegram (`notify.telegram`) | `notifications` |
| `messaging` | Outbox, inbox, публикация и подписки | `outbox`, `inbox` |
| `analytics` | Приём событий (`/track`, очередь `core.analytics`), агрегаты, живые прогоны, SUS, панель справедливости ([metrics.md](metrics.md)) | `analytics.analytics_events`, `live_runs`, `mv_*` |
| `credentials` | Open Badge 3.0: выпуск, подпись Ed25519, проверка, отзыв | `issued_credentials` |
| `admin`, `public`, `views` | Админка и качество, бейдж и публичный профиль, журнал просмотров | `eval_runs`, `profile_views` |

**Владелец:** Backend-1. Модули `offers`, `notifications`, `companies`, `vacancies` — Backend-2.

### 2.3. `ml` — интеллектуальные блоки
Один код, три процесса. **Без своей БД:** справочник берёт у core (HTTP + кеш), результаты публикует событиями.

| Процесс | Что делает | Как вызывается |
|---|---|---|
| `ml-api` | Текст запроса → фильтры, эмбеддинги, **конвейер навыков** (`/v1/skills/resolve`: модерация, «навык ли это», судья по типу связи) | синхронный HTTP от core, таймаут 2–5 с |
| `ml-worker-llm` | Разбор резюме, генерация и оценка ИИ-интервью, обоснования топ-5, черновики вопросов | очередь `ml.llm` (приоритеты, `prefetch=1`) |
| `ml-worker-code` | Анализ GitHub: клон в песочнице, языки, авторство, технологии, зрелость, флаги, соавторы | очередь `ml.code` |

Использует `llm-chat` (llama.cpp на Vulkan) и bge-m3 на CPU. Подробно: [ml.md](ml.md). **Владелец:** ML.

### 2.4. `fsp-connector` — всё про ФСП
- **Порт `FspPort`** и адаптеры: наш мок, мок организаторов, реальный API. Смена источника затрагивает только этот сервис.
- **Привязка участника:** OAuth «Войти через ФСП» (core запрашивает URL авторизации и обмен кода по HTTP), код подтверждения, ручной ID.
- **Синхронизация:** по команде `fsp.sync`, по вебхуку ФСП (вебхуки приходят сюда, edge маршрутизирует `/integrations/fsp/*`), раз в час.
- **Нормализация:** сырые ответы → `FspResult`, `FspCompetition`, `FspTeam`, `FspRank` → события `fsp.results.imported`, `fsp.competitions.updated`.
- **Своя БД `fsp_connector`:** привязки (`fsp_links`), курсоры синхронизации, сырые ответы (аудит), журнал вебхуков.
- Подробно: [fsp.md](fsp.md). **Владелец:** Backend-2.

### 2.5. `bot` — Telegram
- aiogram 3, long polling, FSM в Redis.
- Онбординг, резюме файлом, привязка ФСП и GitHub, офферы с кнопками, причины отказа, вопросы, тесты, статус поиска, одноразовые ссылки на сайт.
- **Без бизнес-логики:** действия пользователя — HTTP в `core /internal/tg/*`. Исходящие — из очереди `bot.telegram`.
- Подробно: [telegram.md](telegram.md). **Владелец:** Backend-2 (или Frontend в команде из 4 человек).

### 2.6. `fsp-mock`
Имитация ФСП: участники, результаты, соревнования, команды, разряды, OAuth со страницей выбора участника, коды подтверждения, вебхук «новый результат», админ-кнопка для демо. Данные генерирует `tools/seed` вместе с витриной. Доступен на `mock.fsp.patissons.tech`.

### 2.7. Инфраструктура

| Компонент | Зачем |
|---|---|
| PostgreSQL 16 + pgvector + pg_trgm | Граф и все доменные данные core, база fsp-connector |
| RabbitMQ 3.13+ (management) | Шина: события, команды, задачи ML, уведомления, SSE-фан-аут |
| Redis 7 | Кеш, лимиты, FSM бота, одноразовые токены, сессии тестов и рекомендаций |
| MinIO | Файлы резюме |
| llm-chat | llama.cpp server на Vulkan (RX 5700 XT) |
| Caddy | edge на VPS (TLS) и gateway на сервере (статика, маршрутизация) |

## 3. Владельцы

| Зона | 5 человек | 4 человека |
|---|---|---|
| PM, питч, демо | не назначен (совмещает кто-то из команды) | не назначен |
| core: auth, candidates, graph, taxonomy, matching, search, market, navigator, инфраструктура | Backend-1 | Backend |
| core: offers, notifications, companies, vacancies, admin API; fsp-connector; bot; fsp-mock | Backend-2 | Backend + Frontend (бот) |
| ml, модели, эталоны, eval | ML | ML |
| web, дизайн-система, визуализация графа | Frontend | Frontend |
| Данные: справочник, правила ФСП, банк вопросов, seed | ML + PM | ML + PM |

## 4. Трассировка требований → сервисы и модули

Требования — [product.md §8](../archive/product-v1.md#8-требования-moscow).

| Требование | Пр. | Где | Флоу |
|---|---|---|---|
| C1 Регистрация на сайте и в Telegram, согласия | M | core: auth, consents · bot | F1 |
| C2 Резюме → разбор → правка | M | core: resumes, graph · ml-worker-llm | F2 |
| C3 Привязка ФСП, импорт | M | fsp-connector · core: graph | F3, F11 |
| C4 Автоматическая категория | M | core: graph, taxonomy | F5 |
| C5 Навыки с доверием и источниками | M | core: graph (API подграфа) | F5 |
| C6 Офферы, контакты после принятия | M | core: offers, notifications · bot | F8 |
| C7 Настройки интересов | M | core: candidates | — |
| C8 GitHub, ДНК кода | S | ml-worker-code · core: code, graph | F4 |
| C9 Объяснение и оспаривание категории | S | core: graph, candidates | F5 |
| C10 Навигатор + соревнования ФСП + **uplift «+N% вакансий»** | S | core: navigator, matching · fsp-connector (календарь) | F14 |
| C11 Тест и ИИ-интервью | S | core: assessment · ml-worker-llm | F9, F10 |
| C12 Mini App | W | — | — |
| C13 Бейдж «Подтверждено ФСП» | C | core: public | — |
| C14 Резюме из подтверждённого профиля | C | core: candidates | — |
| E1 Компания, модерация | M | core: companies, admin | — |
| E2 Вакансии на профессиональном языке | M | core: vacancies, taxonomy | F7 |
| E3 Каталог, фильтры по доверию и ФСП | M | core: search, market | F6 |
| E4 Анонимные карточки | M | core: search, graph, views | F6 |
| E5 Оффер с обязательной вилкой | M | core: offers | F8 |
| E6 Процент совпадения с объяснением | M | core: matching (пути в графе) | F6, F7 |
| E7 Подбор под вакансию | M | core: matching | F7 |
| E8 Карта рынка | S | core: market | — |
| E9 Поиск обычным текстом | S | core: search · ml-api | F6 |
| E10 «Вилка ниже рынка» | C | core: matching | F8 |
| E11 Подписка на категорию | C | core: search, notifications | F5 |
| E12 Найм команды ФСП | C | core: graph (`candidate_links`), offers | — |
| **E14 Похожие кандидаты и подстройка выдачи под работодателя** | S | core: matching (уровень 1) | F6 |
| A1 Справочник, правила дисциплин | M | core: taxonomy, admin | — |
| A2 Модерация | S | core: companies, offers, admin | — |
| A3 Дашборд | S | core: admin, market | — |
| A4 Страница качества | S | core: admin · tools/eval | — |
| Q1 Развёрнуто, документировано (OpenAPI + AsyncAPI) | M | все | — |
| Q2 Локальная обработка | M | ml | — |
| Q3 Согласия, анонимизация, удаление | M | core: consents, candidates, graph | F13 |
| Q4 Резюме ≤ 30 с с прогрессом | S | ml-worker-llm (приоритет), core: SSE | F2 |
| Q6 Тестовые и реальные данные ФСП | M | fsp-connector (адаптеры) | F3 |
| Q7 Воспроизводимое демо | M | tools/seed, `make demo-reset` | — |
| **Метрики качества и продукта** (архив [product-v1.md §15](../archive/product-v1.md)) | M | tools/eval, core: analytics, страница качества | — |
| Идея 1: взаимный подбор | S | core: matching (`p_accept`) | F7, F8 |
| Идея 4: панель справедливости | S | tools/eval `fairness`, core: analytics | — |
| Идея 6: предупреждение о широкой вилке | C | core: vacancies, offers | F8 |
| Идея 7: вопросы для структурированного интервью | C | core: assessment · ml-worker-llm | — |
| Идея 8: Open Badge 3.0 | C | core: credentials | — |
| Идеи 2–3 (минимально): «попросить подтвердить навык», срок действия теста | C | core: assessment, notifications · bot | F9 |
