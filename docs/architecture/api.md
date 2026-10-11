# API

REST API сервиса `core`. Полная спецификация с запросами, ответами и кодами ошибок — [openapi.json](../openapi.json) (OpenAPI 3.1, генерируется из кода: `make openapi`; CI сверяет файл с кодом). На стенде: Swagger UI — `/api/docs`, ReDoc — `/api/redoc`.

## Общие правила

- **Базовый путь** — `/api/v1` (gateway срезает префикс). 218 операций.
- **Формат** — JSON, время в UTC (ISO 8601), деньги — целые рубли в месяц.
- **Аутентификация** — `Authorization: Bearer <access JWT>`; обновление — `POST /auth/refresh` по cookie `rt` ([security.md](security.md)).
- **Ошибки** — RFC 9457 Problem Details (`application/problem+json`) с машинным полем `code`:

  ```json
  {"type": "about:blank#offer_limit_exceeded", "title": "Лимит офферов на сутки исчерпан",
   "status": 429, "code": "offer_limit_exceeded", "errors": []}
  ```

  `errors` — ошибки полей при 422. При 429 — заголовок `Retry-After`. Чужой ресурс — 404.
- **Пагинация** выдачи — непрозрачный курсор `next_cursor` и `limit` (до 100).
- **Идемпотентность** — `Idempotency-Key` при создании оффера: повтор того же запроса возвращает исходный оффер, тот же ключ с другим телом — 409.
- **Трассировка** — заголовок `X-Request-Id` становится `correlation_id` в логах и событиях.
- **Клиент фронта** генерируется orval из OpenAPI (`make api-gen`), руками его не правим.

## Группы эндпоинтов

| Группа | Префиксы | Роль | Назначение |
|---|---|---|---|
| Аутентификация | `/auth/*`, `/me`, `/me/consents`, `/me/profile` | все | Регистрация, вход (пароль, Telegram, magic-ссылка, жюри), refresh, email-код, согласия, личный профиль |
| Кандидат | `/candidates/me/*` | candidate | Анкета, предпочтения, видимость, стоп-лист, аватар, PDF, категория и спор, просмотры, удаление |
| Резюме | `/candidates/me/resumes/*` | candidate | Загрузка, статус разбора, подтверждение |
| Тест | `/assessment/*` | candidate | Опрос, попытки, следующее задание, ответ, разбор, «Объясни ответ», история, превью плана |
| Регулярные задания | `/assessment/tasks/*`, `/employer/tasks/*` | candidate / employer | Задания категории, ответы, оценка |
| Конструктор | `/families/*` | employer, fsp_admin | Создание задания, готовность |
| Граф | `/candidates/me/graph`, `/candidates/{pseudo_id}/graph` | candidate / employer | Подграф доказательств (анонимный для работодателя) |
| ФСП | `/candidates/me/fsp/*`, `/auth/fsp/*` | candidate | Привязка через реестр, заявка, синхронизация, обзор |
| Справочник | `/taxonomy/*` | все | Навыки, профессии, подсказки ввода |
| Компании | `/companies/*`, `/company-invites/*` | employer | Компания, логотип, команда HR, приглашения в команду, журнал доступа |
| Вакансии | `/vacancies/*` | employer / все | CRUD, публикация, закрытие; публичный список и отклик |
| Подбор | `/needs/*`, `/categories/{p}/{g}/candidates`, `/shortlist`, `/search/*`, `/subscriptions` | employer | Потребность → категории → кандидаты, поиск, разбор запроса, шорт-лист, подписки |
| Карточка | `/candidates/{pseudo_id}/card`, `/similar` | employer | Анонимная карточка и похожие кандидаты |
| Рост кандидата | `/candidates/me/standing`, `/navigator`, `/uplift`, `/interests` | candidate | Сила и место, путь к следующему грейду, uplift, интересы компаний |
| Офферы | `/offers/*`, `/interests/*`, `/team-offers`, `/teams`, `/candidates/me/offers`, `/candidates/me/applications` | employer / candidate | Интерес, приглашение, отклик, статусы, контакты, переписка, задание, жалоба, отзыв доступа |
| Рекомендации | `/recs/*` | employer | Реакции на выдачу и подстройка сессии |
| Open Badge | `/me/credentials`, `/public/credentials/*`, `/.well-known/did.json` | candidate / все | Выпуск, отзыв, проверка |
| Публичное | `/public/profiles/{slug}`, `/public/stats` | все | Публичный профиль, цифры лендинга |
| Аналитика | `/track`, `/admin/dashboard`, `/admin/metrics`, `/admin/summary`, `/admin/live-runs`, `/run/{token}` | все / fsp_admin | Сбор событий, воронки, живые прогоны |
| Администрирование | `/admin/families/*`, `/admin/assessment/generate`, `/admin/professions/*`, `/admin/skills/*`, `/admin/skill-cards/*`, `/admin/companies/*`, `/admin/complaints/*`, `/admin/fsp/*`, `/admin/demo/*` | fsp_admin | Допуск заданий, справочник, модерация, реестр ФСП, демо-экраны |
| SSE | `/events/stream` | все | Поток уведомлений и статусов |

## Internal API

Не публикуется наружу (gateway отвечает 404), требует `Authorization: Service <token>`.

| Сервис | Путь | Кто вызывает | Назначение |
|---|---|---|---|
| core | `/internal/tg/*`, `/internal/auth/magic-link` | bot | Действия пользователя из Telegram, короткий токен кандидата для теста |
| core | `/internal/taxonomy/snapshot` | ml | Снимок справочника навыков для быстрого сопоставления |
| core | `/internal/track` | сервисы | События аналитики |
| ml-api | `/v1/embeddings`, `/v1/query/parse`, `/v1/skills/resolve`, `/v1/skills/card-draft`, `/v1/families/key-draft`, `/v1/families/generate`, `/v1/families/solve`, `/v1/assessment/explain`, `/healthz` | core | ML-функции ([ml.md](../mechanics/ml.md)) |
| fsp-connector | `/internal/links*`, `/internal/oauth/*`, `/internal/registry/*`, `/internal/demo/*` | core | Привязка, реестр ФСП, демо-кнопки |
| fsp-connector | `POST /integrations/fsp/webhook` | ФСП | Публичный вебхук с подписью HMAC |

API мока ФСП (`/api/v1/participants`, `/competitions`, `/teams`, `/verification/*`, OAuth `/oauth/*`, OIDC discovery) описан в [fsp.md](../mechanics/fsp.md).
