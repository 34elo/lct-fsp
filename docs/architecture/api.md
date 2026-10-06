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
| Идемпотентность | `Idempotency-Key` обязателен для `POST /offers`, `POST /team-offers`. Повторный ключ возвращает исходный ответ (ключ хранится в `offers.idempotency_key`, уникален в паре с компанией; заголовок `Idempotent-Replay: true` на повторе) |
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
| `POST /auth/telegram` | P | Поля Telegram Login Widget как есть (`id`, `auth_date`, `hash`, …) → `{access_token, user}` + cookie. Подпись HMAC и `auth_date` ≤ 24 ч; нового пользователя создаёт кандидатом без email. Ошибки: `401 invalid_telegram_auth`, `401 telegram_auth_expired`, `503 telegram_login_disabled` (нет токена бота) |
| `POST /auth/magic` | P | `{token}` из ссылки бота → `{access_token, user}` + cookie. Токен одноразовый (5 мин); иначе `401 invalid_magic_token` |
| `GET /auth/fsp/start` | P/C | Редирект на OAuth ФСП (мок). Для вошедшего кандидата это привязка, иначе вход |
| `GET /auth/fsp/callback` | P/C | Обмен кода → `fsp_links` → `fsp_sync` |
| `GET /me` | любая | `{user, role, candidate?, company?, consents, telegram_linked}` |
| `GET /me/consents`, `PUT /me/consents` | любая | Список и выдача/отзыв согласий |
| `POST /me/telegram/link` | C, E | → `{deep_link}` вида `https://t.me/<bot>?start=link_<token>` (токен 15 мин, одноразовый); `503 telegram_disabled`, если имя бота не задано |

Коды ошибок `/auth/*`: `email_taken` (409), `invalid_credentials` (401, одинаков для неверного пароля и неизвестного email), `refresh_reused` (401, повторное использование refresh — вся семья отозвана, cookie сбрасывается), `unauthorized` (401), `rate_limited` (429), `forbidden_origin` (403, `Origin` не из `ALLOWED_ORIGINS` на `/auth/refresh` и `/auth/logout`). Саморегистрация — только `candidate` и `employer`. `GET /me` пока возвращает `{id, email, role, consents[]}` (`consents` — типы действующих согласий).

`GET /me/consents` → массив по всем `consent_type`: `{type, required, granted, version, current_version, granted_at}`. `PUT /me/consents` `{consents:[{type, granted, version?}]}` → тот же массив; идемпотентно. Выдача с устаревшей `version` → 409 `consent_version_mismatch`. Эндпоинты, требующие согласия, отвечают 403 `consent_required` (зависимость `require_consent(type)`).

### 2.2. Кандидат: профиль

| Метод и путь | Назначение |
|---|---|
| `GET /candidates/me/profile` | Полный профиль владельца: `CandidateProfile` |
| `PATCH /candidates/me/preferences` | `{salary_min, formats, employment_types, city, relocation, search_status}`. `search_status=active` выставляет `active_until=+7д` |
| `PATCH /candidates/me/visibility` | `{companies, education, repos, public_profile}` |
| `PUT /candidates/me/stoplist` | `{company_ids[]}` |
| `POST /candidates/me/resumes` | multipart `file` (PDF/DOCX по сигнатуре, до 10 МБ; 10 в сутки) → `202 {resume_id, job_id}`. Ошибки: `413 file_too_large`, `415 unsupported_file_type`, `422 empty_file`, `429` |
| `GET /candidates/me/resumes/{id}` | `{status: queued|parsing|parsed|confirmed|failed, parsed: ParsedResume, error}`; чужое → 404 |
| `POST /candidates/me/resumes/{id}/confirm` | `{edits: ParsedResumeEdits}` → профиль пересчитывается. Повтор безвреден; до разбора `409 resume_not_parsed`; неизвестный `add_skills` → `422 unknown_skill` |
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
| `GET /candidates/me/offers?initiator=` | `OfferForCandidate[]` (приглашения и отклики; `initiator=employer|candidate` фильтрует) |
| `GET /candidates/me/applications` | `OfferForCandidate[]` — мои отклики (E20-3) |
| `POST /candidates/me/applications/{id}/withdraw` | Отозвать свой отклик из `sent/viewed`; приглашение или чужой оффер — 404 |
| `DELETE /candidates/me` | Удаление профиля (F13) |

Реализовано (E4-6): `GET /candidates/me/category` → `CategoryExplanation` `{primary_role, roles[{role, weight, score}], primary_stack, explanation[{skill, weight, confidence, level, sources, contribution}], grade: GradeInfo, dispute?}` (объяснение считается по `candidate_skills`, ml.md §4; `grade.next_grade.hints` — «как подняться»). `POST /candidates/me/category/dispute` `{claimed_role, claimed_grade, comment?≤2000}` (согласие `pd_processing`; неизвестная роль/грейд — 422) → 201 `{id, claimed_role, claimed_grade, comment, status: open, created_at}` в `category_disputes`, событие `category.disputed` в outbox (без комментария); пока есть неразобранное оспаривание — 409 `dispute_exists`. Разбор админом — позже (E12).

