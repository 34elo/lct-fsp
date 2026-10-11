# Архитектура

ФСП Карьера — модульный монолит `core` и несколько сервисов-спутников, связанных шиной RabbitMQ. Почему так — [ADR-0001](../adr/0001-modular-monolith-and-satellites.md).

## Функциональная архитектура

```mermaid
flowchart LR
  subgraph Кандидат
    C1[Регистрация и согласия] --> C2[Резюме — необязательно]
    C2 --> C3[Опрос: направление, стек, формат, вилка, грейд]
    C3 --> C4[Тест на заявленный грейд]
    C4 --> C5[Категория: профессия × грейд]
    C5 --> C6[ФСП, регулярные задания, навигатор]
  end
  subgraph Работодатель
    E1[Компания] --> E2[Потребность текстом или фильтрами]
    E2 --> E3[Рекомендованные категории]
    E3 --> E4[Кандидаты по rank с объяснением]
    E4 --> E5[Интерес → приглашение с вилкой]
  end
  C5 -. видимость после теста и согласия .-> E4
  E5 --> C7[Принять / отклонить]
  C7 --> E6[Контакты, переписка, статусы найма]
  subgraph ФСП
    F1[Реестр: мероприятия, участники, результаты] --> C6
  end
```

Пять функциональных блоков:

| Блок | Что делает | Где описано |
|---|---|---|
| Идентичность и профиль | Регистрация, вход, роли, согласия, анкета, резюме, видимость | [security.md](security.md), [features.md](../product/features.md) |
| Тест и категоризация | Опрос, генерация вариантов, адаптивный тест, грейды, банк заданий | [assessment.md](../mechanics/assessment.md) |
| Доказательства и доверие | Граф навыков, доказательства из теста, резюме, ФСП, заданий; доверие к навыку | [skills.md](../mechanics/skills.md) |
| Подбор и контакт | Потребность → категории → кандидаты, поиск, интерес, приглашения, отклики, раскрытие контактов | [matching.md](../mechanics/matching.md), [contact.md](../mechanics/contact.md) |
| Интеграции | ФСП (реестр, мок, синхронизация), Telegram, ML/LLM | [fsp.md](../mechanics/fsp.md), [ml.md](../mechanics/ml.md) |

## Компонентная архитектура

```mermaid
flowchart TB
  U[Браузер] --> GW[gateway · Caddy :28080]
  TG[Telegram] <--> BOT[bot · aiogram]
  GW --> WEB[web · React SPA]
  GW -->|/api/v1| API[core-api · FastAPI]
  GW -->|/integrations/fsp| FSPC[fsp-connector]
  API --> PG[(PostgreSQL + pgvector)]
  API --> R[(Redis)]
  API --> S3[(MinIO)]
  API -->|internal HTTP| ML[ml-api]
  API -->|internal HTTP| FSPC
  W[core-worker] --> PG
  SCH[core-scheduler] --> MQ
  API -. outbox .-> MQ{{RabbitMQ}}
  W <--> MQ
  MLW[ml-worker-llm / ml-worker-code] <--> MQ
  FSPC <--> MQ
  BOT <--> MQ
  BOT -->|internal HTTP| API
  FSPC --> FPG[(БД fsp_connector)]
  FSPC --> MOCK[fsp-mock]
  ML --> LLM[llama-server на хосте · необязательно]
  MLW --> LLM
```

| Компонент | Технологии | Назначение |
|---|---|---|
| `web` | React 19, Vite, TypeScript, Tailwind 4, TanStack Query, `@fsp/ui` | SPA для трёх ролей; данные только через сгенерированный из OpenAPI клиент |
| `gateway` | Caddy 2 | Единая точка входа, роутинг по Host и пути, SSE без буферизации, `/internal/*` наружу закрыт |
| `core-api` | FastAPI, SQLAlchemy 2 async, Pydantic v2 | REST API, SSE `/events/stream` |
| `core-worker` | FastStream | Обработчики очередей `core.*`, ретранслятор outbox |
| `core-scheduler` | APScheduler | Команды по расписанию: истечение офферов, синхронизация ФСП, рейтинг компаний, предложения профессий |
| `ml-api` | FastAPI, sentence-transformers | Эмбеддинги, разбор запроса, сопоставление навыков, черновики ключей и объяснений |
| `ml-worker-llm`, `ml-worker-code` | FastStream | Разбор резюме и генерация заданий через очередь `ml.llm` (приоритеты, `prefetch=1`) |
| `fsp-connector` | FastAPI, своя БД | Порт ФСП, реестр, привязка, синхронизация, вебхук |
| `fsp-mock` | FastAPI | Имитация API ФСП с OAuth 2.0 + PKCE и OIDC discovery |
| `bot` | aiogram 3 | Telegram-канал без бизнес-логики |
| PostgreSQL 16 + pgvector | — | Данные core и fsp-connector (две базы, свои роли) |
| RabbitMQ | — | События, команды, UI-шина для SSE |
| Redis | — | Кеш выдачи, лимиты, одноразовые токены, сессии бота |
| MinIO | — | Резюме, аватары, логотипы |

