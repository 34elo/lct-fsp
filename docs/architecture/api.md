# API и контракты

> **Источник правды после старта разработки** — OpenAPI, который генерирует FastAPI (`/api/v1/openapi.json`, Swagger UI на `/api/docs`, ReDoc на `/api/redoc`). Этот документ фиксирует **договорённости до кода**, чтобы фронт, бот и ML начали работать параллельно. Если код расходится с документом, обновляем документ в том же PR.
> Межпроцессные контракты (события и команды RabbitMQ, `ui.user.*`, `notify.telegram`) лежат в `packages/contracts` и описаны в AsyncAPI (FastStream), см. [messaging.md](messaging.md).

## 1. Конвенции

| Тема | Правило |
|---|---|
| Базовый путь | `https://api.fsp.patissons.tech/api/v1` (публичное), `/internal` (сервисное, gateway наружу не пропускает). SPA живёт на `dashboard.fsp.patissons.tech`: CORS только для него, с credentials |
| Формат | JSON, `snake_case` в полях, даты ISO 8601 UTC, деньги — целые рубли/мес |
| Аутентификация | `Authorization: Bearer <access_jwt>` (15 мин). Refresh — httpOnly `Secure` `SameSite=Lax` cookie `rt` на путь `/api/v1/auth`, 30 дней, с ротацией |
| Internal | `Authorization: Service <token>` (отдельный токен на каждый сервис: bot, ml, mock) |
| Ошибки | RFC 9457 Problem Details: `{"type","title","status","detail","code","errors":[{"field","message"}]}`. `code` — машинный: `offer_limit_exceeded`, `salary_range_required`, `consent_required`… |
| Пагинация | курсорная: `?cursor=&limit=` (по умолчанию 20, максимум 100) → `{"items":[], "next_cursor": "…"|null, "total": 123?}` |
| Идемпотентность | `Idempotency-Key` обязателен для `POST /offers`, `POST /team-offers`. Повторный ключ возвращает исходный ответ (хранится в Redis 24 ч) |
| Асинхронные операции | `202 Accepted` + `{"job_id", "resource_id"}`. Статус — по ресурсу (`GET …/{id}`), прогресс — по SSE |
| Версии ресурсов | В ответах профиля есть `profile_version`, у вакансии `version`. Фронт по ним понимает, что SSE-обновление относится к текущим данным |
| Лимиты | `429` + `Retry-After`. См. [messaging.md §6](messaging.md#7-лимиты) |
| Трассировка | `X-Request-ID` (генерирует edge или клиент) прокидывается в логи, задачи и вызовы ml |
| Роли | В каталоге ниже: `C` — кандидат, `E` — сотрудник компании, `EA` — админ компании, `A` — админ ФСП, `P` — публично, `S` — сервис |

## 2. Каталог эндпоинтов

### 2.1. Аутентификация и аккаунт

| Метод и путь | Роль | Назначение |
|---|---|---|
| `POST /auth/register` | P | `{email, password, role: candidate|employer}` |
| `POST /auth/login` | P | `{email, password}` → `{access_token, user}` + cookie |
| `POST /auth/refresh` | P (cookie) | Ротация refresh, новый access |
| `POST /auth/logout` | любая | Отзыв семьи refresh-токенов |
| `POST /auth/telegram` | P | Данные Telegram Login Widget → вход или регистрация кандидата |
| `POST /auth/magic` | P | `{token}` из ссылки бота → вход |
| `GET /auth/fsp/start` | P/C | Редирект на OAuth ФСП (мок). Для вошедшего кандидата это привязка, иначе вход |
| `GET /auth/fsp/callback` | P/C | Обмен кода → `fsp_links` → `fsp_sync` |
| `GET /me` | любая | `{user, role, candidate?, company?, consents, telegram_linked}` |
| `GET /me/consents`, `PUT /me/consents` | любая | Список и выдача/отзыв согласий |
| `POST /me/telegram/link` | C, E | → `{deep_link}` для привязки Telegram |

Коды ошибок `/auth/*`: `email_taken` (409), `invalid_credentials` (401, одинаков для неверного пароля и неизвестного email), `refresh_reused` (401, повторное использование refresh — вся семья отозвана, cookie сбрасывается), `unauthorized` (401), `rate_limited` (429), `forbidden_origin` (403, `Origin` не из `ALLOWED_ORIGINS` на `/auth/refresh` и `/auth/logout`). Саморегистрация — только `candidate` и `employer`. `GET /me` пока возвращает `{id, email, role, consents[]}` (`consents` — типы действующих согласий).

`GET /me/consents` → массив по всем `consent_type`: `{type, required, granted, version, current_version, granted_at}`. `PUT /me/consents` `{consents:[{type, granted, version?}]}` → тот же массив; идемпотентно. Выдача с устаревшей `version` → 409 `consent_version_mismatch`. Эндпоинты, требующие согласия, отвечают 403 `consent_required` (зависимость `require_consent(type)`).

### 2.2. Кандидат: профиль

| Метод и путь | Назначение |
|---|---|
| `GET /candidates/me/profile` | Полный профиль владельца: `CandidateProfile` |
| `PATCH /candidates/me/preferences` | `{salary_min, formats, employment_types, city, relocation, search_status}`. `search_status=active` выставляет `active_until=+7д` |
| `PATCH /candidates/me/visibility` | `{companies, education, repos, public_profile}` |
| `PUT /candidates/me/stoplist` | `{company_ids[]}` |
| `POST /candidates/me/resumes` | multipart `file` → `202 {resume_id, job_id}` |
| `GET /candidates/me/resumes/{id}` | `{status, parsed: ParsedResume, error}` |
| `POST /candidates/me/resumes/{id}/confirm` | `{edits: ParsedResumeEdits}` → профиль пересчитывается |
| `GET /candidates/me/skills` | `SkillWithTrust[]` |
| `POST /candidates/me/skills` | `{skill_id}` — заявить навык самому (`source=self`) |
| `DELETE /candidates/me/skills/{skill_id}` | Убрать свой `self`/`resume` навык (доказательства ФСП/кода/тестов не удаляются) |
| `GET /candidates/me/skills/{skill_id}/evidence` | `Evidence[]` — «откуда взялся навык» |
| `GET /candidates/me/category` | `CategoryExplanation`: роли, грейд, разбивка, уверенность, как подняться |
| `POST /candidates/me/category/dispute` | `{claimed_role, claimed_grade, comment}` |
| `POST /candidates/me/fsp/link` | `{participant_id? , email?}` → `{method: "code"|"manual", masked_contact?}` |
| `POST /candidates/me/fsp/verify` | `{code}` |
| `POST /candidates/me/fsp/sync` | `202` — ручное обновление (не чаще раза в 10 минут) |
| `GET /candidates/me/fsp` | `{link, achievements: FspAchievement[], ranks, teams}` |
| `POST /candidates/me/github` | `{login}` → `202 {analysis_id}` |
| `GET /candidates/me/code-analysis` | Последний `CodeAnalysis` |
| `GET /candidates/me/navigator` | `Navigator` |
| `GET /candidates/me/uplift` | `Uplift` — какой навык подтвердить, чтобы подходить под N% больше вакансий ([matching.md §6](matching.md#6-uplift-для-кандидата-какой-навык-добавить)) |
| `GET /candidates/me/graph?skills=top|all&vacancy_id=` | `Subgraph` — граф доказательств для визуализации ([graph.md §6](graph.md#6-api-подграфа)) |
| `POST /candidates/me/navigator/clicks` | `{competition_id, skill_id}` — учёт переходов на соревнования |
| `GET /candidates/me/views` | `{total_30d, companies_30d, by_day[]}` |
| `GET /candidates/me/offers` | `OfferForCandidate[]` |
| `DELETE /candidates/me` | Удаление профиля (F13) |

Реализовано (E3-1): `GET /candidates/me/profile`, `PATCH /candidates/me/preferences`, `PATCH /candidates/me/visibility`, `PUT /candidates/me/stoplist`. Только роль `candidate` (иначе 403). Анкета создаётся лениво при первом обращении. Запись требует согласие `pd_processing` (403 `consent_required`); `visibility.public_profile=true` — ещё и `public_profile`. `PATCH` частичный (`null` очищает `salary_min`/`city`), `visibility` дополнительно содержит `teams` (по умолчанию `true`). Ответ `PATCH` и `GET profile` — пока заготовка `CandidateProfile` без категории, грейда и навыков (`skills: []`, `category/grade: null`); их добавляют E3-2, E4-x. `PUT stoplist` `{company_ids[]}` (до 200 UUID, дубли схлопываются) возвращает сохранённый список; существование компаний пока не проверяется (появится с E6-1). `active` без продления через 7 дней отдаётся как `open`.

### 2.3. Проверка навыков

| Метод и путь | Роль | Назначение |
|---|---|---|
| `GET /assessment/skills` | C | Навыки с банком вопросов + когда можно пересдать |
| `POST /assessment/tests` | C | `{skill_id}` → `{session_id, question: TestQuestion, progress}` |
| `POST /assessment/tests/{id}/answer` | C | `{question_id, option_id}` → `{next_question?: TestQuestion, result?: TestResult}` |
| `POST /assessment/interviews` | C | `{repo_id?}` → `202 {interview_id}` |
| `GET /assessment/interviews/{id}` | C | `{status, questions[], grades?}` |
| `POST /assessment/interviews/{id}/answers` | C | `{question_id, text}` |

### 2.4. Офферы (обе стороны)

| Метод и путь | Роль | Назначение |
|---|---|---|
| `POST /offers/salary-hint` | E | `{vacancy_id, candidate_id, salary_from, salary_to}` → `SalaryHint` (с `p_accept` и `range_too_wide`) |
| `POST /vacancies/{id}/candidates/{pseudo_id}/interview-kit` | E | `202` → вопросы для структурированного интервью ([ml.md §10.1](ml.md#101-вопросы-для-структурированного-интервью)); `GET` того же пути — результат |
| `POST /candidates/{pseudo_id}/skill-requests` | E | Минимальная версия «попросить подтвердить навык»: `{skill}` → кандидату в бот приходит ссылка на тест, компании — уведомление о результате |
| `POST /offers` | E | `CreateOffer` + `Idempotency-Key` → `201 Offer` |
| `GET /offers?status=&vacancy_id=` | E | Офферы компании |
| `GET /offers/{id}` | C, E | Оффер. Для кандидата первое открытие переводит `sent → viewed` |
| `POST /offers/{id}/accept` | C | → `accepted`, раскрытие контактов |
| `POST /offers/{id}/decline` | C | `{reason, comment?}` |
| `POST /offers/{id}/withdraw` | E | Только из `sent/viewed` |
| `POST /offers/{id}/status` | E | `{status: interview|hired|not_hired}` |
| `GET /offers/{id}/messages`, `POST /offers/{id}/messages` | C, E | Переписка по офферу |
| `GET /offers/{id}/contacts` | E | Контакты кандидата, только если `accepted` и дальше |
| `POST /offers/{id}/complaint` | C | `{reason, comment}` |
| `POST /team-offers` | E | 🚀 `{vacancy_id, fsp_team_id, salary_per_member[]}` |

### 2.5. Работодатель

| Метод и путь | Роль | Назначение |
|---|---|---|
| `POST /companies` | E | Регистрация компании → `pending` |
| `GET /companies/me`, `PATCH /companies/me` | E / EA | Профиль компании, рейтинг ответственности |
| `POST /companies/me/members` | EA | Приглашение по email |
| `GET /market/map?metric=candidates|median_salary|fsp_share|verified_share&formats=` | E | `MarketCell[]` |
| `GET /market/skills?role=` | E | 🚀 Граф навыков рынка |
| `POST /search/parse` | E | `{text}` → `ParsedQuery` |
| `POST /search/candidates` | E | `{filters: SearchFilters, sort: match|trust|fresh, cursor, vacancy_id?, session_id?}` → `Page<CandidateCard>` + `session_id`; пишет показы |
| `GET /candidates/{pseudo_id}/card?vacancy_id=` | E | `CandidateCardFull` (пишет просмотр) |
| `POST /vacancies` / `GET /vacancies` / `GET|PATCH|DELETE /vacancies/{id}` | E | CRUD. В теле: роль, грейды, навыки (обязательный, мин. уровень, вес), формат, вилка, `important_qualities` (командные качества, удваивают их вес в подборе) |
| `POST /vacancies/{id}/publish`, `POST /vacancies/{id}/close` | E | Публикация и закрытие |
| `POST /vacancies/from-query` | E | `{parsed_query}` → черновик вакансии |
| `GET /vacancies/{id}/matches?min_trust=&fsp_only=&cursor=` | E | `Page<MatchItem>` + `session_id`; пишет показы |
| `GET /candidates/{pseudo_id}/similar` | E | Похожие кандидаты |
| `GET /candidates/{pseudo_id}/graph?vacancy_id=` | E | Анонимный подграф, подсветка путей под требования вакансии |
| `POST /recs/feedback` | E | `{session_id, candidate_pseudo_id, event: open|dwell|shortlist|dismiss, reason?}` |
| `GET /recs/sessions/{id}`, `DELETE /recs/sessions/{id}` | E | Учтённые подстройки (чипсы «Учли: …») / сброс |
| `GET /teams?discipline=&min_place=` | E | 🚀 Команды ФСП, где есть кандидаты платформы |
| `GET|POST|DELETE /saved-searches` | E | Подписки на категорию |

Реализовано (E6-1): `POST /companies` (роль `employer`, одна компания на пользователя, иначе 409 `company_exists`; создатель — `admin`, статус `pending`), `GET|PATCH /companies/me` (PATCH только `admin` компании, 403 иначе; поля `name`, `inn`, `site`, `description`; `status` и `responsibility_score` через PATCH не меняются), `POST /companies/me/members` `{email, role}` (только `admin`; пользователь с ролью `employer` должен быть уже зарегистрирован, иначе 404 `user_not_found`; состоит в другой компании — 409 `already_member`). Модерация: `GET /admin/companies?status=`, `POST /admin/companies/{id}/verify|reject` (роль `fsp_admin`; verify из `pending|rejected`, reject из `pending|verified`, повтор того же решения идемпотентен, `blocked` через эти эндпоинты не меняется — 409 `invalid_status`). `GET /me` для работодателя возвращает `company: {id, name, status, role}`. Ограничение по `verified` для офферов и вакансий добавят E6-2 и E9-x; `company_id` в JWT пока не кладётся, компания определяется по `company_members`.

Реализовано (E6-2): `POST|GET /vacancies`, `GET|PATCH|DELETE /vacancies/{id}`, `POST /vacancies/{id}/publish|close` (роль `employer`, доступ участникам компании-владельца, чужая или несуществующая вакансия → 404 `vacancy_not_found`; нет компании → 404 `company_not_found`). Тело: `title, role, grade_min, grade_max, formats[], employment_type, city?, salary_from, salary_to, description?, important_qualities[], skills[{slug, required=true, min_level=2 (1–4), weight=1.0 (0–3]}]`; slug синонима-слияния приводится к живому навыку, неизвестный или `rejected` — 422 `unknown_skill`, повтор — 422 `duplicate_skill`; `grade_min > grade_max` — 422 `invalid_grade_range`, `salary_to < salary_from` — 422 `invalid_salary_range`. В ответе есть `range_too_wide` (`salary_to / salary_from > 1.6`, предупреждение, не блокирует). Статусы: `draft → published → closed`; `PATCH` (поля и/или полный список `skills`) — только `draft|published`, иначе 409 `invalid_status`; `DELETE` — только черновик (204), иначе 409. `publish`: только `verified` компания (иначе 403 `company_not_verified`) и минимум один обязательный навык (иначе 422 `no_required_skills`); повторные `publish` и `close` идемпотентны. `version` растёт на каждое изменение и на смену статуса; в outbox уходят `vacancy.published` (при публикации), `vacancy.updated` (правка опубликованной), `vacancy.closed`, всё `{vacancy_id, version}`. `POST /vacancies/from-query` и `embedding` — позже (E7-x, E10-x).

### 2.6. Администратор ФСП

| Метод и путь | Назначение |
|---|---|
| `GET|POST|PATCH /admin/skills`, `…/aliases`, `…/relations` | Граф навыков: вершины, синонимы, связи |
| `GET /admin/skills/queue` | Спорные решения конвейера: предложенные слияния, новые вершины с низкой уверенностью |
| `POST /admin/skills/{id}/approve|reject`, `POST /admin/skills/merge {from, into}`, `POST /admin/skills/merges/{id}/revert` | Решения админа по графу навыков |
| `GET|POST|DELETE /admin/skills/distinct`, `GET|POST|DELETE /admin/skills/blocklist` | «Точно разные» пары и стоп-лист |
| `GET /admin/skills/growth` | Рост графа: новые вершины и связи за период, доля автоматических решений |
| `GET /admin/discipline-rules/suggestions` | Предложения добавить навык в правило дисциплины (lift по участникам) |
| `GET|PUT /admin/discipline-rules` | Правила «дисциплина → навыки» |
| `GET|PUT /admin/scoring-config` | Веса доверия, грейда, матчинга (с версией) |
| `GET /admin/companies?status=pending`, `POST /admin/companies/{id}/verify|reject` | Модерация компаний |
| `GET /admin/complaints`, `POST /admin/complaints/{id}/resolve` | Жалобы |
| `GET /admin/dashboard` | Воронка ФСП → профиль → оффер → найм, востребованные навыки, регионы, переходы на соревнования |
| `GET /admin/quality`, `GET /admin/quality/{run_id}` | Страница качества (eval_runs) |
| `POST /admin/quality/runs` | Загрузка результата `make eval` (роль A или сервисный токен) |
| `GET /admin/quality/fairness` | Панель справедливости: impact ratio по группам (синтетика + демо-показы) |
| `GET|POST /admin/live-runs`, `GET /admin/live-runs/{id}` | Живые прогоны: создать приглашение, результаты (задания, время, SUS) |
| `GET /run/{token}`, `POST /run/{token}/sus` | Для испытателя: старт прогона, анкета SUS |
| `GET /admin/health` | SLO, очереди, DLQ, GPU (блок «Здоровье») |
| `POST /admin/demo/fsp-result` | Демо: создать результат в моке → вебхук (F11) |
| `POST /admin/demo/reset` | Только при `DEMO_MODE=true`: сброс к снапшоту |

### 2.7. Публичные

| Метод и путь | Назначение |
|---|---|
| `GET /public/stats` | Счётчики для лендинга: кандидатов, с ФСП, компаний, офферов |
| `GET /public/badge/{slug}.svg` | Бейдж «Подтверждено ФСП · Middle Backend · ●●●●». Кеш 1 ч |
| `GET /public/credentials/{id}` | **Open Badge 3.0** (W3C Verifiable Credential, JSON-LD, подпись Ed25519 `eddsa-rdfc-2022`): достижение «Подтверждено ФСП» с навыками ●●●● и фактами-основаниями |
| `GET /public/credentials/{id}/verify` | Проверка подписи и отзыва (для работодателя вне платформы) |
| `GET /.well-known/did.json` | Публичный ключ издателя (`did:web:fsp.patissons.tech`) |
| `POST /track` | Батч событий интерфейса (до 50), см. [metrics.md](metrics.md) |
| `GET /public/profiles/{slug}` | Публичный профиль (если кандидат включил) |
| `GET /athlete/{slug}` | Краулерам (Telegram, VK, Slack по User-Agent) — HTML с OG-тегами, людям — редирект на `dashboard.fsp…/athlete/{slug}` |
| `GET /taxonomy` | `{version, skills[{slug,name,kind,group,testable}], roles[{slug,name}], disciplines[{slug,name}], grades[], formats[], employment_types[]}` (только `active` навыки). `ETag` `W/"tax-<version>-<хеш статики>"`, `If-None-Match` → 304, `Cache-Control: public, max-age=300` |
| `POST /integrations/fsp/webhook` | Вебхук ФСП/мока (HMAC `X-Signature`) |
| `GET /healthz`, `GET /readyz` | Проверки живости и готовности |

### 2.8. Realtime

`GET /events/stream` — SSE. Внутри: core-worker и ml-worker публикуют в RabbitMQ `ui.user.<id>`, core-api держит соединения и раздаёт ([messaging.md](messaging.md)). Аутентификация: access-токен в query (`?access_token=`, короткоживущий), заголовок `Authorization: Bearer` или cookie `access_token`; токен проверяется при подключении (нет или недействителен → 401 `unauthorized`). Соединение получает только сообщения своего `user_id`; повторной отправки пропущенного по `Last-Event-ID` нет — после переподключения фронт перечитывает данные запросами. Очередь соединения — 100 сообщений, при переполнении вытесняется старое. Сервер шлёт `event: <type>\ndata: <json>\nid: <seq>`, heartbeat — каждые 20 с. Типы событий: [§4](#4-sse-события).

### 2.9. Internal (для bot и сервисов)

| Метод и путь | Кто вызывает | Назначение |
|---|---|---|
| `POST /internal/tg/start` | bot | `{tg_user_id, chat_id, username, start_param?}` → `{user_id, role, missing_consents[], linked: bool}` |
| `POST /internal/tg/consents` | bot | `{tg_user_id, types[]}` |
| `POST /internal/tg/link` | bot | `{tg_user_id, token}` — привязка по deep link |
| `POST /internal/auth/magic-link` | bot | `{tg_user_id, redirect}` → `{url}` |
| `POST /internal/tg/resumes` | bot | multipart `file` + `tg_user_id` → `202` |
| `POST /internal/tg/resumes/{id}/confirm` | bot | Подтверждение без правок |
| `GET /internal/tg/profile?tg_user_id=` | bot | Краткий профиль для сообщения |
| `POST /internal/tg/fsp/link`, `…/verify` | bot | Привязка ФСП из бота |
| `POST /internal/tg/github` | bot | `{tg_user_id, login}` |
| `POST /internal/tg/offers/{id}/view|accept|decline|messages` | bot | Действия по офферу от имени `tg_user_id` |
| `POST /internal/tg/tests`, `…/{id}/answer` | bot | Адаптивный тест |
| `GET /internal/tg/navigator?tg_user_id=` | bot | Навигатор кратко |
| `PATCH /internal/tg/status` | bot | Статус поиска |
| `GET /internal/taxonomy/snapshot` | ml | `Authorization: Service <SERVICE_TOKEN_ML>` (пустой токен = закрыто, иначе 401). `{version, skills[{id,slug,name,kind,group,status,testable,description,aliases[]}], adjacent[{a,b,weight}], parent[{child,parent,weight}], distinct[[a,b]], roles[{slug,name,skills{}}], disciplines[{slug,name,rules[{skill,weight,track}]}]}`; вершины `active` и `provisional`, кеш Redis `c:tax:{version}` |

**Internal fsp-connector** (вызывает core-api):

| Метод и путь | Назначение |
|---|---|
| `GET /internal/oauth/authorize-url?state=&code_challenge=` | `{url}` — страница «Войти через ФСП» (PKCE S256; state и verifier хранит core) |
| `POST /internal/oauth/exchange` | `{code, code_verifier, candidate_id}` → `{participant_id, verified: true}` + событие `fsp.linked` (`method=oauth`); код одноразовый, повтор → 502 `fsp_auth_error` |
| `POST /internal/links` | `{candidate_id, participant_id?, email?, manual?}` → `{method: code|manual, masked_contact?}`. Есть контакт в ФСП → отправляет код (`s:fspcode:{cid}`, TTL 10 мин), привязки ещё нет; контакта нет или `manual=true` → сразу `fsp_links(manual, verified=false)` + `fsp.linked`. Ошибки: 404 `fsp_not_found`, 409 `fsp_already_linked` (+ запись в `fsp_link_conflicts`), 409 `candidate_already_linked`, 409 `fsp_ambiguous` |
| `POST /internal/links/verify` | `{candidate_id, code}` → `{verified}`; верный код → `fsp_links(code, verified=true)` + `fsp.linked`; 5 неверных попыток → 429 `too_many_attempts`, нет ожидающего кода → 410 `code_expired` |
| `GET /internal/competitions?from=&to=` | Календарь (для навигатора, если копия в core устарела) |
| `POST /integrations/fsp/webhook` | Публичный, вебхук ФСП/мока (HMAC) — маршрутизируется edge'ем сюда |

### 2.10. ml-api (внутренний, вызывает только core)

| Метод и путь | Вход | Выход |
|---|---|---|
| `POST /v1/query/parse` | `{text, rule_hint?: SearchFilters, taxonomy_version}` | `ParsedQuery` |
| `POST /v1/embeddings` | `{texts[], kind: "query"|"passage"}` | `{model, dim, vectors[][]}` |
| `POST /v1/skills/resolve` | `{mentions: [{raw, context}], taxonomy_version}` (до 50) | `[{raw, norm, decision: alias|fuzzy|new|same_pending|rejected, skill_slug?, kind: hard|soft|domain|not_skill, relation?: {type, to_slug, confidence}, reason?}]` ([skills.md §3](skills.md#3-конвейер-для-нового-упоминания)) |
| `GET /healthz` | — | `{llm: up|down, embedder: up|down, model, queue_depth}` |

## 3. Ключевые схемы (TypeScript-нотация)

```ts
type TrustLevel = 0 | 1 | 2 | 3 | 4;           // ○○○○ … ●●●●
type EvidenceSource = "self" | "resume" | "github" | "test" | "ai_interview" | "fsp" | "codeforces";

interface SkillWithTrust {
  skill: { slug: string; name: string; group: string };
  confidence: number;               // 0..1
  level: TrustLevel;
  sources: EvidenceSource[];
  claimed_only: boolean;            // только self/resume — «заявлено»
  status: "active" | "provisional";  // provisional — «новый навык», слабое доверие
  derived_from?: string;            // выведено по иерархии из навыка slug
  top_evidence: EvidenceBrief[];    // до 3
}

interface EvidenceBrief {
  id: string;
  source: EvidenceSource;
  strength: number;
  observed_at: string;              // дата факта
  title: string;                    // «Призёр Кубка России по продуктовому программированию, 2 место из 120, капитан»
  verified: boolean;
}

interface GradeInfo {
  grade: Grade; score: number; confidence: number; preliminary: boolean;
  breakdown: { signal: string; label: string; points: number; evidence_ids: string[] }[];
  next_grade?: { grade: Grade; points_needed: number; hints: string[] };
}

interface CandidateProfile {
  pseudonym: string; profile_version: number;
  search_status: "active" | "open" | "dnd"; active_until?: string;
  preferences: { salary_min?: number; formats: WorkFormat[]; employment_types: EmploymentType[]; city?: string; relocation: boolean };
  visibility: { companies: boolean; education: boolean; repos: boolean; public_profile: boolean };
  category: { primary_role: RoleSlug; roles: { role: RoleSlug; weight: number }[]; primary_stack: string[] };
  grade: GradeInfo;
  skills: SkillWithTrust[];
  team_signals: TeamSignal[];       // лидерство, командная работа, результативность, рост — только из фактов
  claimed_soft: string[];           // «указано в резюме», в расчётах не участвует
  fsp?: { verified: boolean; achievements: FspAchievement[]; ranks: { discipline: string; rank: string }[] };
  code?: { radar: Record<"backend"|"frontend"|"devops"|"data"|"quality"|"open_source", number>; languages: { lang: string; share: number }[]; flags: string[]; analyzed_at: string };
  experience: { title: string; company?: string; start: string; end?: string; skills: string[] }[];
  completeness: { resume: boolean; fsp: boolean; github: boolean; tests: number; score: number }; // для онбординга
}

// Работодатель видит только это до принятия оффера
interface CandidateCard {
  pseudo_id: string;               // стабильный, не равен user_id
  pseudonym: string;               // «Backend #4821»
  avatar_seed: string;             // для генеративного аватара-созвездия
  primary_role: RoleSlug; grade: Grade; grade_preliminary: boolean;
  primary_stack: string[];
  top_skills: { slug: string; name: string; level: TrustLevel; sources: EvidenceSource[] }[]; // до 8
  fsp_highlights: { title: string; level: string; place?: number; of?: number; year: number }[]; // до 3
  salary_min?: number; formats: WorkFormat[]; city?: string; relocation: boolean;
  search_status: "active" | "open";
  match?: { score: number; explanation: ExplanationItem[] };
  updated_at: string;
}

interface CandidateCardFull extends CandidateCard {
  skills: SkillWithTrust[];
  grade_info: GradeInfo;
  code?: CandidateProfile["code"];       // без ссылок на репозитории, если visibility.repos = false
  experience: { title: string; company?: string; months: number; skills: string[] }[]; // company — только если разрешено
  offers_from_you: { id: string; status: OfferStatus }[];
}

interface ExplanationItem {
  kind: "plus" | "minus" | "warn";
  code: "skill_confirmed" | "skill_adjacent" | "skill_missing" | "skill_claimed_only" | "fsp_achievement"
      | "salary_fit" | "salary_below_min" | "grade_fit" | "grade_mismatch" | "format_fit" | "active_search"
      | "team_signal" | "semantic_only";
  text: string;                    // «FastAPI, PostgreSQL — подтверждено кодом (●●●○) и тестом»
  skill?: string;
  evidence_ids: string[];          // каждое утверждение ссылается на доказательство
  weight: number;                  // вклад в score
}

interface SearchFilters {
  roles?: RoleSlug[]; grade_min?: Grade; grade_max?: Grade;
  skills_must?: { slug: string; min_level?: TrustLevel }[];
  skills_nice?: string[];
  formats?: WorkFormat[]; employment_types?: EmploymentType[];
  salary_max?: number;             // бюджет работодателя: кандидаты с salary_min ≤ salary_max
  cities?: string[]; relocation_ok?: boolean;
  min_trust?: TrustLevel;          // минимальный уровень по обязательным навыкам
  fsp_only?: boolean; fsp_disciplines?: string[];
  active_only?: boolean;
  semantic_text?: string;          // смысловой остаток запроса для эмбеддинга («высоконагруженный API»)
}

interface ParsedQuery {
  filters: SearchFilters;
  chips: { key: keyof SearchFilters; value: unknown; label: string; source: "rule" | "llm"; confidence: number }[];
  unparsed: string[];
  refining: boolean;               // LLM ещё не ответила — будут уточнения
}

interface MarketCell { role: RoleSlug; grade: Grade; candidates: number; median_salary: number | null; fsp_share: number; verified_share: number; active_share: number }

interface CreateOffer { vacancy_id: string; candidate_pseudo_id: string; salary_from: number; salary_to: number; message?: string }

interface Offer {
  id: string; status: OfferStatus; created_at: string; expires_at: string;
  vacancy: { id: string; title: string; role: RoleSlug; grade_min: Grade; grade_max: Grade; formats: WorkFormat[] };
  salary_from: number; salary_to: number; message?: string;
  below_candidate_min: boolean;
  match_snapshot?: { score: number; explanation: ExplanationItem[] };
  decline?: { reason: DeclineReason; comment?: string };
  awaiting_reply_from?: "candidate" | "company";
}
interface OfferForCandidate extends Offer { company: { id: string; name: string; logo_url?: string; responsibility_score?: number; verified: boolean } }
interface OfferForCompany extends Offer { candidate: CandidateCard; contacts?: { name: string; email?: string; phone?: string; telegram?: string } }

interface SalaryHint {
  candidate_min?: number; below_candidate_min: boolean;
  category_median?: number; vs_category_median: number;   // −0.18 = ниже на 18%
  p_accept: number;                                       // взаимный подбор, 0..1
  acceptance_hint: "low" | "medium" | "high";
  range_too_wide: boolean;                                // salary_to / salary_from > 1.6
  message: string;
}

interface TeamSignal {
  signal: "leadership" | "teamwork" | "results" | "growth";
  value: number;                    // 0..1
  label: "strong" | "present";      // ≥ 0.6 «сильное подтверждение», 0.3–0.6 «есть подтверждение»
  facts: { fact_id: string; title: string }[];   // «Капитан, Кубок России 2025, финал, 2 место»
}

interface Uplift {
  relevant_total: number;           // релевантные открытые вакансии
  base: number;                     // подходит сейчас
  items: {
    skill: string; name: string; current_level: TrustLevel;
    extra: number; pct: number;     // +9 вакансий, +0.64
    median_salary_delta: number;
    how_to_confirm: ({ kind: "test"; minutes: number } | { kind: "github" } |
                     { kind: "fsp_competition"; id: string; title: string; start_date: string; registration_url?: string })[];
  }[];
  combo?: { skills: string[]; extra: number; pct: number };
}

interface Navigator {
  target: { role: RoleSlug; grade: Grade };
  next_grade: { points_needed: number; hints: string[] };
  uplift: Uplift["items"];          // топ-3
}

interface Subgraph {                // graph.md §6
  profile_version: number;
  nodes: { id: string; type: "candidate" | "skill" | "fsp_result" | "repo" | "test" | "interview" | "experience" | "competition" | "team";
           label: string; level?: TrustLevel; confidence?: number; date?: string; verified?: boolean; derived_from?: string; ghost?: boolean }[];
  edges: { from: string; to: string; type: "has_fact" | "confirms" | "owns" | "adjacent" | "parent" | "at" | "member_of";
           strength?: number; weight?: number; evidence_id?: string }[];
  highlight?: { requirement: string; path: string[] }[];
}

interface TestQuestion { id: string; text: string; code?: string; options: { id: string; text: string }[]; time_limit_sec: number; index: number; max: number }
interface TestResult { skill: string; theta: number; se: number; level_before: TrustLevel; level_after: TrustLevel; questions: number }

interface FspAchievement { competition: { id: string; title: string; discipline: string; level: string; date: string }; stage: string; place?: number; of?: number; team?: { id: string; name: string; role: string }; skills: { slug: string; strength: number }[] }

interface ParsedResume {
  parser_version: string;
  person: { full_name?: string; email?: string; phone?: string; telegram?: string; city?: string; links: string[] };
  summary?: string;
  experience: { company?: string; title?: string; start?: string; end?: string | null; description?: string; skills: string[]; is_commercial: boolean }[];
  education: { institution?: string; degree?: string; field?: string; year_end?: number }[];
  skills: { raw: string; slug?: string; quote: string; method: string; confidence: number }[];
  unknown_skills: string[];
  total_experience_months: number;
  warnings: string[];              // «не нашёл даты в опыте №2»
}
```

## 4. SSE-события

| `event` | Кому | `data` |
|---|---|---|
| `job.progress` | владельцу задачи | `{job_id, kind: resume|code|interview|fsp_sync, stage, pct, message}` |
| `resume.parsed` / `resume.failed` | C | `{resume_id, reason?}` |
| `fsp.imported` | C | `{new_achievements: FspAchievement[]}` |
| `code.analysis.completed` | C | `{analysis_id}` |
| `profile.updated` | C | `{profile_version, diff: {skills_up: [{slug, from, to}], skills_new: [...], grade?: {from, to}, category?: {from, to}}}` |
| `offer.created` | C | `{offer_id}` |
| `offer.updated` | C, E | `{offer_id, status, awaiting_reply_from}` |
| `offer.message` | C, E | `{offer_id, message_id}` |
| `matches.ready` | E | `{vacancy_id, count}` |
| `matches.rationale_ready` | E | `{vacancy_id, candidate_pseudo_ids[]}` |
| `notification.new` | все | `{id, type, title}` |

## 5. Сообщения бота (callback_data)

Ограничение Telegram — 64 байта. Формат `<домен>:<действие>:<id>[:<арг>]`:

| callback_data | Действие |
|---|---|
| `c:ok` / `c:no` | Согласия |
| `r:ok:<resume_id>` | Подтвердить разбор резюме |
| `o:v:<offer_id>` / `o:a:<offer_id>` / `o:d:<offer_id>` / `o:q:<offer_id>` | Подробнее / принять / отклонить / вопрос |
| `o:r:<offer_id>:<reason>` | Причина отказа (`ls`, `ws`, `wf`, `wg`, `nl`, `ot`) |
| `t:s:<skill_slug>` | Начать тест |
| `t:a:<session_id>:<question_idx>:<option_id>` | Ответ теста (~45 байт; индекс вопроса защищает от нажатия старой кнопки) |
| `s:<active|open|dnd>` | Статус поиска |

Подробно: [telegram.md](telegram.md).