Реализовано (E3-1): `GET /candidates/me/profile`, `PATCH /candidates/me/preferences`, `PATCH /candidates/me/visibility`, `PUT /candidates/me/stoplist`. Только роль `candidate` (иначе 403). Анкета создаётся лениво при первом обращении. Запись требует согласие `pd_processing` (403 `consent_required`); `visibility.public_profile=true` — ещё и `public_profile`. `PATCH` частичный (`null` очищает `salary_min`/`city`), `visibility` дополнительно содержит `teams` (по умолчанию `true`). Ответ `PATCH` и `GET profile` (E4-7) — `CandidateProfile` с `category` (`null`, пока роль не определена), `grade` (`GradeInfo`; `preliminary` — уверенность ниже 0.5, подписи сигналов разбивки — по-русски), `skills` (`SkillWithTrust` с `top_evidence`), `team_signals` (только `value ≥ 0.3`, подпись `strong`/`present`, факты без ПДн) и `claimed_soft`; `fsp`, `code`, `completeness` пока не отдаются. `GET /candidates/me/skills/{skill_id}/evidence` — `EvidenceBrief[]` навыка владельца (свежие первыми; для выведенного по иерархии навыка — доказательства основания); `skill_id` принимает id или slug; навыка нет в профиле → 404 `skill_not_found`. `PUT stoplist` `{company_ids[]}` (до 200 UUID, дубли схлопываются) возвращает сохранённый список; существование компаний пока не проверяется (появится с E6-1). `active` без продления через 7 дней отдаётся как `open`.