Модули `core` (`services/core/app/*`) общаются только через `service.py` друг друга; в чужие модели и репозитории не ходят. Сервисы-спутники не ходят в БД `core`: только события, команды и internal API с сервисными токенами. Подробнее — [modules.md](modules.md).

## Ключевые потоки

### Регистрация → тест → категория

```mermaid
sequenceDiagram
  actor C as Кандидат
  participant W as web
  participant A as core-api
  participant DB as PostgreSQL
  participant Q as RabbitMQ
  C->>W: регистрация + согласие ПДн
  W->>A: POST /auth/register
  C->>W: опрос (профессия, стек, вилка, грейд)
  W->>A: PUT /assessment/survey
  W->>A: POST /assessment/attempts
  loop пока SPRT не принял решение
    W->>A: GET /attempts/{id}/next
    A-->>W: вариант задания (без ключа)
    W->>A: POST /attempts/{id}/answers
    A->>A: проверка пересборкой варианта, LLR += …
  end
  A->>DB: θ, калибровка b, грейд, доказательства test
  A->>DB: outbox: assessment.attempt.finished, candidate.category.changed
  DB-->>Q: relay
  Q-->>A: core-worker: пересчёт профиля, подписки, уведомления
```

### Потребность → приглашение → контакты

```mermaid
sequenceDiagram
  actor E as Работодатель
  actor C as Кандидат
  participant A as core-api
  participant B as bot
  E->>A: POST /needs {text}
  A-->>E: категории с affinity и счётчиками
  E->>A: GET /categories/{p}/{g}/candidates
  A-->>E: анонимные карточки по rank
  E->>A: POST /interests (вилка, сообщение)
  A-->>C: SSE + Telegram «вами интересуются»
  C->>A: POST /interests/{id}/open
  E->>A: POST /interests/{id}/invite
  C->>A: POST /offers/{id}/accept
  A->>A: contact_reveals (единственная точка раскрытия)
  E->>A: GET /offers/{id}/contacts
```

### Результат ФСП → профиль

`fsp-connector` получает новые результаты (вебхук, синхронизация по расписанию или кнопке) → пишет `fsp.results.imported` в свой outbox → `core-worker` сохраняет факты, пересобирает доказательства `fsp` по правилам «дисциплина → навыки» → пересчёт доверия к навыкам и силы профиля → уведомление кандидату.

## Надёжность сообщений

- Событие пишется в таблицу `outbox` в той же транзакции, что и данные; ретранслятор публикует его с подтверждением брокера.
- Обработчики идемпотентны: id сообщения фиксируется в `inbox` в той же транзакции, повтор отбрасывается.
- Ошибка обработчика → очередь задержки 5 с → 30 с → 2 мин → DLQ.

Подробно — [messaging.md](messaging.md).

## Масштабирование и интеграция

- Модули `core` уже общаются событиями из `packages/contracts`: любой можно вынести в сервис без смены контрактов.
- Поиск и подбор работают в памяти поверх SQL-фильтров (сотни–тысячи анкет); при росте до сотен тысяч — отдельная read-модель поиска из outbox.
- Новый источник ФСП — новый адаптер `FspPort` с маппингом; ядро не меняется.
- LLM — сменный модуль за `ml-api` и очередью `ml.llm`: локальная модель, облачный OpenAI-совместимый провайдер или без LLM вовсе.

## Концепции за рамками MVP

**Защита от фиктивных вакансий и недобросовестных работодателей.** Уже есть: модерация компании (`pending → verified/rejected/blocked`), метка «проверена» для кандидатов, лимиты интересов и приглашений, обязательная вилка, жалобы кандидатов с разбором администратором, рейтинг ответственности компании (доля принятых приглашений со штрафами за отозванные и просроченные), предупреждение о вилке ниже ожиданий кандидата. Дальше: проверка ИНН по ЕГРЮЛ и домена почты, скоринг риска вакансии (вилка вне рынка, массовые приглашения без найма, повторные жалобы), автоматическое снижение в выдаче и блокировка, публичная история найма компании.

**Интеграция с ATS.** Работодатель подключает ATS по OAuth-токену компании. Платформа отдаёт вебхуки `offer.accepted`, `offer.status_changed`, отклики и шорт-лист в формате ATS (кандидат со ссылкой на анонимную карточку, контакты — только после принятия); из ATS принимаются вакансии и статусы найма (`interview`, `hired`, `not_hired`). Внутри это ещё один потребитель событий `offer.*` и адаптер на каждую ATS, по образцу `FspPort`.

**Дальше по дорожной карте:** настоящий FSP ID на Keycloak вместо мока, обучение ранжирования на накопленных показах и реакциях, объективный тест для дизайнеров (ревью макета с внесёнными дефектами), Telegram Mini App.