Реализовано (E5-7): привязка ФСП для web (core → fsp-connector по HTTP, `SERVICE_TOKEN_CORE`, `FSP_CONNECTOR_URL`; ПДн в логи не пишутся, ошибки connector пробрасываются с тем же `code`). `GET /auth/fsp/start?next=/me&redirect=` — роль `candidate`; по умолчанию `200 {url}` (SPA делает `location.assign`), с `redirect=true` — `302` на страницу ФСП; PKCE и `state` в Redis `s:oauth:{state}` 10 мин, одноразовые; без токена 401 (с `redirect=true` — 302 на `/login?fsp=need_login`): анонимный вход через ФСП пока не поддержан, только привязка. `GET /auth/fsp/callback?code=&state=` — публичный, всегда `302` в SPA (`WEB_BASE_URL` + `next`) с `?fsp=linked` или `?fsp=error&reason=<code>`. `POST /candidates/me/fsp/link` `{participant_id?, email?, manual?}` (нужно одно из первых двух; 10/10 мин) и `/verify` `{code}` → `{verified}` — согласие `pd_processing`. `POST /candidates/me/fsp/sync` → 202, раз в 10 минут (429 `sync_too_often`), без привязки 409 `fsp_not_linked`, команда `fsp.sync(reason=manual)` через outbox. `GET /candidates/me/fsp` → `{link: {linked, verified, participant_id}, achievements, ranks, teams[{id,name,role}]}`; `link` берётся из копии `fsp_participants`, поэтому после `fsp.linked` появляется с задержкой воркера.

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
| `POST /offers/salary-hint` | E | `{vacancy_id, candidate_pseudo_id, salary_from, salary_to}` → `SalaryHint` (с `p_accept` и `range_too_wide`) |
| `POST /vacancies/{id}/candidates/{pseudo_id}/interview-kit` | E | `202` → вопросы для структурированного интервью ([ml.md §10.1](ml.md#101-вопросы-для-структурированного-интервью)); `GET` того же пути — результат |
| `POST /candidates/{pseudo_id}/skill-requests` | E | Минимальная версия «попросить подтвердить навык»: `{skill}` → кандидату в бот приходит ссылка на тест, компании — уведомление о результате |
| `POST /offers` | E | `CreateOffer` + `Idempotency-Key` → `201 Offer` |
| `GET /offers?status=&vacancy_id=&initiator=` | E | Офферы компании; `initiator=candidate` — отклики на её вакансии |
| `GET /offers/{id}` | C, E | Оффер. Для кандидата первое открытие переводит `sent → viewed` |
| `GET /vacancies/public?role=&city=&q=&limit=&offset=` | — | E20-3: опубликованные вакансии без авторизации (`PublicVacancyOut`: вилка, навыки, `company{id,name,verified,responsibility_score}`) |
| `POST /vacancies/{id}/apply` | C | E20-3: `{message?}` → `201 OfferForCandidate` с `initiator=candidate`; вилка — из вакансии, контакты кандидата раскрыты сразу |
| `POST /offers/{id}/accept` | C | → `accepted`, раскрытие контактов |
| `POST /offers/{id}/decline` | C | `{reason, comment?}` |
| `POST /offers/{id}/withdraw` | E | Только из `sent/viewed` |
| `POST /offers/{id}/status` | E | `{status: interview|hired|not_hired}` |
| `GET /offers/{id}/messages`, `POST /offers/{id}/messages` | C, E | Переписка по офферу |
| `GET /offers/{id}/events` | C, E | Таймлайн переходов: `[{id, from_status?, to_status, actor, created_at}]`, без payload |
| `GET /offers/{id}/contacts` | E | Контакты кандидата, только если `accepted` и дальше |
| `POST /offers/{id}/complaint` | C | `{reason, comment}` |
| `POST /team-offers` | E | `{vacancy_id, fsp_team_id, salary_per_member[{candidate_pseudo_id, salary_from, salary_to}], message?}` → `{team_offer_id, fsp_team_id, team_name, offers: OfferForCompany[]}` (E15-2) |

### 2.5. Работодатель

| Метод и путь | Роль | Назначение |
|---|---|---|
| `POST /companies` | E | Регистрация компании → `pending` |
| `GET /companies/me`, `PATCH /companies/me` | E / EA | Профиль компании, рейтинг ответственности |
| `POST /companies/me/members` | EA | Приглашение по email |
| `GET /market/map?metric=candidates|median_salary|fsp_share|verified_share&formats=` | E | `MarketCell[]` |
| `GET /market/skills?role=` | E | 🚀 Граф навыков рынка |
| `POST /search/parse` | E | `{text}` → `ParsedQuery` |
| `POST /search/candidates` | E | `{filters: SearchFilters, category?: CategoryRef, sort: match|trust|fresh|mutual, cursor, vacancy_id?, session_id?}` → `Page<CandidateCard>` + `session_id` + `tuning?` (`{active, signals, chips, hints}`, при своём `session_id` после ≥ 3 реакций выдача переставляется, matching.md §7); пишет показы |
| `GET /candidates/{pseudo_id}/card?vacancy_id=` | E | `CandidateCardFull` (пишет просмотр) |
| `POST /vacancies` / `GET /vacancies` / `GET|PATCH|DELETE /vacancies/{id}` | E | CRUD. В теле: роль, грейды, навыки (обязательный, мин. уровень, вес), формат, вилка, `important_qualities` (командные качества, удваивают их вес в подборе) |
| `POST /vacancies/{id}/publish`, `POST /vacancies/{id}/close` | E | Публикация и закрытие |
| `POST /vacancies/from-query` | E | `{parsed_query}` → черновик вакансии |
| `GET /vacancies/{id}/matches?min_trust=&fsp_only=&cursor=` | E | `Page<MatchItem>` + `session_id`; пишет показы |
| `GET /candidates/{pseudo_id}/similar?limit=` | E | `{items: CandidateCard + similarity, common_skills[], session_id}` (формула — matching.md §11); скрытая анкета — 404 `candidate_not_found`; пишет показы |
| `GET /candidates/{pseudo_id}/graph?vacancy_id=` | E | Анонимный подграф, подсветка путей под требования вакансии |
| `POST /recs/feedback` | E | `{session_id, candidate_pseudo_id, event: open|dwell|shortlist|dismiss, reason?}` → `{id, impression_id, event, created_at, tuning: SessionTuning}` (E17-4) |
| `GET /recs/sessions/{id}`, `DELETE /recs/sessions/{id}` | E | `SessionTuning {session_id, active, signals, min_signals, weights[{feature, start, current, change}], chips[{feature, text, change}], hints[{kind, reason, text, count}]}` — учтённые подстройки (чипсы «Учли: …», matching.md §7) / сброс → 204; чужая или несуществующая сессия — 404 `rec_session_not_found` |
| `GET /teams?discipline=&min_place=` | E | Команды ФСП, где есть ≥2 видимых кандидата платформы: `[{id, name, competition_title, discipline, best_place, members[{pseudo_id, role, primary_role, grade}]}]` (E15-2) |
| `GET|POST|DELETE /saved-searches` | E | Подписки на категорию |

Реализовано (E6-1): `POST /companies` (роль `employer`, одна компания на пользователя, иначе 409 `company_exists`; создатель — `admin`, статус `pending`), `GET|PATCH /companies/me` (PATCH только `admin` компании, 403 иначе; поля `name`, `inn`, `site`, `description`; `status` и `responsibility_score` через PATCH не меняются), `POST /companies/me/members` `{email, role}` (только `admin`; пользователь с ролью `employer` должен быть уже зарегистрирован, иначе 404 `user_not_found`; состоит в другой компании — 409 `already_member`). Модерация: `GET /admin/companies?status=`, `POST /admin/companies/{id}/verify|reject` (роль `fsp_admin`; verify из `pending|rejected`, reject из `pending|verified`, повтор того же решения идемпотентен, `blocked` через эти эндпоинты не меняется — 409 `invalid_status`). `GET /me` для работодателя возвращает `company: {id, name, status, role}`. Ограничение по `verified` для офферов и вакансий добавят E6-2 и E9-x; `company_id` в JWT пока не кладётся, компания определяется по `company_members`.

Реализовано (E20-12): `PATCH /companies/me` дополнительные поля `contacts` (`{name?, email?, phone?, telegram?}`) и `direction` (направление деятельности); обновляются в том же эндпоинте вместе с `name`, `inn`, `site`, `description`. Используются в приглашениях и профиле компании.

Реализовано (E6-2): `POST|GET /vacancies`, `GET|PATCH|DELETE /vacancies/{id}`, `POST /vacancies/{id}/publish|close` (роль `employer`, доступ участникам компании-владельца, чужая или несуществующая вакансия → 404 `vacancy_not_found`; нет компании → 404 `company_not_found`). Тело: `title, role, grade_min, grade_max, formats[], employment_type, city?, salary_from, salary_to, description?, important_qualities[], skills[{slug, required=true, min_level=2 (1–4), weight=1.0 (0–3]}]`; slug синонима-слияния приводится к живому навыку, неизвестный или `rejected` — 422 `unknown_skill`, повтор — 422 `duplicate_skill`; `grade_min > grade_max` — 422 `invalid_grade_range`, `salary_to < salary_from` — 422 `invalid_salary_range`. В ответе есть `range_too_wide` (`salary_to / salary_from > 1.6`, предупреждение, не блокирует). Статусы: `draft → published → closed`; `PATCH` (поля и/или полный список `skills`) — только `draft|published`, иначе 409 `invalid_status`; `DELETE` — только черновик (204), иначе 409. `publish`: только `verified` компания (иначе 403 `company_not_verified`) и минимум один обязательный навык (иначе 422 `no_required_skills`); повторные `publish` и `close` идемпотентны. `version` растёт на каждое изменение и на смену статуса; в outbox уходят `vacancy.published` (при публикации), `vacancy.updated` (правка опубликованной), `vacancy.closed`, всё `{vacancy_id, version}`. `POST /vacancies/from-query` и `embedding` — позже (E7-x, E10-x).

Реализовано (E7-3): `POST /search/candidates` (роль `employer`, нужна компания, иначе 404 `company_not_found`; `verified` не требуется). Тело: `{filters, sort=match, cursor, limit=20 (1–100), vacancy_id?, session_id?}`; ответ `{items: CandidateCard[], next_cursor, total, session_id}`. `vacancy_id` чужой или несуществующий — 404 `vacancy_not_found`. Фильтры: роль (`primary_role`), грейды (диапазон), форматы и типы занятости (пересечение), `salary_max` (кандидаты без вилки подходят), города (город совпал или кандидат готов к релокации), `relocation_ok`, `active_only`, `skills_must` с `min_level` и `min_trust` (уровень ≥ порога; неизвестный slug — пустая выдача), `fsp_only`, `fsp_disciplines`. Всегда скрыты: `dnd`, удалённые, анкеты без роли, кандидаты со стоп-листом этой компании. Сортировки: `trust` (среднее доверие по пяти сильнейшим навыкам), `fresh` (`updated_at`), `match` — с `vacancy_id` скор подбора (у кандидатов, не прошедших жёсткие фильтры вакансии, `match: null`, они идут в конце), без вакансии покрытие `skills_must`/`skills_nice` по доверию. Курсор непрозрачный (сортировка + ключ + `pseudo_id`), несовпавший или битый курсор — первая страница. `semantic_text` пока не используется. Страница кешируется на 60 с (messaging.md §6); `catalog_version` считается от числа живых анкет и максимального `updated_at`. `session_id` пока только генерируется (запись показов — E17-1). В `CandidateCard` нет `user_id`, имени, контактов, компаний и репозиториев.

Видимость v2 (E20-11, E23-1, blocks.md §4.5, ADR-018): в выдаче (поиск, подбор под вакансию, «похожие») и в `GET /candidates/{pseudo_id}/card` только кандидаты с **действующим грейдом из теста** (`assessment.service.get_grades_many`) и согласием `profile_publication`; иначе карточка — 404 `candidate_not_found`. Резюме без теста категории не даёт. Фильтр `category: {profession, grade}` (грейд `junior|middle|senior`, иначе 422) оставляет только участников категории (`category_members`). Карточка несёт `categories: CategoryRef[]` — подтверждённые тестом профессия × грейд. Ключ кеша выдачи включает отпечаток согласий и `category_counts`. Сила профиля (E23-2, assessment.md §9): карточка выдачи несёт `strength: {value, rank, top[{code T|F|S|R|C, text, value, weight}]}` (топ-3 слагаемых по вкладу); `rank = 0.6·match + 0.4·strength` считается и задаёт порядок только при фильтре `category` (без него `rank = null`, порядок прежний). Нет действующего грейда выбранной профессии — `strength = null`. Создание оффера по `pseudo_id` пока проверяет только базовую доступность анкеты (dnd, роль, стоп-лист).

Реализовано (E7-5): `POST /search/parse` (роль `employer`) `{text (1–500)}` → `ParsedQuery`; правила, затем LLM-уточнение через ml-api `/v1/query/parse` (E7-6, `ML_API_URL`, таймаут `QUERY_PARSE_TIMEOUT_SECONDS`=5): правила главнее (деньги, форматы, города, грейд, флаги), LLM добавляет роли, навыки из справочника и `semantic_text`, расхождения — чипс `?` (`source=llm`, `confidence=0.3`), `refining=true`; ответ кешируется в Redis `c:qparse:{tax_v}:{sha}` на 24 ч; недоступная или невалидная LLM — деградация до правил (`refining=false`), не ошибка. Код — `app/matching/query_llm.py`. Правила — `app/matching/query_parser.py`, справочник синонимов — `taxonomy.service.alias_index` (slug, название, синонимы живых навыков; неоднозначная форма отбрасывается). Распознаём: роль (`roles`; навык, чей slug совпал с ролью, становится ролью), грейд (`мидл`, `senior`, `джун+`, `senior+` = senior…lead, диапазон `middle-senior` / «от middle до senior» → `grade_min`/`grade_max`), навыки (`skills_must`; после «желательно» или перед «плюсом» — `skills_nice`), формат, тип занятости («стажёр» ставит ещё и `grade intern`), бюджет (`до 250к`, `200-250 тыс`, `до 1,5 млн`, `300000 ₽` → `salary_max`), город, `relocation_ok`, `active_only`, `fsp_only`. Фраза «от 150 000» фильтром не выражается и уходит в `unparsed`. Нераспознанные значимые слова — `semantic_text`. Чипсы атомарные: по одному на роль, навык, формат, город; `value` — одно значение (`"python"` для роли, `{slug}` для `skills_must`, строка для `skills_nice`, число для `salary_max`), `source=rule`, `confidence` 0.5–0.9.

Реализовано (E7-4): `GET /candidates/{pseudo_id}/card?vacancy_id=&source=` (роль `employer`, нужна компания) → `CandidateCardFull`: поля `CandidateCard` + `skills` (`SkillWithTrust`, до 3 кратких доказательств; заголовок — общий по источнику, для ФСП название соревнования, без ссылок и названий репозиториев), `grade_info`, `experience` (`months`; `company` только при `visibility.companies`; образования нет), `offers_from_you` (`{id, status}` офферов этой компании этому кандидату). `code` пока не отдаётся (нет модуля анализа кода). С `vacancy_id` заполняется `match`. Скрытая анкета (`dnd`, удалена, без роли, стоп-лист компании), несуществующий `pseudo_id`, чужая вакансия — 404 (`candidate_not_found` / `vacancy_not_found`). `source` — `search|match|similar|direct` (по умолчанию `direct`). Каждый успешный запрос пишет строку в `profile_views` (повторные открытия тоже). `GET /candidates/me/views` (роль `candidate`) → `{total_30d, companies_30d, by_day[{date, count}]}` — только числа, названий компаний нет.

Реализовано (E8-1): `POST /offers` (роль `employer`, `Idempotency-Key` обязателен, иначе 422 `idempotency_key_required`), `GET /offers?status=&vacancy_id=` (до 100, новые первыми), `GET /offers/{id}` (кандидат: первое открытие `sent → viewed`; чужой оффер любой стороной — 404 `offer_not_found`), `GET /candidates/me/offers`, `POST /offers/{id}/accept|decline|withdraw|status`. Ответы: `OfferForCompany` (`candidate` — анонимный `CandidateCard`; `contacts` только в `GET /offers/{id}` после принятия), `OfferForCandidate` (`company`). Создание: компания `verified` (иначе 403 `company_not_verified`), вакансия своя и `published` (иначе 404 `vacancy_not_found` / 409 `vacancy_not_published`), кандидат виден в поиске для этой компании (иначе 404 `candidate_not_found`); тело `{vacancy_id, candidate_pseudo_id, salary_from, salary_to, message?}`, вилка обязательна (422 `salary_range_required`, `salary_to < salary_from` — 422 `invalid_salary_range`; `range_too_wide` не блокирует); второй оффер по той же вакансии тому же кандидату — 409 `offer_exists`. Лимиты за скользящие 24 ч по БД (`scoring.yaml` `limits`): 20 офферов на компанию (429 `offer_limit_exceeded`), 10 входящих на кандидата (429 `candidate_offer_limit_exceeded`), оба с `Retry-After`. Повтор запроса с тем же ключом и теми же вакансией и кандидатом возвращает исходный оффер (проверяется до лимитов), с другими — 409 `idempotency_key_reused`. Срок жизни — `offer_validity_days` (7); `match_snapshot` берётся из `matches`; `below_candidate_min = salary_to < salary_min`. Автомат — flows.md F8: ответ кандидата (`accept`, `decline {reason, comment?}`) из `sent|viewed`, `withdraw` — из `sent|viewed`, `status` — только `interview|hired|not_hired` (`accepted → interview|not_hired`, `interview → hired|not_hired`); запрещённый переход — 409 `invalid_transition`, ответ или отзыв после срока — 409 `offer_expired`. Каждый переход пишет `offer_events` и `offer.sent|viewed|accepted|declined|withdrawn|expired|status_changed` в outbox в той же транзакции. `salary-hint` и `team-offers` — E8-4, E15-2; перевод `sent|viewed → expired` по времени — `offers.expire_due()` (вызовет cron E8-5).

Реализовано (E15-2): `GET /teams` (роль `employer`) — участник виден, если не `dnd`, есть роль, компания не в его стоп-листе и `visibility.teams` не выключен; скрытые не раскрываются, команда показывается при ≥2 видимых участниках; `discipline` — по соревнованию команды, `min_place` — лучшее место в `fsp_results` с этим `team_id` не хуже заданного. `POST /team-offers` (`Idempotency-Key` обязателен, почта подтверждена): вакансия своя и опубликована, команда видимая, участники из `salary_per_member` — разные (≥2, иначе 422 `team_members_invalid`) и состоят в команде (404 `candidate_not_found` / `team_not_found`). Создаёт по обычному офферу на участника (те же проверки, лимиты и события `offer.sent`) с общим `team_offer_id`; всё в одной транзакции, ошибка на любом участнике откатывает все. Ключ идемпотентности оффера участника — `<ключ>#<pseudo_id>`, повтор возвращает исходные офферы с `Idempotent-Replay: true`. Каждый участник принимает/отклоняет свой оффер; `team_offer_id` отдаётся в `OfferOut`.

Реализовано (E20-2, ADR-022): приглашение без вакансии. `CreateOffer`: `vacancy_id` необязателен, новые поля `title` (≤ 200), `description` (≤ 4000), `contact_method` (`platform|email|phone|telegram`); без вакансии нужен `title` (422 `title_required`), вилка обязательна как раньше. Перед созданием — `identity.require_verified_email` (403 `email_not_verified`, пока `EMAIL_VERIFICATION_REQUIRED=false` — пропускает). Второе открытое (`sent|viewed`) приглашение без вакансии той же компании тому же кандидату — 409 `offer_exists`; повтор по `Idempotency-Key` — исходный оффер. В ответах `Offer*`: `vacancy` может быть `null`, добавлены `title` (без своего — название вакансии), `description`, `contact_method`, `initiator` (`employer|candidate`). Принятие и раскрытие контактов — тот же автомат. События `offer.*` — `schema_version: 2` (messaging.md §2.1).

Реализовано (E8-6, минимум): `POST /offers/salary-hint` (роль `employer`, своя вакансия, кандидат виден компании, вилка обязательна) → `SalaryHint`: `p_accept` — детерминированная формула [matching.md §4.1](matching.md#41-взаимный-подбор-интерес-кандидата) (`app/matching/p_accept.py`, коэффициенты и пороги — `scoring.yaml` `p_accept`; `company_rating` берётся из `responsibility_score`, `stack_interest` — доля `primary_stack` кандидата среди навыков вакансии), `acceptance_hint` по порогам 0.35/0.65, `below_candidate_min`, `range_too_wide` (>1.6); `category_median` — медиана `salary_min` анкет в ячейке role×grade (нужно ≥ 3 анкет, иначе `null`), `vs_category_median = salary_to / median − 1`. Реализовано (E18-6): сортировка `mutual` — `H = 2·score·p_accept / (score + p_accept)` (`mutual()` в `p_accept.py`); без `sort` в теле при `vacancy_id` — `mutual`, без вакансии — `match`; `mutual` без вакансии сводится к `match`; не прошедшие жёсткие фильтры вакансии идут в конце. В `CandidateCard.match` и в полной карточке с `vacancy_id` поле `interest` (`low|medium|high`) — интерес кандидата при вилке вакансии. `GET /offers/{id}/events` — таймлайн для обеих сторон.

Реализовано (E20-3, ADR-022): отклик кандидата — оффер с `initiator = candidate` (`offers.service.apply`). `POST /vacancies/{id}/apply` (роль `candidate`): вакансия не `published` или не найдена — 404 `vacancy_not_found`, компания в стоп-листе — 409 `company_in_stoplist`, повтор (в том числе после приглашения на ту же вакансию) — 409 `already_applied`, лимит `application_candidate_per_day` (20 за 24 ч) — 429. Статус `sent`, `awaiting_reply_from = company`; контакты раскрываются сразу (`contact_reveals` создаётся при отклике — отклик есть согласие кандидата). Компания видит отклик в `GET /offers?initiator=candidate`, первое открытие `GET /offers/{id}` переводит `sent → viewed`; дальше `POST /offers/{id}/status` `interview|not_hired` (из `sent|viewed`), `interview → hired|not_hired`; `accept`, `decline` и `withdraw` компании на отклик — 409 `invalid_transition`. Кандидат отзывает отклик через `/candidates/me/applications/{id}/withdraw`. Статусы видны обеим сторонам (`GET /offers/{id}`, `/candidates/me/applications`). События `offer.*` с `initiator = candidate`; уведомление «Новый отклик» уходит компании, в метрики офферов и меню бота отклики не входят; лимиты приглашений отклики не считают. `GET /vacancies/public` объявлен раньше `/{vacancy_id}`.

Реализовано (E8-2): при переходе в `accepted` в той же транзакции создаётся `contact_reveals` (одна строка на оффер). `GET /offers/{id}/contacts` (роль `employer`, свой оффер) → `{name, email?, phone?, telegram?}`; до принятия или после отказа — 409 `contacts_not_revealed`, чужой оффер — 404; каждое чтение пишет в лог `contacts.viewed` (offer, компания, пользователь, без ПДн). Пока анкета не хранит `full_name_enc`/`contacts_enc`, `name` — псевдоним, `email` — почта аккаунта, `telegram` — `@username` привязанного бота, `phone` пуст. `GET|POST /offers/{id}/messages` (обе стороны; `{text}` 1–2000 символов; чужой оффер — 404): писать можно в `sent|viewed|accepted|interview`, иначе 409 `offer_closed` (после срока — 409 `offer_expired`), пустой текст — 422 `empty_message`, лимит 30 сообщений в час на пользователя и оффер (429 + `Retry-After`); в `accepted|interview` `awaiting_reply_from` переключается на другую сторону; событие `offer.message` с `message_id` уходит в outbox. `POST /offers/{id}/complaint` (роль `candidate`, свой оффер; `{reason, comment?}`, `reason` ∈ `spam|discrimination|fake_company|salary_mismatch|abuse|other`, иначе 422 `invalid_reason`): 201 `{id, offer_id, reason, status: open, created_at}`, повторная жалоба на тот же оффер — 409 `complaint_exists`; разбор — `/admin/complaints`.

Реализовано (E13-1b): `GET /admin/complaints?status=open|resolved|dismissed` (роль `fsp_admin`, новые сверху, до 100; `{id, offer_id, company_id, company_name, reason, comment, status, created_at}`, без данных жалобщика), `POST /admin/complaints/{id}/resolve` `{decision?: resolved|dismissed}` (по умолчанию `resolved`; повтор того же решения идемпотентен, смена решения — 409 `invalid_status`; нет жалобы — 404 `complaint_not_found`). Модерация компаний — E6-1 (выше).

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
| `GET /admin/dashboard?days=30` | Дашборд ФСП (роль `fsp_admin`), `days` 1–180. Когортная воронка по `analytics_events`: регистрация → тест → категория (`category_changed` или `profile_updated.grade_to`) → приглашение (`offer_received`) → ответ; у этапов `count`, `pct_of_registered`, `pct_of_previous`; `fsp_share` (привязали ФСП / зарегистрированные), `navigator_to_competition` (клик `competition_clicked` из навигатора или uplift / увидели `uplift_shown`). Ячейки меньше 5 человек: `count`, `pct` = `null`, `hidden: true`. Востребованные навыки и регионы — позже |
| `GET /admin/quality`, `GET /admin/quality/{run_id}` | Страница качества (eval_runs) |
| `POST /admin/quality/runs` | Загрузка результата `make eval` (роль A или сервисный токен) |
| `GET /admin/quality/fairness` | Панель справедливости: impact ratio по группам (синтетика + демо-показы) |
| `POST /admin/live-runs` | Создать прогон: `{scenario: candidate|employer, tasks?: [id], notes?}` → `RunOut` с `token` и `path` (`/run/<token>`) |
| `GET /admin/live-runs?scenario=` | Прогоны и сводка `summary`: успешность заданий, медианное время, медианный SUS, согласие с категорией |
| `GET /admin/live-runs/{id}` | Прогон: задания (счётчик, время), шаги, общее время, затык (`stuck_task`), SUS, согласие с категорией |
| `GET /run/{token}` | Для испытателя (без входа): задания и их выполнение; по токену, неверный токен → 404; лимит 60/мин на IP |
| `POST /run/{token}/start` | Для испытателя: запускает таймер и привязывает псевдоним вошедшего пользователя (идемпотентно) |
| `POST /run/{token}/sus` | Для испытателя: `{answers: [1..5]×10, category_agree?, notes?}`, завершает прогон; повтор → 409 `run_finished` |
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
| `POST /track` | Батч событий интерфейса, см. [metrics.md](metrics.md). Тело `{events[1..50]{event, ts, session_id?, run_id?, app_version?, props}, batch_id?, access_token?}` (`actor`, `role`, `channel` от клиента не принимаются → `422`). Авторизация необязательна: роль и псевдоним берутся из Bearer-токена, для `sendBeacon` (без заголовков) токен можно передать в теле; без токена событие анонимное. `202 {accepted, rejected, duplicate}`: событие с неизвестным именем, не из источника `web` или с лишним полем в `props` отклоняется (`rejected`), остальные пишутся. Повтор того же `batch_id` за 10 минут не пишет события (`duplicate: true`). 120 запросов в минуту на пользователя или IP, `429` |
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
| `POST /internal/track` | bot | Батч событий бота: `{events[1..50]{event, ts, session_id?, run_id?, app_version?, props, user_id?, role?}, batch_id?}` → `202 {accepted, rejected, duplicate}`. Канал `tg`, источник `bot` (допустимы только события с этим источником: `uplift_shown`, `uplift_clicked`, `competition_clicked`); `user_id` core превращает в псевдоним `HMAC` сам, без него событие анонимное. Повтор `batch_id` не дублирует |
| `POST /internal/tg/start` | bot | `{tg_user_id, chat_id, username, start_param?}` → `{user_id, role, missing_consents[], linked: bool}`. Нет аккаунта — создаёт кандидата без email (заготовку), повтор обновляет `chat_id`. `missing_consents` — из `pd_processing`, `telegram_notifications`; `linked` — аккаунт связан с сайтом (есть email). `start_param` обрабатывает бот |
| `POST /internal/tg/consents` | bot | `{tg_user_id, types[]}` → `204`; неизвестный тип `422 invalid_consent`, неизвестный Telegram `404 telegram_unknown` |
| `POST /internal/tg/link` | bot | `{tg_user_id, token}` — привязка по deep link → `{user_id, linked}`. Заготовка бота (без email и пароля) вливается в аккаунт сайта: согласия переносятся, заготовка деактивируется. Повтор для того же аккаунта безвреден. Ошибки: `410 link_token_invalid`, `404 telegram_unknown` (не было `/start`), `409 telegram_already_linked` (Telegram привязан к другому аккаунту сайта или у аккаунта уже есть другой Telegram) |
| `POST /internal/auth/magic-link` | bot | `{tg_user_id, redirect}` → `{url}` вида `<WEB_BASE_URL>/auth/magic?token=…&redirect=…`. `redirect` — только путь SPA (`/…`), иначе `422 invalid_redirect`; 5 ссылок в минуту на Telegram |
| `POST /internal/tg/resumes` | bot | multipart `file` + `tg_user_id` → `202 {resume_id, job_id}`. Проверки как у сайта: PDF/DOCX по сигнатуре, до 10 МБ, 10 в сутки; без `pd_processing` — `403 consent_required`. Ошибки: `413`, `415`, `422 empty_file`, `429` |
| `GET /internal/tg/resumes/{id}?tg_user_id=` | bot | `{status, error, experience_months, skills[], unknown_skills}` — компактный итог разбора для сообщения «Вот что я понял»; чужое → 404 |
| `POST /internal/tg/resumes/{id}/confirm` | bot | `{tg_user_id}` — подтверждение без правок; повтор безвреден; до разбора `409 resume_not_parsed` |
| `GET /internal/tg/profile?tg_user_id=` | bot | Краткий профиль для сообщения: `{primary_role, grade, grade_preliminary, skills[≤6]: {name, level, claimed_only}, fsp[≤3]}` |
| `GET /internal/tg/fsp?tg_user_id=` | bot | `{linked, verified, participant_id, achievements[≤6], teams[]}` (E9-4) |
| `POST /internal/tg/fsp/link`, `…/verify`, `…/sync` | bot | `{tg_user_id, participant_id? \| email?}` → `{method, masked_contact}`; `{tg_user_id, code}` → `{verified}`; `{tg_user_id}` → `202`. Правила и лимиты как у `/candidates/me/fsp/*` (10 попыток / 10 мин, sync раз в 10 мин, нужно `pd_processing`); ошибки connector пробрасываются с тем же `code` |
| `GET /internal/tg/category?tg_user_id=` | bot | `{categories[{profession, title, grade, needs_confirmation, valid_until}], claims[{profession, title, status, declared_grade, confirmed_grade}]}` — через `assessment.service` (`get_grades`, `claimed_vs_confirmed`), без своей логики |
| `GET\|PATCH /internal/tg/settings` | bot | `{salary_min, formats[], search_status}`; PATCH `{tg_user_id, salary_min?, formats?}` частичный, `salary_min: null` очищает; запись требует `pd_processing` |
| `PATCH /internal/tg/status` | bot | `{tg_user_id, status: active\|open\|dnd}` → настройки; `active` на 7 дней, как `PATCH /candidates/me/preferences` |
| `POST /internal/tg/github` | bot | `{tg_user_id, login}` |
| `GET /internal/tg/offers?tg_user_id=` | bot | Активные офферы кандидата (`sent|viewed|accepted|interview`, до 10, новые первыми) → `TgOffer[]`: поля `offer_id`, `status` и те же данные, что у шаблона `offer_new` (`company_name`, `company_responsibility`, `vacancy_title`, `formats[]`, `employment_type`, `salary_from/to`, `message`, `match_score`, `explanation[]`, `below_candidate_min`, `expires_at`) |
| `POST /internal/tg/offers/{id}/view|accept` | bot | `{tg_user_id}` → `TgOffer`. `view` переводит `sent → viewed`; правила и ошибки как у `/offers/{id}/accept` (`409 invalid_transition`, `409 offer_expired`) |
| `POST /internal/tg/offers/{id}/decline` | bot | `{tg_user_id, reason, comment?}` → `TgOffer`; `reason` — `DeclineReason` (бот переводит коды кнопок `ls|ws|wf|wg|nl|ot`) |
| `POST /internal/tg/offers/{id}/messages` | bot | `{tg_user_id, text}` (1–2000) → `201 {id}`; канал `tg`, правила и лимит 30/час как у сайта (`409 offer_closed`, `422 empty_message`). Чужой оффер, как и везде, — `404 offer_not_found`; неизвестный Telegram — `404 telegram_unknown` |
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
  categories: { profession: string; grade: "junior" | "middle" | "senior" }[]; // CategoryRef, из теста (E23-1)
  strength?: { value: number; rank: number | null; top: { code: "T"|"F"|"S"|"R"|"C"; text: string; value: number; weight: number }[] } | null; // E23-2
}

interface CandidateCardFull extends CandidateCard {
  skills: SkillWithTrust[];
  grade_info: GradeInfo;
  code?: CandidateProfile["code"];       // без ссылок на репозитории, если visibility.repos = false
  experience: { title: string; company?: string; months: number; skills: string[] }[]; // company — только если разрешено
  offers_from_you: { id: string; status: OfferStatus }[];
  claimed_vs_confirmed: ClaimedVsConfirmed[]; // assessment.md §9, blocks.md §4.3: заявлено (опрос/резюме) vs подтверждено тестом
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

interface Navigator {             // E12-1: GET /candidates/me/navigator (app/matching/navigator.py)
  target?: { role: RoleSlug; grade: "junior" | "middle" | "senior" };   // следующий грейд теста; нет у senior
  current_grade?: { profession: string; grade: string; valid_until: string; needs_confirmation: boolean };  // из assessment.get_grades
  next_grade?: { points_needed: number; hints: string[] };   // v1, candidates.grade_next
  test?: { profession: string; grade: string; path: string };  // path = /me/assessment?profession=&grade= (blocks.md §4.8)
  skill_gaps: { skill: string; name: string; weight: number; confidence: number; testable: boolean }[];  // навыки профессии с уверенностью < 0.65, до 8
  competitions: { id: string; title: string; start_date: string; registration_url?: string; skills: string[] }[];  // ближайшие 120 дней, правило дисциплины закрывает пробел, до 5
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

// Правки при подтверждении: убрать навык из разбора (slug), добавить свой (source=self, 0.15), заменить опыт/образование целиком
interface ParsedResumeEdits {
  remove_skills: string[]; add_skills: string[];
  experience?: ParsedResume["experience"]; education?: ParsedResume["education"];
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
| `o:b:<offer_id>` | Назад от выбора причины к кнопкам оффера |
| `t:s:<skill_slug>` | Начать тест |
| `t:a:<session_id>:<question_idx>:<option_id>` | Ответ теста (~45 байт; индекс вопроса защищает от нажатия старой кнопки) |
| `s:<active|open|dnd>` | Статус поиска |
| `f:l` / `f:s` | ФСП: ввести ID или email / обновить результаты |
| `g:sal` / `g:f:<remote|hybrid|office>` | Настройки: минимальная зарплата (FSM) / переключить формат |

Подробно: [telegram.md](telegram.md).
