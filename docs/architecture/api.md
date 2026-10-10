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
| `POST /auth/jury` | P | E40-1, только `DEMO_MODE` (иначе 404): `{role: candidate\|employer, pair?}` → `JuryAuthOut {access_token, user, pair}` + cookie. Песочница жюри: своя пара демо-аккаунтов на ключ `pair` (тот же ключ — та же песочница, без него — новая); лимит 30 за 10 мин на IP |
| `POST /auth/refresh` | P (cookie) | Ротация refresh, новый access |
| `POST /auth/logout` | любая | Отзыв семьи refresh-токенов |
| `POST /auth/email/send` | U | Повторная отправка кода подтверждения → 204. Не чаще раза в минуту (409 `cooldown`, дата в `detail`), 5 в час (429). Новый код аннулирует старый |
| `POST /auth/email/verify` | U | `{code}` → 204, ставит `email_verified_at`. Неверный код → 400 `invalid_code`; истёк (15 мин) → 400 `code_expired`; 5 неверных попыток → 429 `too_many_attempts`. Повтор после успеха — 204 |
| `POST /auth/telegram` | P | Поля Telegram Login Widget как есть (`id`, `auth_date`, `hash`, …) → `{access_token, user}` + cookie. Подпись HMAC и `auth_date` ≤ 24 ч; нового пользователя создаёт кандидатом без email. Ошибки: `401 invalid_telegram_auth`, `401 telegram_auth_expired`, `503 telegram_login_disabled` (нет токена бота) |
| `POST /auth/magic` | P | `{token}` из ссылки бота → `{access_token, user}` + cookie. Токен одноразовый (5 мин); иначе `401 invalid_magic_token` |
| `GET /auth/fsp/start` | P/C | Редирект на OAuth ФСП (мок). Для вошедшего кандидата это привязка, иначе вход |
| `GET /auth/fsp/callback` | P/C | Обмен кода → `fsp_links` → `fsp_sync` |
| `POST /auth/password/change` | U | E39-8. `{current_password, new_password(8..128)}` → 204. Неверный текущий или нет пароля (вход через Telegram) → 403 `wrong_password`; короткий новый → 422; 5 в час (429). Все остальные сессии (refresh-семьи) закрываются, текущая остаётся |
| `POST /auth/password/initial` | U | E41-16. Первая смена временного пароля HR: `{new_password(8..128)}` → 204, без текущего пароля. Не требуется — 409 `password_change_not_required`; срок вышел — 403 `temp_password_expired`; совпадает с временным — 422 `same_password`; 5 в час (429). Сессии остаются; смена фиксируется в БД до отправки ответа (E43-3) |
| `GET /me` | любая | `{user, role, candidate?, company?, consents, telegram_linked}` |
| `GET /me/consents`, `PUT /me/consents` | любая | Список и выдача/отзыв согласий |
| `POST /me/credentials` | кандидат | Выпустить Open Badge `{profession?}` на действующую категорию. `201 {id, profession, grade, url, issued_at, valid_until, revoked_at, credential}`; тот же грейд повторно — тот же бейдж, новый грейд — старый отзывается (`superseded`). `404 grade_not_found`, `409 publication_required` (нет `public_profile` или согласия `profile_publication`) |
| `GET /me/credentials` | кандидат | Свои бейджи (в т.ч. отозванные) |
| `POST /me/credentials/{id}/revoke` | кандидат | Отозвать бейдж; идемпотентно, чужой или несуществующий → `404 credential_not_found` |
| `POST /me/telegram/link` | C, E | → `{deep_link}` вида `https://t.me/<bot>?start=link_<token>` (токен 15 мин, одноразовый); `503 telegram_disabled`, если имя бота не задано |

Коды ошибок `/auth/*`: `email_taken` (409), `invalid_credentials` (401, одинаков для неверного пароля и неизвестного email), `refresh_reused` (401, повторное использование refresh — вся семья отозвана, cookie сбрасывается), `unauthorized` (401), `rate_limited` (429), `forbidden_origin` (403, `Origin` не из `ALLOWED_ORIGINS` на `/auth/refresh` и `/auth/logout`). Саморегистрация — только `candidate` и `employer`. Код подтверждения (E20-1, 6 цифр, хранится хешем) уходит на email при регистрации по SMTP (`SMTP_*`; пустой `SMTP_HOST` — письмо не отправляется, регистрация не падает; dev — Mailpit, профиль `dev`, UI `:28025`). `EMAIL_VERIFICATION_REQUIRED` (по умолчанию `false`) включает проверку `require_verified_email` там, где она вызывается. `user` в ответах `/auth/*` и `/me` содержит `email_verified`. `GET /me` пока возвращает `{id, email, role, email_verified, consents[]}` (`consents` — типы действующих согласий).

`GET /me/consents` → массив по всем `consent_type`: `{type, required, granted, version, current_version, granted_at}`. `PUT /me/consents` `{consents:[{type, granted, version?}]}` → тот же массив; идемпотентно. Выдача с устаревшей `version` → 409 `consent_version_mismatch`. Эндпоинты, требующие согласия, отвечают 403 `consent_required` (зависимость `require_consent(type)`).

### 2.2. Кандидат: профиль

| Метод и путь | Назначение |
|---|---|
| `GET /candidates/me/profile` | Полный профиль владельца: `CandidateProfile` (в нём `claimed_vs_confirmed: ClaimedVsConfirmed[]` — заявлено в опросе/резюме против грейда из теста, E23-3; E39-15: `education[]`, `links[]`, `hidden_skills[]`, `resume_draft_id` — последнее резюме в `queued|parsing|parsed`, ещё не подтверждённое; `skills[].skill.type` — тип навыка) |
| `PATCH /candidates/me/profile` | Ручная форма (E20-4), частичное обновление: `{contacts: {email, phone, telegram} | null, full_name: string(≤120) | null, stack: [{slug, years?}], experience_months, desired_roles: slug профессии системы[] (≤5; `GET /taxonomy/professions/suggest`, неизвестная — `422`; E41-6), soft_skills: slug[], age_group: adult|minor, parent_consent: bool, links: url[] (≤10, `^https?://`, ≤300) | null, hidden_skills: slug[] (≤200) | null}` → `CandidateProfile` (в нём `contacts` — только владельцу, `desired_roles`, `experience_months`). Стек — полный список: доказательства `self` (сила 0.15, «заявлено»), убранные выключаются; софт-навыки → `claimed_soft`. Контакты и ФИО шифруются (`contacts_enc`, `full_name_enc`, Fernet); `full_name` пустой или `null` очищает, в профиле владельца отдаётся как есть. Изменение стека, стажа, софт-навыков → пересчёт и рост `profile_version`. Возраст (E32-5b): `age_group` — `adult` или `minor` (15–17 лет), дата рождения не собирается; `parent_consent: true` только при `minor` (иначе `422`), `false` — отзыв; смена на `adult` сбрасывает согласие. В профиле: `age_group`, `parent_consent`, `publishable` (`false` у `minor` без согласия родителя — анкета не попадает в каталог и подбор). Ссылки (E39-15) — полный список, дубли схлопываются, шифруются (`links_enc`), видны только владельцу. Скрытые навыки (E39-15) — полный список slug: работодатель их не видит (карточка, `top_skills`, `primary_stack`, пункты объяснения подбора), на подбор и грейд не влияют. Ошибки: `422 unknown_skill` (нет в справочнике, софт в стеке, не софт в `soft_skills`) |
| `GET /candidates/me/profile.pdf` | PDF-резюме владельца (E20-6, E41-13; HTML → WeasyPrint, A4, 1–2 страницы, кириллица, графит и хвойный зелёный): ФИО (или псевдоним) и фото, профессия и грейд (без разбора «из чего сложился»), свои контакты, желаемая роль, город и формат, навыки списком по типам, опыт, образование, достижения ФСП, оценка на платформе, ссылки. `application/pdf`, `Content-Disposition: attachment`, `Cache-Control: private, no-store`. Не кешируется (рендер ~1 с); только `candidate` (чужого профиля нет — отдельного ресурса нет). Ошибки: `401`, `403` |
| `PATCH /candidates/me/preferences` | `{salary_min, formats, employment_types, city, relocation, search_status}`. `search_status=active` выставляет `active_until=+7д` |
| `PATCH /candidates/me/visibility` | `{full_name, companies, fsp, region, education, repos, teams, public_profile}` (все необязательные; E36-4, ADR-027). Умолчания: `full_name=false`, `companies=true`, `fsp=true`, `region=true`, `education=false`, `repos=false`, `teams=true`. Реально изменившиеся ключи пишут событие `candidate.visibility.changed`. Контакты настройкой не открываются — только принятие приглашения или отклик (blocks.md §4.5) |
| `PUT /candidates/me/stoplist` | `{company_ids[]}` |
| `POST /candidates/me/resumes` | multipart `file` (PDF/DOCX по сигнатуре, до 10 МБ; 10 в сутки) → `202 {resume_id, job_id}`. Ошибки: `413 file_too_large`, `415 unsupported_file_type`, `422 empty_file`, `429` |
| `GET /candidates/me/resumes/{id}` | `{status: queued|parsing|parsed|confirmed|failed, parsed: ParsedResume, error}`; чужое → 404 |
| `POST /candidates/me/resumes/{id}/confirm` | `{edits: ParsedResumeEdits}` → профиль пересчитывается. Повтор безвреден; до разбора `409 resume_not_parsed`; неизвестный `add_skills` → `422 unknown_skill` |
| `GET /candidates/me/skills` | **Не реализовано** (отдельной ручки нет, навыки приходят в `GET /candidates/me/profile` и `/graph`). План: `SkillWithTrust[]` |
| `POST /candidates/me/skills` | **Не реализовано:** заявить навык можно через `PATCH /candidates/me/profile` (`stack`, источник `self`). План: `{skill_id}` |
| `DELETE /candidates/me/skills/{skill_id}` | **Не реализовано:** убрать навык можно через `PATCH /candidates/me/profile` (полный `stack`). План: убрать свой `self`/`resume` навык (доказательства ФСП/кода/тестов не удаляются) |
| `GET /candidates/me/skills/{skill_id}/evidence` | `Evidence[]` — «откуда взялся навык» |
| `GET /candidates/me/category` | `CategoryExplanation`: роли, грейд, разбивка, уверенность, как подняться |
| `POST /candidates/me/category/dispute` | `{claimed_role, claimed_grade, comment}` |
| `POST /candidates/me/fsp/registry-link` | Кнопка «Привязать ФСП» (E39-28, ADR-052): core передаёт в реестр email аккаунта и телефон из контактов → `{linked, matched_by: email|phone|null, participant_id}`. Совпал ровно один участник — привязка сразу (`fsp.linked`, `method=registry`, `verified=true`), достижения приходят следующей синхронизацией; иначе `linked=false` и UI показывает заявку. Нужно согласие `pd_processing`; лимит 10 за 10 мин; 409 `fsp_already_linked` |
| `GET /candidates/me/fsp/request` | Последняя своя заявка на привязку `{id, full_name, email, phone, event, status: pending|accepted|rejected, reason, created_at, decided_at}` или `null` |
| `POST /candidates/me/fsp/requests` | `201` заявка админу `{full_name, email?, phone?, event?}` (нужен email или телефон; повтор правит открытую заявку). 422 `bad_email`/`bad_phone`/`validation_error`, 409 `candidate_already_linked`; лимит 5 за 10 мин |
| `POST /candidates/me/fsp/link` | Старый путь (UI не использует с E39-28, бэкенд сохранён): `{participant_id? , email?}` → `{method: "code"|"manual", masked_contact?}` |
| `POST /candidates/me/fsp/verify` | `{code}` |
| `POST /candidates/me/fsp/sync` | `202` — ручное обновление (не чаще раза в 10 минут) |
| `GET /candidates/me/fsp` | `{link, achievements: FspAchievement[], ranks, teams}` |
| `POST /candidates/me/github` | **Не реализовано** (E10-1 «ДНК кода» вне прототипа). План: `{login}` → `202 {analysis_id}` |
| `GET /candidates/me/code-analysis` | **Не реализовано** (вместе с анализом GitHub, E10-1). План: последний `CodeAnalysis` |
| `GET /candidates/me/navigator` | `Navigator` |
| `GET /candidates/me/standing` | `CandidateStanding {profession, grade, mode, confirmed_at, strength {value, rank, top_percent, relative, gap_to_next_ten {top_percent, gap_relative}, parts[]}, leader {grade, relative=100}, category_size, peers[{strength, salary_min, theta}], category_stats {candidates, interests, interest_salary_from_median, interest_salary_to_median, companies_searching}}` (E35-12a, E39-16) — сила профиля и место среди кандидатов своей категории «профессия × грейд» (основная профессия, иначе старший грейд). Сила — формула [assessment.md §9](assessment.md) без запроса (S — доверие по навыкам); `rank` 1 — сильнейший, равные делят место, `top_percent = ceil(rank / category_size · 100)`; `relative` (E39-12) = сила / сила лидера категории · 100 (0–100 %; нулевой лидер → 100), `leader` — анонимно: грейд и 100 %, без идентификаторов; `gap_to_next_ten` — сколько п. п. «от лидера» не хватает до ближайшей границы «десятки» выше (топ-34 → топ-30; у топ-10 % и лидера `null`); формулы подбора не меняются, число силы в UI не показываем. `peers` — до 200 точек для графика «Где ты среди своих» (своя первой, без идентификаторов): X — уровень в тесте `theta`, Y — `strength`. `category_stats` (E39-16) — общие числа категории: `candidates` — число кандидатов, `interests` и медианы вилок `interest_salary_*_median` — по интересам и приглашениям компаний кандидатам категории (медиан нет без интересов), `companies_searching` — компаний с опубликованной вакансией на профессию, в вилку грейдов которой входит грейд категории. Без действующего грейда — `200` с пустыми полями (`strength: null`, `category_size: 0`). Только роль `candidate` (иначе 403). Код — `services/core/app/matching/standing.py` |
| `GET /candidates/me/uplift` | `Uplift` — какой навык подтвердить, чтобы подходить под N% больше вакансий ([matching.md §6](matching.md#6-uplift-для-кандидата-какой-навык-добавить)) |
| `GET /candidates/me/graph?skills=top|all&depth=facts|competitions` | `Subgraph` — граф доказательств (в т.ч. тесты `test`; у навыка `skill_type`) для визуализации ([graph.md §6](graph.md#6-api-подграфа)) |
| `POST /candidates/me/navigator/clicks` | **Не реализовано** (ручки в коде нет). План: `{competition_id, skill_id}` |
| `GET /candidates/me/views` | `ProfileViewsStats`: `{total_30d, companies_30d, window_days, visible, by_day[]}`; `by_day` — полные 30 дней с нулями, `visible` — карточка доступна работодателям (E43-5) |
| `GET /candidates/me/offers?initiator=` | `OfferForCandidate[]` (приглашения и отклики; `initiator=employer|candidate` фильтрует) |
| `GET /candidates/me/applications` | `OfferForCandidate[]` — мои отклики (E20-3) |
| `POST /candidates/me/applications/{id}/withdraw` | Отозвать свой отклик из `sent/viewed`; приглашение или чужой оффер — 404 |
| `DELETE /candidates/me` | Удаление профиля (F13, 152-ФЗ), необратимо. Тело подтверждения: `{password}` (если у аккаунта есть пароль) или `{confirm: "УДАЛИТЬ"}` (вход через Telegram, пароля нет). `204`. Неверное подтверждение → `403 confirmation_failed`; 5 попыток в час (`429`); не `candidate` → `403`; повтор и удалённый профиль → `404 candidate_not_found`. Требует только токен (согласие `pd_processing` не нужно) |

Удаление профиля (F13): в одной транзакции стираются резюме (записи и файлы в хранилище), опыт, образование, доказательства и навыки, попытки, ответы, грейды, опросы и ответы на регулярные задания, оспаривания категории; согласия отзываются; в `candidates` остаётся обезличенная строка с псевдонимом (на неё ссылаются офферы и таблицы блока 2), `deleted_at` скрывает её из подбора, `profile_version` растёт. В `users` обнуляются email и пароль, `is_active=false`, `deleted_at`, refresh-токены и коды подтверждения удаляются, токен доступа перестаёт действовать (`401`), email можно зарегистрировать заново. Событие `candidate.deleted` `{candidate_id}` уходит в outbox: по нему аналитика удаляет сырые события, остальные модули блока 2 (подбор, офферы, Telegram, ФСП, бейджи, просмотры) чистят свои данные сами.

Реализовано (E4-6): `GET /candidates/me/category` → `CategoryExplanation` `{primary_role, roles[{role, weight, score}], primary_stack, explanation[{skill, weight, confidence, level, sources, contribution}], grade: GradeInfo, dispute?}` (объяснение считается по `candidate_skills`, ml.md §4; `grade.next_grade.hints` — «как подняться»). `POST /candidates/me/category/dispute` `{claimed_role, claimed_grade, comment?≤2000}` (согласие `pd_processing`; неизвестная роль/грейд — 422) → 201 `{id, claimed_role, claimed_grade, comment, status: open, created_at}` в `category_disputes`, событие `category.disputed` в outbox (без комментария); пока есть неразобранное оспаривание — 409 `dispute_exists`. Разбор админом — позже (E12).

Реализовано (E3-1): `GET /candidates/me/profile`, `PATCH /candidates/me/preferences`, `PATCH /candidates/me/visibility`, `PUT /candidates/me/stoplist`. Только роль `candidate` (иначе 403). Анкета создаётся лениво при первом обращении. Запись требует согласие `pd_processing` (403 `consent_required`); `visibility.public_profile=true` — ещё и `public_profile`. `PATCH` частичный (`null` очищает `salary_min`/`city`), `visibility` дополнительно содержит `teams` (по умолчанию `true`). Ответ `PATCH` и `GET profile` (E4-7) — `CandidateProfile` с `category` (`null`, пока роль не определена), `grade` (`GradeInfo`; `preliminary` — уверенность ниже 0.5, подписи сигналов разбивки — по-русски), `skills` (`SkillWithTrust` с `top_evidence`), `team_signals` (только `value ≥ 0.3`, подпись `strong`/`present`, факты без ПДн) и `claimed_soft`; `fsp`, `code`, `completeness` пока не отдаются. `GET /candidates/me/skills/{skill_id}/evidence` — `EvidenceBrief[]` навыка владельца (свежие первыми; для выведенного по иерархии навыка — доказательства основания); `skill_id` принимает id или slug; навыка нет в профиле → 404 `skill_not_found`. `PUT stoplist` `{company_ids[]}` (до 200 UUID, дубли схлопываются) возвращает сохранённый список; существование компаний пока не проверяется (появится с E6-1). `active` без продления через 7 дней отдаётся как `open`.

Реализовано (E5-7): привязка ФСП для web (core → fsp-connector по HTTP, `SERVICE_TOKEN_CORE`, `FSP_CONNECTOR_URL`; ПДн в логи не пишутся, ошибки connector пробрасываются с тем же `code`). `GET /auth/fsp/start?next=/me&redirect=` — роль `candidate`; по умолчанию `200 {url}` (SPA делает `location.assign`), с `redirect=true` — `302` на страницу ФСП; PKCE и `state` в Redis `s:oauth:{state}` 10 мин, одноразовые; без токена 401 (с `redirect=true` — 302 на `/login?fsp=need_login`): анонимный вход через ФСП пока не поддержан, только привязка. `GET /auth/fsp/callback?code=&state=` — публичный, всегда `302` в SPA (`WEB_BASE_URL` + `next`) с `?fsp=linked` или `?fsp=error&reason=<code>`. `POST /candidates/me/fsp/link` `{participant_id?, email?, manual?}` (нужно одно из первых двух; 10/10 мин) и `/verify` `{code}` → `{verified}` — согласие `pd_processing`. `POST /candidates/me/fsp/sync` → 202, раз в 10 минут (429 `sync_too_often`), без привязки 409 `fsp_not_linked`, команда `fsp.sync(reason=manual)` через outbox. `GET /candidates/me/fsp` → `{link: {linked, verified, participant_id}, achievements, ranks, teams[{id,name,role}]}`; `link` берётся из копии `fsp_participants`, поэтому после `fsp.linked` появляется с задержкой воркера.

### 2.3. Проверка навыков

Тест v2 — адаптивный, по профессии и заявленному грейду ([assessment.md](assessment.md) §3–5, §10). Схемы и коды ошибок каждой строки — в assessment.md §10; здесь каталог путей. Чужая попытка, задание или семейство → 404.

| Метод и путь | Роль | Назначение |
|---|---|---|
| `GET /assessment/survey`, `PUT /assessment/survey` | C | Опрос о себе: профессия, заявленный грейд, стек, ожидания (история — новые записи) |
| `POST /assessment/attempts` | C | `{profession, declared_grade, mode?}` → `201` попытка. `409 cooldown` / `attempt_active`, `403 email_not_verified` / `consent_required`, `422 unknown_profession`. `mode=express` — экспресс-режим |
| `GET /assessment/attempts/{id}` | C | Итог: грейд, θ по типам, разбор ошибок, честность |
| `GET /assessment/attempts/{id}/next` | C | Следующее задание без ключа: `{response_id, kind, stem, options?, time_limit_s, steps?}` или итог |
| `POST /assessment/attempts/{id}/answers` | C | `{response_id, answer, rt_ms, telemetry}`; повтор с тем же `response_id` идемпотентен |
| `GET /assessment/attempts/{id}/review` | C | Разбор теста «что подтянуть» (E41-5): только задания с неполным баллом, без верных ответов и вариантов: `{attempt_id, profession, items[{response_id, seq, kind, stem, yours?, reason{code,label,detail}, skill, skill_type, score, rt_ms?, time_limit_s, why, misconception?, steps?}]}`; полей `correct` и `options` в ответе нет; идёт — `409 attempt_active`, чужая — `404` |
| `POST /assessment/attempts/{id}/upgrade` | C | Тест следующего грейда по приглашению бонусного этапа (ADR-025): `201`, новая попытка |
| `POST /assessment/attempts/{id}/responses/{response_id}/explain` | C | «Объясни ответ» после завершения попытки: `{self_reason?}` → причина ошибки по правилам |
| `GET /assessment/history` | C | История опросов и попыток, даты кулдаунов |
| `POST /assessment/plan/preview` | C, E | `{vacancy_id \| skills}` → план теста и 3 примера заданий (демо «вакансия → тест»); ключей в ответе нет |
| `GET /assessment/tasks`, `GET /assessment/tasks/{task_id}` | C | Открытые регулярные задания действующих категорий; вариант без ключа и рубрики |
| `POST /assessment/tasks/{task_id}/answer` | C | `{answer}` — один ответ на раунд, повтор возвращает принятый |
| `POST /families`, `GET /families`, `GET /families/{family_id}` | E, A | Конструктор заданий: черновик семейства, свои семейства (E30-1); `ready` — «Готово» (E41-14) |
| `PUT /families/{family_id}/ready` `{ready}` | E, A | «Готово» / «В черновик» для задания компании (E41-14, ADR-027): без допуска админа; ключ от LLM подтверждается этим же действием; у заданий админа — 409 `not_company_family`; чужое → 404 |
| `POST /employer/tasks`, `GET /employer/tasks`, `GET /employer/tasks/{task_id}` | E | Регулярные задания работодателя (E25-1): черновик, список, карточка со счётчиками |
| `POST /employer/tasks/{task_id}/publish`, `POST /employer/tasks/{task_id}/close` | E | Рассылка по категории (событие `regular_task.published`), закрытие |
| `GET /employer/tasks/{task_id}/submissions` | E | Ответы: только `pseudo_id` и `invite_url` |
| `PUT /employer/tasks/{task_id}/submissions/{submission_id}/score` | E | `{marks: [bool]}` — оценка рубрики открытого задания |
| `GET /admin/families`, `POST /admin/families/{family_id}/approve\|pilot\|quarantine\|retire` | A | Очередь допуска семейств со статистикой и решение админа; карточка (E39-31): `grade` (по уровню), `skill`, `professions[{slug,title}]` (профессии, где навык основной), `example{kind,stem,options,answer}` — сгенерированный вариант и ответ решателя (ключ) |
| `POST /admin/families/{family_id}/key` | A | Утвердить ключ задания конструктора |
| `GET /admin/demo/two-worlds`, `GET /admin/demo/llm-exam` | A | Демо-экраны качества теста (E34-3). Демо ФСП (`/admin/demo/fsp-result`, `/reset`) — §2.6 |
| `GET /assessment/interviews/{id}` и `POST /assessment/interviews`, `…/answers` | C | **Не реализовано:** ИИ-интервью по репозиторию (E11-3/E11-4, вне прототипа). Формат: `{repo_id?}` → `202 {interview_id}`; `{status, questions[], grades?}`; `{question_id, text}` |

Каталог `/admin/professions*`, `/admin/profession-suggestions*` (E41-17), `/admin/skill-cards*`, `/admin/skills/*` (справочник, E13-1a) — §2.6, публичные `/taxonomy`, `/taxonomy/professions` — §2.7. Пути v1 `/assessment/skills`, `/assessment/tests`, `/assessment/tests/{id}/answer` удалены: заменены попытками `/assessment/attempts*` (assessment.md §10).

### 2.4. Офферы (обе стороны)

| Метод и путь | Роль | Назначение |
|---|---|---|
| `POST /offers/salary-hint` | E | `{vacancy_id, candidate_pseudo_id, salary_from, salary_to}` → `SalaryHint` (с `p_accept` и `range_too_wide`) |
| `POST /vacancies/{id}/candidates/{pseudo_id}/interview-kit` | E | `202` → вопросы для структурированного интервью ([ml.md §10.1](ml.md#101-вопросы-для-структурированного-интервью)); `GET` того же пути — результат |
| `POST /candidates/{pseudo_id}/skill-requests` | E | Минимальная версия «попросить подтвердить навык»: `{skill}` → кандидату в бот приходит ссылка на тест, компании — уведомление о результате |
| `POST /offers` | E | `CreateOffer` + `Idempotency-Key` → `201 Offer` |
| `GET /offers?status=&vacancy_id=&initiator=` | E | Офферы компании; `initiator=candidate` — отклики на её вакансии |
| `GET /offers/{id}` | C, E | Оффер. Для кандидата первое открытие переводит `sent → viewed` |
| `GET /vacancies/public?role=&city=&q=&grade=&skills=&salary_min=&salary_max=&format=&limit=&offset=` | — | E20-3, E39-17: опубликованные вакансии без авторизации (`PublicVacancyOut`: вилка, навыки, `company{id,name,verified,responsibility_score}`). `role` — slug профессии справочника (`str`, а не `RoleSlug`: роль вне старого списка не роняет ответ); `grade` — грейд входит в вилку вакансии; `skills` (повторяется) — вакансия требует все; `salary_min/max` — вилка вакансии пересекает указанную; `format` — `office|hybrid|remote` |
| `GET /vacancies/public/{id}` | — | E39-17: карточка опубликованной вакансии; черновик, закрытая, чужой id — 404 `vacancy_not_found` |
| `POST /vacancies/{id}/apply` | C | E20-3: `{message?}` → `201 OfferForCandidate` с `initiator=candidate`; вилка — из вакансии, контакты кандидата раскрыты сразу |
| `POST /offers/{id}/accept` | C | Необязательное тело `{message?}` (≤ 500) → `accepted`, раскрытие контактов; `message` — единственный ответ кандидата (E39-26) |
| `POST /offers/{id}/decline` | C | `{reason, comment?}` |
| `POST /offers/{id}/withdraw` | E | Только из `sent/viewed` |
| `POST /offers/{id}/status` | E | `{status: interview|hired|not_hired}` |
| `GET /offers/{id}/messages`, `POST /offers/{id}/messages` | C, E | Только сопроводительное компании (E41-4): кандидат текстом не отвечает (`POST` от кандидата — `403 candidate_message_disabled`), второе сообщение компании — `409 message_limit` |
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
| `GET /companies/me/members` | E / EA | Команда: `CompanyTeamOut` `{members: CompanyMemberOut[], invites: InviteOut[], can_manage}` (E39-24) |
| `POST /companies/me/invites`, `DELETE /companies/me/invites/{id}` | EA | Приглашение HR по ссылке, отзыв (E39-24); с E41-16 `deprecated`, интерфейс их не вызывает, выданные ссылки работают до истечения |
| `DELETE /companies/me/members/{user_id}` | EA | Отозвать доступ HR: убрать из команды, закрыть сессии (E39-24, E41-16) |
| `POST /companies/me/hr` | EA | E41-16. Создать аккаунт HR без почты: `{email, full_name}` → `201 HrAccessCard` (логин и временный пароль — один раз) |
| `POST /companies/me/members/{user_id}/password` | EA | E41-16. Выдать HR новый временный пароль → `HrAccessCard` |
| `GET /companies/me/access-log` | EA | E41-16. Журнал доступа HR → `AccessLogEntry[]` (последние 50) |
| `GET /company-invites/{token}`, `POST /company-invites/{token}/accept` | — / E | Предпросмотр и принятие приглашения (E39-24) |
| `GET|PATCH /me/profile`, `PUT|DELETE /me/avatar` | E, A | Личный профиль сотрудника: ФИО, должность, описание, аватар (E39-24) |
| `PUT|DELETE /companies/me/logo`, `GET /companies/{id}/logo?v=` | EA, публично | Логотип компании: PNG/JPEG/WebP по сигнатуре, ≤ 2 МБ; чтение без токена (E41-12) |
| `PUT|DELETE /candidates/me/avatar`, `GET /candidates/{pseudo_id}/avatar?v=&sig=` | C, по подписи | Аватар кандидата; адрес со строкой `sig` выдаётся владельцу и работодателю после приглашения (E41-12) |
| `GET /users/{id}/avatar?v=` | — | Аватар сотрудника компании или админа ФСП (E39-24) |
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
| `GET /employer/activity?limit=` | E | Лента активности компании (E35-12b), новые сверху, `limit` 1–100 (30): `ActivityFeed {items: ActivityEvent[]}`; `ActivityEvent {id, kind, at, candidate{pseudo_id, pseudonym, primary_role?, grade?}, link, offer_id?, subscription_id?, detail?}`. `kind`: `subscription_hit` (новый кандидат по подписке; только пока виден работодателям, `detail` = профессия), `interest_opened`, `interest_declined` (`detail` = код причины), `invitation_accepted`, `invitation_declined`, `task_answered` (ответ на задание в приглашении, `detail` = название). Только строки своей компании, кандидат — анонимная карточка, контактов нет и после принятия. `link` — маршрут веба (`/employer/offers/{id}` или `/employer/candidates/{pseudo_id}`). Ответы на регулярные задания (`/employer/tasks`) в ленту не входят — у них свой экран |
| `POST /interests` | E | Интерес до приглашения (ADR-026): `{candidate_pseudo_id, salary_from, salary_to, salary_basis?, message? (≤300), vacancy_id?, title?}` → `OfferForCompany` со `status = interest` |
| `POST /interests/{id}/invite` | E | Приглашение по открытому интересу: `{salary_from?, salary_to?, message?, title?, description?, contact_method?}` → `OfferForCompany` (`interest_opened → sent`) |
| `GET /candidates/me/interests` | C | `InterestsSummary {companies, salary_from_min, salary_to_max, items: OfferForCandidate[]}` — открытые интересы |
| `POST /interests/{id}/open`, `POST /interests/{id}/decline` | C | «Открыть» / «не интересно» `{reason, comment?}` → `OfferForCandidate` |
| `GET /offers/{id}/task`, `POST /offers/{id}/task/answer` | C | Задача в приглашении (E33-3): `TaskView {task, item, can_answer}`; один ответ `{answer}` → `TaskBrief {title, minutes, deadline_at, answered_at, score}`, повтор идемпотентен. В `POST /offers` и `POST /interests/{id}/invite` — необязательное `task {family_id, deadline_days 1–14}` |

Реализовано (E6-1): `POST /companies` (роль `employer`, одна компания на пользователя, иначе 409 `company_exists`; создатель — `admin`, статус `pending`), `GET|PATCH /companies/me` (PATCH только `admin` компании, 403 иначе; поля `name`, `inn`, `site`, `description`; `status` и `responsibility_score` через PATCH не меняются), `POST /companies/me/members` `{email, role}` (только `admin`; пользователь с ролью `employer` должен быть уже зарегистрирован, иначе 404 `user_not_found`; состоит в другой компании — 409 `already_member`). Модерация: `GET /admin/companies?status=`, `POST /admin/companies/{id}/verify|reject` (роль `fsp_admin`; verify из `pending|rejected`, reject из `pending|verified`, повтор того же решения идемпотентен, `blocked` через эти эндпоинты не меняется — 409 `invalid_status`). `GET /me` для работодателя возвращает `company: {id, name, status, role}`. Ограничение по `verified` для офферов и вакансий добавят E6-2 и E9-x; `company_id` в JWT пока не кладётся, компания определяется по `company_members`.

Реализовано (E33-1, ADR-026): интерес — та же строка `offers`, статусы `interest → interest_opened → sent` (дальше обычный автомат F8). `POST /interests` (роль `employer`, `require_verified_email`, компания `verified` иначе 403, кандидат виден компании иначе 404 `candidate_not_found`, вакансия — своя и `published`): вилка обязательна (422 `salary_range_required` / `invalid_salary_range`), `message` > 300 — 422; срок — `limits.interest_validity_days` (7). Повтор отметки, пока интерес компании кандидату открыт, возвращает его же (`Idempotent-Replay: true`, без события и расхода лимита); идёт приглашение — 409 `offer_exists`. Лимит — `limits.interest_company_per_week` (30) за скользящие 7 дней → 429 `interest_limit_exceeded` с `Retry-After`; входящий суточный лимит кандидата общий с офферами, суточный лимит офферов компании интересы не тратят. `GET /candidates/me/interests` — открытые интересы (`interest|interest_opened`, срок не вышел) с агрегатом; в `GET /candidates/me/offers` интерес попадает только после приглашения. `POST /interests/{id}/open` (`interest → interest_opened`, ход компании; повтор — no-op; закрытый — 409), `POST /interests/{id}/decline {reason, comment?}` (`DeclineReason`; для интереса: вилка `low_salary`, формат `wrong_format`, компания `wrong_company` — новое значение, не ищу `not_looking`; повтор с той же причиной — no-op, с другой — 409). `POST /interests/{id}/invite` — только после «открыть» (иначе 409 `interest_not_opened`), без вакансии нужен `title` (422 `title_required`), вилку можно уточнить; срок становится `offer_validity_days`, ставится `invited_at`; повтор — no-op. Отзыв интереса — `POST /offers/{id}/withdraw`. Чужой или не интерес — 404 `interest_not_found`. Принять интерес напрямую и писать в чат до приглашения нельзя (409). Контакты — только после принятия приглашения. Истечение — тот же cron `offers.expire_due()`. В `OfferOut` поля `interest_at`, `interest_opened_at`, `invited_at`.

Задача в приглашении (E33-3, ADR-026): `task {family_id, deadline_days}` — семейство из конструктора компании (E30-1) или банка. Проверка до создания оффера: чужое — 404 `not_found`, свой черновик (не «Готово») — 409 `task_not_ready`, дольше 15 минут — 422 `task_too_long`, срок вне 1–14 дней — 422 `invalid_task_deadline`, банк блока 1 недоступен — 503 `task_bank_unavailable` (оффер не создаётся); повтор по `Idempotency-Key` задачу не дублирует. Срок считается от отправки приглашения. Кандидат: `GET /offers/{id}/task` — вариант без ключа (сид от пары кандидат × оффер; `item = null`, если ответ принят, срок вышел или оффер закрыт; интерес и чужой оффер — 404), `POST /offers/{id}/task/answer` — один ответ, повтор возвращает принятый (`Idempotent-Replay: true`), после срока 409 `task_deadline_passed`, закрытый оффер — 409 `offer_closed`. Решать можно и после принятия; принять приглашение можно без решения. Оценку и доказательство `task` в профиль (`fact_id` = оффер, один раз) делает блок 1 внутри `submit` порта `offers/invite_task.py` (`TaskBank` → `assessment.service.invite_task_describe|item|submit`, заявка З-2-02). Результат — `OfferForCompany.task {…, family_id, answer}` только у компании этого оффера (чужой оффер — 404), у кандидата — `OfferForCandidate.task` без ответа. Таблица `offer_tasks` (миграция `b2_12`).

«Почему вы» (E33-2): `OfferForCandidate` (интерес и приглашение работодателя: `GET /candidates/me/interests`, `/candidates/me/offers`, `/offers/{id}`) несёт `why_you: {factors[{code grade|skills|salary|format, text, weight}] (топ-3 по весу), unconfirmed[text]}` и `company.reliability: {responsibility_score, response_rate, avg_response_hours, sample}`. Факторы считаются по данным самого кандидата и вакансии: грейд из теста против диапазона вакансии, подтверждённые навыки (доверие ≥ 0.5), вилка против `salary_min`, формат; `unconfirmed` — неподтверждённые обязательные навыки и расхождения (вилка ниже ожиданий, формат, грейд). У отклика кандидата `why_you = null`. Рейтинг: доля ответов и средний срок по откликам кандидатов и открытым интересам компании за 90 дней; при выборке < 3 доли и срока нет (`null`, без штрафа). Данных других кандидатов нет. Код — `services/core/app/offers/why.py`.

Реализовано (E32-5a): `salary_basis` (`gross` — до НДФЛ, по умолчанию, или `net` — на руки) у вакансий (`POST|PATCH /vacancies`, ответы `VacancyOut`, `PublicVacancyOut`) и офферов (`POST /offers`: пусто — из вакансии, иначе `gross`; отклик наследует вакансию; ответы `OfferOut`; в `notify.telegram` `offer_new` и `/internal/tg/offers` — поле `salary_basis`, бот подписывает «до НДФЛ» / «на руки»). `POST /offers/{id}/contacts/revoke` (роль `candidate`, свой оффер, иначе 404; нет раскрытия — 409 `contacts_not_revealed`; повтор — no-op) → `OfferForCandidate` с `contacts_revoked_at`; после отзыва `GET /offers/{id}/contacts` у компании — 409 `contacts_revoked`, `contacts` в `GET /offers/{id}` пуст. `PATCH /companies/me` поле `show_verified_badge` (по умолчанию `true`): `verified` в `CompanyBrief` и `PublicCompany` = компания верифицирована админом и не скрыла метку.

Реализовано (E20-12): `PATCH /companies/me` дополнительные поля `contacts` (`{name?, email?, phone?, telegram?}`) и `direction` (направление деятельности); обновляются в том же эндпоинте вместе с `name`, `inn`, `site`, `description`. Используются в приглашениях и профиле компании.

Реализовано (E39-24): роли компании — владелец (`company_members.role = admin`, создатель компании) и HR (`member`). HR видит подбор, шорт-лист, приглашения кандидатам, но не правит компанию: `PATCH /companies/me`, приглашения и состав команды — только владелец, иначе `403 forbidden`. `GET /companies/me` отдаёт `my_role`; `description` — Markdown (≤ 5000), фронт рендерит его `Markdown`, правит `MarkdownEditor`. Команда: `GET /companies/me/members` → `CompanyTeamOut` (`members[]`: `user_id`, `role`, `email`, `full_name`, `position`, `avatar_url`, `is_me`; `invites[]` — действующие приглашения, HR получает `[]`; `can_manage`). `POST /companies/me/invites` `{email}` (лимит 30/час на компанию, `429`) → `201 InviteCreated` (`id`, `email`, `created_at`, `expires_at`, `url` — ссылка `/invite/company/{token}`, токен показывается один раз, в БД — sha256); письмо со ссылкой уходит через SMTP; повтор на тот же email отзывает прежнюю ссылку; участник команды — `409 already_member`. Срок — 7 дней. `DELETE /companies/me/invites/{id}` — отзыв (чужое или принятое — `404 invite_not_found`, повтор — no-op). `DELETE /companies/me/members/{user_id}` — убрать HR (чужой — `404 member_not_found`, владельца — `409 owner_cannot_be_removed`). `GET /company-invites/{token}` без авторизации → `InvitePreview` (`company_name`, `company_verified`, `inviter_name`, `email_masked`, `expires_at`); неверный, отозванный, истёкший или принятый токен — `404 invite_not_found`. `POST /company-invites/{token}/accept` (роль `employer`) → `CompanyOut`: email аккаунта должен совпасть с адресом приглашения (`403 invite_email_mismatch`), состоит в другой компании — `409 already_member`. Личный профиль (роли `employer`, `fsp_admin`): `GET|PATCH /me/profile` → `UserProfileOut` `{full_name (≤120), position (≤120), about (≤2000), avatar_url}`, пустая строка или `null` очищает; `PUT /me/avatar` (multipart `file`) — PNG, JPEG или WebP по сигнатуре (`415 unsupported_file_type`), до 2 МБ (`413 file_too_large`), пустой — `422 empty_file`, лимит 20/час; файл в MinIO `avatars/{user_id}/{sha256[:16]}.{ext}`, старый удаляется; `DELETE /me/avatar` — убрать. `GET /users/{id}/avatar?v=` без авторизации (`<img>` не несёт токен) — только сотрудники компаний и админ ФСП, иначе `404 avatar_not_found`; `Cache-Control: public, max-age=86400`, `nosniff`. Подпись приглашения: `OfferOut.sender` `{full_name, position, avatar_url}` — сотрудник, создавший интерес или приглашение (`initiator = employer`), без email и телефона; нет ФИО в профиле — `null`. `CompanyBrief.description` — «О компании» в приглашении кандидату. E40-1: `CompanyBrief.demo` (кандидат не демо, компания демо) и `PublicCompany.demo` (компания демо) — фронт показывает пометку «демо».

Реализовано (E41-16): доступ HR передаёт владелец, без почты. `POST /companies/me/hr` `{email, full_name (2..120)}` (только владелец, иначе `403`) создаёт аккаунт `employer` сразу (email считается подтверждённым, `users.managed_by_company_id` = компания), добавляет его в команду (`member`), пишет имя в `user_profiles` и возвращает `201 HrAccessCard` `{user_id, email, full_name, login_url, temp_password, expires_at}` с `Cache-Control: no-store`: `login_url` = `WEB_BASE_URL` + `/login`, временный пароль — 12 символов без похожих (`xxxx-xxxx-xxxx`, `secrets`), в БД только argon2-хеш, действует 72 ч. Email кандидата — `409 email_is_candidate`, другого аккаунта — `409 email_taken`, уже в команде — `409 already_member`; аккаунт, которому эта же компания отозвала доступ, включается снова с новым паролем. `POST /companies/me/members/{user_id}/password` → `HrAccessCard`: новый временный пароль, прежний пароль и все refresh-сессии HR гаснут сразу; не участник компании — `404 member_not_found`, владелец или HR, зарегистрировавшийся сам, — `409 not_managed`. Создание и сброс — общий лимит 20/час на компанию (`429`). `DELETE /companies/me/members/{user_id}` отзывает доступ: участник удаляется, refresh-токены отзываются, аккаунт от владельца выключается (`is_active=false`) — вход и действующий access-токен дают `401`. Журнал `GET /companies/me/access-log` → `AccessLogEntry[]` `{id, action: created|password_reset|revoked, created_at, actor_name, target_email, target_name}`, новые первыми, только владельцу; паролей в журнале нет. Вход временным паролем: `user.must_change_password=true` в ответах `/auth/*` и `/me`; до смены пароля все эндпоинты, кроме `/me`, `POST /auth/password/initial` и входа, обновления и выхода (`/auth/login|refresh|logout`), отвечают `403 password_change_required`, фронт ведёт на `/password/new`; после 72 ч `POST /auth/login` временным паролем → `401 temp_password_expired`. `CompanyMemberOut` для владельца — `managed`, `must_change_password`, `temp_password_expires_at` (HR получает `false`/`null`). Приглашения по ссылке (`/companies/me/invites`) помечены `deprecated`, из интерфейса убраны; `/company-invites/{token}` работает для выданных ссылок до истечения.

Реализовано (E6-2): `POST|GET /vacancies`, `GET|PATCH|DELETE /vacancies/{id}`, `POST /vacancies/{id}/publish|close` (роль `employer`, доступ участникам компании-владельца, чужая или несуществующая вакансия → 404 `vacancy_not_found`; нет компании → 404 `company_not_found`). Тело: `title, role, grade_min, grade_max, formats[], employment_type, city?, salary_from, salary_to, description?, important_qualities[], skills[{slug, required=true, min_level=2 (1–4), weight=1.0 (0–3]}]`; slug синонима-слияния приводится к живому навыку, неизвестный или `rejected` — 422 `unknown_skill`, повтор — 422 `duplicate_skill`; `grade_min > grade_max` — 422 `invalid_grade_range`, `salary_to < salary_from` — 422 `invalid_salary_range`. В ответе есть `range_too_wide` (`salary_to / salary_from > 1.6`, предупреждение, не блокирует). Статусы: `draft → published → closed`; `PATCH` (поля и/или полный список `skills`) — только `draft|published`, иначе 409 `invalid_status`; `DELETE` — только черновик (204), иначе 409. `publish`: только `verified` компания (иначе 403 `company_not_verified`) и минимум один обязательный навык (иначе 422 `no_required_skills`); повторные `publish` и `close` идемпотентны. `version` растёт на каждое изменение и на смену статуса; в outbox уходят `vacancy.published` (при публикации), `vacancy.updated` (правка опубликованной), `vacancy.closed`, всё `{vacancy_id, version}`. `POST /vacancies/from-query` и `embedding` — позже (E7-x, E10-x).

Реализовано (E7-3): `POST /search/candidates` (роль `employer`, нужна компания, иначе 404 `company_not_found`; `verified` не требуется). Тело: `{filters, sort=match, cursor, limit=20 (1–100), vacancy_id?, session_id?}`; ответ `{items: CandidateCard[], next_cursor, total, session_id}`. `vacancy_id` чужой или несуществующий — 404 `vacancy_not_found`. Фильтры: роль (`primary_role`), грейды (диапазон), форматы и типы занятости (пересечение), `salary_max` (кандидаты без вилки подходят), города (город совпал или кандидат готов к релокации), `relocation_ok`, `active_only`, `skills_must` с `min_level` и `min_trust` (уровень ≥ порога; неизвестный slug — пустая выдача), `fsp_only`, `fsp_disciplines`. Всегда скрыты: `dnd`, удалённые, анкеты без роли, кандидаты со стоп-листом этой компании. Сортировки: `trust` (среднее доверие по пяти сильнейшим навыкам), `fresh` (`updated_at`), `match` — с `vacancy_id` скор подбора (у кандидатов, не прошедших жёсткие фильтры вакансии, `match: null`, они идут в конце), без вакансии покрытие `skills_must`/`skills_nice` по доверию. Курсор непрозрачный (сортировка + ключ + `pseudo_id`), несовпавший или битый курсор — первая страница. `semantic_text` пока не используется. Страница кешируется на 60 с (messaging.md §6); `catalog_version` считается от числа живых анкет и максимального `updated_at`. `session_id` пока только генерируется (запись показов — E17-1). В `CandidateCard` нет `user_id`, имени, контактов, компаний и репозиториев.

Видимость v2 (E20-11, E23-1, blocks.md §4.5, ADR-018): в выдаче (поиск, подбор под вакансию, «похожие») и в `GET /candidates/{pseudo_id}/card` только кандидаты с **действующим грейдом из теста** (`assessment.service.get_grades_many`) и согласием `profile_publication`; иначе карточка — 404 `candidate_not_found`. Резюме без теста категории не даёт. Фильтр `category: {profession, grade}` (грейд `junior|middle|senior`, иначе 422) оставляет только участников категории (`category_members`). Карточка несёт `categories: CategoryRef[]` — подтверждённые тестом профессия × грейд. Ключ кеша выдачи включает отпечаток согласий и `category_counts`. Сила профиля (E23-2, assessment.md §9): карточка выдачи несёт `strength: {value, rank, top[{code T|F|S|R|C, text, value, weight}]}` (топ-3 слагаемых по вкладу); `rank = 0.6·match + 0.4·strength` считается и задаёт порядок только при фильтре `category` (без него `rank = null`, порядок прежний). Нет действующего грейда выбранной профессии — `strength = null`. Создание оффера по `pseudo_id` пока проверяет только базовую доступность анкеты (dnd, роль, стоп-лист).

Потребности и категории (E23-4, assessment.md §9; роль `employer`, нужна компания; чужая потребность → 404 `need_not_found`): `POST /needs {text?, filters?: SearchFilters}` → 201 `{id, text, filters, skills{slug: вес}, grades[], shortlist[], created_at, categories[]}` — текст разбирается как в `/search/parse` (правила + LLM), поля `filters` перекрывают разобранное; ни навыков, ни роли, ни `professions` → 422 `need_empty`. `GET /needs/{id}/categories` → `{need_id, shortlist[], categories[{profession, title, grade, affinity, candidates, median_salary, fsp_share, matched_skills[], named}]}`: профессии с `affinity ≥ 0.4` (нет таких — лучшая с affinity > 0; роль, названная в потребности, попадает всегда) × грейды потребности (без `grade_min/max` — все три); фильтр `professions` (E39-21) задаёт профессии явно — категории только по ним (неизвестный slug пропускается); `candidates` — видимые работодателю (грейд из теста + `profile_publication`, фильтры анкеты потребности и те же `min_trust`, `fsp_only`, `only_confirmed`, `salary_min`, что у выдачи категории — `search.extra_ok`), `median_salary` — при ≥ 3 ожиданиях, `fsp_share` — доля с ФСП (пустая категория — `null`); «почему эта категория» (E39-21): `matched_skills` — названия навыков запроса, которые есть у профессии, по вкладу в affinity (до 5), `named` — профессия названа в запросе или выбрана фильтром. `GET /categories/{profession}/{grade}/candidates?need_id=&session_id=&cursor=&limit=` → `{items: CandidateCard[], next_cursor, total, session_id}` (E17-5: показы пишутся как impressions, `session_id` — для `POST /recs/feedback`; следующие страницы передают его обратно); карточка несёт `is_shortlisted: bool` (E23-5); порядок по `rank`, объяснение — `strength.top`; навыки потребности идут как «желательные» (покрытие входит в `match`, выдачу не обнуляет); неизвестный грейд или slug → 422 `invalid_category`. `POST /needs/{id}/shortlist/{pseudo_id}` / `DELETE /needs/{id}/shortlist/{pseudo_id}` (204, E23-5): добавить/удалить кандидата в шорт-лист потребности; несуществующий кандидат или потребность → 404. Фильтр не сбрасывает отмеченных (E23-5). `GET /shortlist` (E39-23, `employer`) → `{items: [{pseudo_id, need_id}]}`: отмеченные во всех потребностях компании без повторов (свежие потребности первыми), `need_id` — откуда удалять; экран `/employer/shortlist` не зависит от запроса, сохранённого в браузере. Параметры — `data/scoring.yaml`, секция `needs`; таблица `needs`.

Подписка на категорию (E33-4; роль `employer`, нужна компания): `POST /subscriptions {profession, grades[]?, skills[{slug, min_level 1–4}]?, salary_max?, formats[]?, only_confirmed?}` → 201 `{id, profession, grades[], skills[], salary_max, formats[], only_confirmed, created_at}`; неизвестная профессия — 422 `invalid_category`, неизвестный навык — 422 `invalid_skill`, больше `needs.max_subscriptions` (20) на компанию — 429 `subscription_limit`. `GET /subscriptions` — подписки компании, `DELETE /subscriptions/{id}` (204; чужая или несуществующая — 404 `subscription_not_found`). Пустой `grades` — любой грейд; `salary_max` — бюджет: кандидат подходит, если ожидания не выше или не указаны; `only_confirmed` — грейд без `needs_confirmation` и `low_confidence`; `min_level` — уровень доверия навыка кандидата. По `candidate.category.changed` кандидат (видимый работодателю, не в стоп-листе компании, не `dnd`) сверяется с подписками на его категории; подошедший пишется в `category_subscription_hits` (повтор не дублирует), участникам компании уходит уведомление `category_subscription` (SSE `notification.new` + бот, шаблон `category_subscription`) с числом и `pseudo_id` (до 5), не чаще `needs.subscription_digest_minutes` (60) на подписку; накопленное досылает cron `offers.expire` (SSE при этом не публикуется, уведомление видно в ленте).

Встречный сигнал кандидата (E33-6; роль `candidate`): `POST /companies/{company_id}/interest` → 200 `{created_at}` — «интересна компания», повтор идемпотентен и не меняет `created_at`; `DELETE /companies/{company_id}/interest` → 200 `{removed: bool}` — снять отметку. Неизвестная или неподтверждённая компания — 404 `company_not_found`, не кандидат — 403. В выдаче `POST /search/candidates` именно этой компании отметивший кандидат получает `interested_you: true` («вами интересовался») и множитель к порядку `scoring.yaml: matching_weights.candidate_interest_boost` (1.05, детерминированно; на сам `match.score` не влияет); другие компании отметку не видят.

Реализовано (E7-5): `POST /search/parse` (роль `employer`) `{text (1–500)}` → `ParsedQuery`; правила, затем LLM-уточнение через ml-api `/v1/query/parse` (E7-6, `ML_API_URL`, таймаут `QUERY_PARSE_TIMEOUT_SECONDS`=5): правила главнее (деньги, форматы, города, грейд, флаги), LLM добавляет роли, навыки из справочника и `semantic_text`, расхождения — чипс `?` (`source=llm`, `confidence=0.3`), `refining=true`; ответ кешируется в Redis `c:qparse:{tax_v}:{sha}` на 24 ч; недоступная или невалидная LLM — деградация до правил (`refining=false`), не ошибка. Код — `app/matching/query_llm.py`. Правила — `app/matching/query_parser.py`, справочник синонимов — `taxonomy.service.alias_index` (slug, название, синонимы живых навыков; неоднозначная форма отбрасывается). Распознаём: роль (`roles`; навык, чей slug совпал с ролью, становится ролью), грейд (`мидл`, `senior`, `джун+`, `senior+` = senior…lead, диапазон `middle-senior` / «от middle до senior» → `grade_min`/`grade_max`), навыки (`skills_must`; после «желательно» или перед «плюсом» — `skills_nice`), формат, тип занятости («стажёр» ставит ещё и `grade intern`), бюджет (`до 250к`, `200-250 тыс`, `до 1,5 млн`, `300000 ₽` → `salary_max`), город, `relocation_ok`, `active_only`, `fsp_only`. Фраза «от 150 000» фильтром не выражается и уходит в `unparsed`. Нераспознанные значимые слова — `semantic_text`. Чипсы атомарные: по одному на роль, навык, формат, город; `value` — одно значение (`"python"` для роли, `{slug}` для `skills_must`, строка для `skills_nice`, число для `salary_max`), `source=rule`, `confidence` 0.5–0.9.

Реализовано (E7-4): `GET /candidates/{pseudo_id}/card?vacancy_id=&source=` (роль `employer`, нужна компания) → `CandidateCardFull`: поля `CandidateCard` + `skills` (`SkillWithTrust`, до 3 кратких доказательств; заголовок — общий по источнику, для ФСП название соревнования, без ссылок и названий репозиториев), `grade_info`, `experience` (`months`; `company` только при `visibility.companies`; образования нет), `full_name` (E36-5: только при `visibility.full_name`, иначе `null`; контактов в карточке нет никогда — они открываются принятием приглашения или откликом, `GET /offers/{id}/contacts`). При `visibility.fsp=false` из карточки и выдачи убраны не только `fsp_highlights`, но и источник `fsp` в `sources`/`top_evidence` навыков, сигналы `fsp_*` в `grade_info.breakdown` и слагаемое `F` в `strength.top`; `region=false` обнуляет `city`. `offers_from_you` (`{id, status}` офферов этой компании этому кандидату). `code` пока не отдаётся (нет модуля анализа кода). С `vacancy_id` заполняется `match`. Скрытая анкета (`dnd`, удалена, без роли, стоп-лист компании), несуществующий `pseudo_id`, чужая вакансия — 404 (`candidate_not_found` / `vacancy_not_found`). `source` — `search|match|similar|direct` (по умолчанию `direct`). Каждый успешный запрос пишет строку в `profile_views` (повторные открытия тоже). `GET /candidates/me/views` (роль `candidate`) → `ProfileViewsStats` `{total_30d, companies_30d, window_days, visible, by_day[{date, count}]}` — только числа, названий компаний нет; `by_day` — полная шкала 30 дней (нули для дней без просмотров), `visible=false`, пока нет действующего грейда или согласия `profile_publication` (E43-5).

Реализовано (E8-1): `POST /offers` (роль `employer`, `Idempotency-Key` обязателен, иначе 422 `idempotency_key_required`), `GET /offers?status=&vacancy_id=` (до 100, новые первыми), `GET /offers/{id}` (кандидат: первое открытие `sent → viewed`; чужой оффер любой стороной — 404 `offer_not_found`), `GET /candidates/me/offers`, `POST /offers/{id}/accept|decline|withdraw|status`. Ответы: `OfferForCompany` (`candidate` — анонимный `CandidateCard`; `contacts` только в `GET /offers/{id}` после принятия), `OfferForCandidate` (`company`). Создание: компания `verified` (иначе 403 `company_not_verified`), вакансия своя и `published` (иначе 404 `vacancy_not_found` / 409 `vacancy_not_published`), кандидат виден в поиске для этой компании (иначе 404 `candidate_not_found`); тело `{vacancy_id, candidate_pseudo_id, salary_from, salary_to, message?}`, вилка обязательна (422 `salary_range_required`, `salary_to < salary_from` — 422 `invalid_salary_range`; `range_too_wide` не блокирует); второй оффер по той же вакансии тому же кандидату — 409 `offer_exists`. Лимиты за скользящие 24 ч по БД (`scoring.yaml` `limits`): 20 офферов на компанию (429 `offer_limit_exceeded`), 10 входящих на кандидата (429 `candidate_offer_limit_exceeded`), оба с `Retry-After`. Повтор запроса с тем же ключом и теми же вакансией и кандидатом возвращает исходный оффер (проверяется до лимитов), с другими — 409 `idempotency_key_reused`. Срок жизни — `offer_validity_days` (7); `match_snapshot` берётся из `matches`; `below_candidate_min = salary_to < salary_min`. Автомат — flows.md F8: ответ кандидата (`accept`, `decline {reason, comment?}`) из `sent|viewed`, `withdraw` — из `sent|viewed`, `status` — только `interview|hired|not_hired` (`accepted → interview|not_hired`, `interview → hired|not_hired`); запрещённый переход — 409 `invalid_transition`, ответ или отзыв после срока — 409 `offer_expired`. Каждый переход пишет `offer_events` и `offer.sent|viewed|accepted|declined|withdrawn|expired|status_changed` в outbox в той же транзакции. `salary-hint` и `team-offers` — E8-4, E15-2; перевод `sent|viewed → expired` по времени — `offers.expire_due()` (вызовет cron E8-5).

Реализовано (E15-2): `GET /teams` (роль `employer`) — участник виден, если не `dnd`, есть роль, компания не в его стоп-листе и `visibility.teams` не выключен; скрытые не раскрываются, команда показывается при ≥2 видимых участниках; `discipline` — по соревнованию команды, `min_place` — лучшее место в `fsp_results` с этим `team_id` не хуже заданного. `POST /team-offers` (`Idempotency-Key` обязателен, почта подтверждена): вакансия своя и опубликована, команда видимая, участники из `salary_per_member` — разные (≥2, иначе 422 `team_members_invalid`) и состоят в команде (404 `candidate_not_found` / `team_not_found`). Создаёт по обычному офферу на участника (те же проверки, лимиты и события `offer.sent`) с общим `team_offer_id`; всё в одной транзакции, ошибка на любом участнике откатывает все. Ключ идемпотентности оффера участника — `<ключ>#<pseudo_id>`, повтор возвращает исходные офферы с `Idempotent-Replay: true`. Каждый участник принимает/отклоняет свой оффер; `team_offer_id` отдаётся в `OfferOut`.

Реализовано (E20-2, ADR-022): приглашение без вакансии. `CreateOffer`: `vacancy_id` необязателен, новые поля `title` (≤ 200), `description` (≤ 4000), `contact_method` (`platform|email|phone|telegram`); без вакансии нужен `title` (422 `title_required`), вилка обязательна как раньше. Перед созданием — `identity.require_verified_email` (403 `email_not_verified`, пока `EMAIL_VERIFICATION_REQUIRED=false` — пропускает). Второе открытое (`sent|viewed`) приглашение без вакансии той же компании тому же кандидату — 409 `offer_exists`; повтор по `Idempotency-Key` — исходный оффер. В ответах `Offer*`: `vacancy` может быть `null`, добавлены `title` (без своего — название вакансии), `description`, `contact_method`, `initiator` (`employer|candidate`). Принятие и раскрытие контактов — тот же автомат. События `offer.*` — `schema_version: 2` (messaging.md §2.1).

Реализовано (E8-6, минимум): `POST /offers/salary-hint` (роль `employer`, своя вакансия, кандидат виден компании, вилка обязательна) → `SalaryHint`: `p_accept` — детерминированная формула [matching.md §4.1](matching.md#41-взаимный-подбор-интерес-кандидата) (`app/matching/p_accept.py`, коэффициенты и пороги — `scoring.yaml` `p_accept`; `company_rating` берётся из `responsibility_score`, `stack_interest` — доля `primary_stack` кандидата среди навыков вакансии), `acceptance_hint` по порогам 0.35/0.65, `below_candidate_min`, `range_too_wide` (>1.6); `category_median` — медиана `salary_min` анкет в ячейке role×grade (нужно ≥ 3 анкет, иначе `null`), `vs_category_median = salary_to / median − 1`. Реализовано (E33-5): `salary-hint` работает и для интереса/приглашения — `vacancy_id` необязателен (без него формат и стек в `p_accept` не учитываются); в `SalaryHint` добавлены `suggested_salary_to` и `suggested_p_accept` (минимальный верх вилки с шагом 5 % до +40 %, округление вверх до 5000 ₽, при котором `p_accept` достигает порога «высокая», а для «низкой», если это недостижимо, — «средней»; иначе `null`) и `avg_response_hours` (средний срок ответа кандидатов роли на приглашения, нужно ≥ 3 ответов; иначе `null`); параметры — `scoring.yaml` `p_accept.forecast`. Реализовано (E18-6): сортировка `mutual` — `H = 2·score·p_accept / (score + p_accept)` (`mutual()` в `p_accept.py`); без `sort` в теле при `vacancy_id` — `mutual`, без вакансии — `match`; `mutual` без вакансии сводится к `match`; не прошедшие жёсткие фильтры вакансии идут в конце. В `CandidateCard.match` и в полной карточке с `vacancy_id` поле `interest` (`low|medium|high`) — интерес кандидата при вилке вакансии. `GET /offers/{id}/events` — таймлайн для обеих сторон.

Страница приглашения (E41-4): переписки нет. Сопроводительное компании — `message` приглашения; кандидат принимает или отклоняет без текста (`POST /offers/{id}/accept` без тела, `decline` игнорирует `comment`), после принятия — блок контактов. `POST /offers/{id}/messages` оставлен только для сопроводительного компании. Бот переписку не поддерживает: кнопки «Задать вопрос» и `POST /internal/tg/offers/{id}/messages` убраны. `OfferForCandidate.company_contacts {name, email?, phone?, telegram?}` — контакты компании (из `companies.contacts`, запасная почта — аккаунт подписанта) только после принятия и пока кандидат не отозвал доступ; у `Contacts` кандидата (`OfferForCompany.contacts`, `GET /offers/{id}/contacts`) к почте и Telegram добавлен `phone` — из профиля кандидата, с запасом на данные аккаунта. Фронт: кнопка «Написать в Telegram» — `https://t.me/<ник>`.

Реализовано (E41-12): аватары и логотипы. `PUT /companies/me/logo` (multipart `file`, только владелец; `415 unsupported_file_type`, `413 file_too_large`, `422 empty_file`, лимит 20/час) и `DELETE /companies/me/logo` → `CompanyOut`; в `CompanyOut` вместо `logo_key` поле `logo_url` (`/companies/{id}/logo?v=`), файл в MinIO `logos/{company_id}/{sha256[:16]}.{ext}`; `GET /companies/{id}/logo` без авторизации (логотип публичен), `Cache-Control: public`. `logo_url` также в `CompanyBrief`, `PublicCompany` и `GET /me` → `company.logo_url`. Аватар кандидата: `PUT|DELETE /candidates/me/avatar` → `CandidateProfile` (поле `avatar_url`, только владельцу), файл `candidate-avatars/{user_id}/{sha256[:16]}.{ext}`, стирается вместе с профилем (`DELETE /candidates/me`). `avatar_url` кандидата — `/candidates/{pseudo_id}/avatar?v=&sig=`, где `sig` = HMAC(`jwt_secret`, `avatar:{pseudo_id}:{key}`)[:32]: смена файла меняет подпись и гасит старые ссылки; неверная подпись и отсутствие файла — одинаковый `404 avatar_not_found`. Работодателю `CandidateCardFull.avatar_url` отдаётся только после приглашения от его компании (строже ФИО: `visibility.full_name` его не открывает); в `CandidateCard` (выдача) и в анонимные DTO его нет. `GET /me` → `avatar_url` (сотрудник — личное фото, кандидат — со строкой доступа). PDF-профиль владельца вшивает аватар.

Работодатель без компании (E39-7): списки `GET /offers`, `GET /vacancies`, `GET /subscriptions`, `GET /employer/tasks` отвечают `200 []`, `GET /employer/activity` — `200 {items: []}` (раньше 404 `company_not_found` падал в консоль нового аккаунта). Запись и карточки (`POST /subscriptions`, `POST /needs`, `GET /companies/me` и др.) по-прежнему 404 `company_not_found`; наличие компании фронт берёт из `GET /me` (`company`).

Реализовано (E20-3, ADR-022): отклик кандидата — оффер с `initiator = candidate` (`offers.service.apply`). `POST /vacancies/{id}/apply` (роль `candidate`): вакансия не `published` или не найдена — 404 `vacancy_not_found`, компания в стоп-листе — 409 `company_in_stoplist`, повтор (в том числе после приглашения на ту же вакансию) — 409 `already_applied`, лимит `application_candidate_per_day` (20 за 24 ч) — 429. Статус `sent`, `awaiting_reply_from = company`; контакты раскрываются сразу (`contact_reveals` создаётся при отклике — отклик есть согласие кандидата). Компания видит отклик в `GET /offers?initiator=candidate`, первое открытие `GET /offers/{id}` переводит `sent → viewed`; дальше `POST /offers/{id}/status` `interview|not_hired` (из `sent|viewed`), `interview → hired|not_hired`; `accept`, `decline` и `withdraw` компании на отклик — 409 `invalid_transition`. Кандидат отзывает отклик через `/candidates/me/applications/{id}/withdraw`. Статусы видны обеим сторонам (`GET /offers/{id}`, `/candidates/me/applications`). События `offer.*` с `initiator = candidate`; уведомление «Новый отклик» уходит компании, в метрики офферов и меню бота отклики не входят; лимиты приглашений отклики не считают. `GET /vacancies/public` объявлен раньше `/{vacancy_id}`. Роль вакансии (`role`) — профессия из справочника (`roles.is_profession`) или старый `RoleSlug`; создание и правка с неизвестной ролью — 422 `unknown_role` (E39-17).

Реализовано (E8-2): при переходе в `accepted` в той же транзакции создаётся `contact_reveals` (одна строка на оффер). `GET /offers/{id}/contacts` (роль `employer`, свой оффер) → `{name, email?, phone?, telegram?}`; до принятия или после отказа — 409 `contacts_not_revealed`, чужой оффер — 404; каждое чтение пишет в лог `contacts.viewed` (offer, компания, пользователь, без ПДн). Пока анкета не хранит `full_name_enc`/`contacts_enc`, `name` — псевдоним, `email` — почта аккаунта, `telegram` — `@username` привязанного бота, `phone` пуст. `GET|POST /offers/{id}/messages` (обе стороны; `{text}` 1–2000 символов; чужой оффер — 404): писать можно в `sent|viewed|accepted|interview`, иначе 409 `offer_closed` (после срока — 409 `offer_expired`), пустой текст — 422 `empty_message`, лимит 30 сообщений в час на пользователя и оффер (429 + `Retry-After`); в `accepted|interview` `awaiting_reply_from` переключается на другую сторону; событие `offer.message` с `message_id` уходит в outbox. `POST /offers/{id}/complaint` (роль `candidate`, свой оффер; `{reason, comment?}`, `reason` ∈ `spam|discrimination|fake_company|salary_mismatch|abuse|other`, иначе 422 `invalid_reason`): 201 `{id, offer_id, reason, status: open, created_at}`, повторная жалоба на тот же оффер — 409 `complaint_exists`; разбор — `/admin/complaints`.

Реализовано (E13-1b): `GET /admin/complaints?status=open|resolved|dismissed` (роль `fsp_admin`, новые сверху, до 100; `{id, offer_id, company_id, company_name, reason, comment, status, created_at}`, без данных жалобщика), `POST /admin/complaints/{id}/resolve` `{decision?: resolved|dismissed}` (по умолчанию `resolved`; повтор того же решения идемпотентен, смена решения — 409 `invalid_status`; нет жалобы — 404 `complaint_not_found`). Модерация компаний — E6-1 (выше).

### 2.6. Администратор ФСП

| Метод и путь | Назначение |
|---|---|
| `GET|POST|PATCH /admin/skills`, `…/aliases`, `…/relations` | Граф навыков: вершины, синонимы, связи |
| `GET /admin/skills/queue` | Очередь слияний («то же», уверенность 0.6–0.9) с превью «что объединится»; `POST /admin/skills/queue/{slug}/approve` — слить в предложенный навык, `…/reject {mark_distinct}` — оставить отдельным (E16-7) |
| `POST /admin/skills/{slug}/approve|reject`, `POST /admin/skills/merge {from, into}`, `GET /admin/skills/merges`, `POST /admin/skills/merges/{id}/revert`, `GET /admin/skills/provisional` | Решения админа по графу: временный навык (с черновиком карточки), ручное слияние, журнал и откат. Нет навыка/слияния → 404, пара «точно разные» → 409 `merge_forbidden_distinct`; роль `fsp_admin` |
| `GET|POST /admin/skills/distinct`, `DELETE /admin/skills/distinct?a=&b=`, `GET|POST /admin/skills/blocklist`, `DELETE /admin/skills/blocklist?norm=` | «Точно разные» пары и стоп-лист |
| `GET /admin/skills/graph` | Граф навыков для просмотра: `nodes` (slug, название, тип, статус), `edges` (`adjacent`, `parent`), `version` справочника; роль `fsp_admin` |
| `GET /admin/skills/hints` | Подсказки экспертам (`taxonomy_hints`): правила дисциплин и кандидаты в новые профессии |
| `GET|POST /admin/professions`, `GET|PATCH|DELETE /admin/professions/{slug}` | Профессии теста и веса навыков (E13-1a, `fsp_admin`). POST `{slug, title, skill_weights{slug:вес}}` → 201; PATCH `{title?, skill_weights?}` (веса заменяются целиком); DELETE снимает признак профессии (веса остаются). Веса в (0, 1], навыки живые, покрыты все 6 типов: иначе 422 `invalid_weight` / `unknown_skill` / `missing_skill_types`; повтор слага — 409 `profession_exists`. Ответ — `ProfessionInfo` + `taxonomy_version`; список включает скрытые профессии (`active: false`, E36-2) |
| `GET /admin/profession-suggestions`, `POST /admin/profession-suggestions/{id}/accept`, `POST /admin/profession-suggestions/{id}/reject` | «Новая профессия?» (E41-17, `fsp_admin`; [skills.md §5.1](skills.md#51-предложения-новых-профессий)). GET — открытые предложения по убыванию поддержки: `{id, title, skills[{slug, name, type, share}], support_vacancies, support_needs, nearest{slug, title, overlap}?, examples[{vacancy_id?, title}], status, profession?, created_at}`. `accept` (тело необязательно: `{slug?, title?}`) создаёт профессию одной кнопкой — профиль навыков собирается сам (ядро + навыки ближайшей профессии для типов без семейств) → 201 `{suggestion, profession: ProfessionOut}`; ошибки создания — как у `POST /admin/professions`. `reject` → `ProfessionSuggestionOut`, похожий кластер больше не предлагается. Нет предложения → 404, решение уже принято → 409 `suggestion_decided` |
| `GET /admin/skill-cards`, `GET|PUT /admin/skill-cards/{slug}` | Карточки навыков (E13-1a). `source`: `admin` (правка в `scoring_config`, ключ `skill_card:<slug>`, своя `version`), `file` (`data/skills/cards`), `draft` (ml). PUT принимает `SkillCard`; `skill` ≠ путь → 422 `card_skill_mismatch`, `type` ≠ типу навыка → 422 `card_type_mismatch` |
| `GET /admin/skills/growth` | Рост графа: новые вершины и связи за период, доля автоматических решений |
| `GET /admin/discipline-rules/suggestions` | Предложения добавить навык в правило дисциплины (lift по участникам) |
| `GET|PUT /admin/discipline-rules` | Правила «дисциплина → навыки» |
| `GET|PUT /admin/scoring-config` | Веса доверия, грейда, матчинга (с версией) |
| `GET /admin/companies?status=pending`, `POST /admin/companies/{id}/verify|reject` | Модерация компаний |
| `GET /admin/complaints`, `POST /admin/complaints/{id}/resolve` | Жалобы |
| `GET /admin/dashboard?days=30` | Дашборд ФСП (роль `fsp_admin`), `days` 1–180. Когортная воронка по `analytics_events`: регистрация → тест → категория (`category_changed` или `profile_updated.grade_to`) → приглашение (`offer_received`) → ответ; у этапов `count`, `pct_of_registered`, `pct_of_previous`; `fsp_share` (привязали ФСП / зарегистрированные), `navigator_to_competition` (клик `competition_clicked` из навигатора или uplift / увидели `uplift_shown`). Ячейки меньше 5 человек: `count`, `pct` = `null`, `hidden: true`. Демо-аккаунты (`is_demo`) не считаются; `include_demo=true` — с ними (E40-1). Счётчики `counters` (регистрации, тесты, грейды, интересы работодателей, приглашения, принятые приглашения — события за окно) и `daily` (те же счётчики по дням UTC, от старого к новому; день меньше 5 событий — `null`) для страницы «Аналитика» (E41-15). Востребованные навыки и регионы — позже |
| `GET /admin/summary` | «Что требует вас» на главной админки (E39-29, роль `fsp_admin`, [admin.md §3](admin.md#3-главная-что-требует-вас)): `{queues: [{id, count}], total}`, `id` — `fsp_requests`, `families` (статус `pilot`), `skills` (предложенные слияния), `companies` (`pending`), `complaints` (`open`). fsp-connector недоступен — `count: null`, остальные счётчики отдаются |
| `GET /admin/metrics?days=30` | Онлайн-метрики v2 (E31-4, роль `fsp_admin`), `days` 1–180. Считаются на лету по `analytics_events` (metrics.md §9.3): `candidate_funnel` (регистрация → email → опрос → старт теста → завершение → категория; шаги без событий в окне — `available=false`, из цепочки исключены), `employer_funnel` (потребность → категория → шорт-лист → приглашение), `invites` (отправлено/отвечено/принято/отказано/истекло, `accept_rate`, `respond_72h_rate`, время регистрация → первое приглашение и доля с приглашением за 14 дней, потребность → приглашение, причины отказов), `interests` (встречный оффер E33: интерес → открыл → пригласили → приняли, `open_rate`, `invite_rate`, `accept_rate`, время до открытия и приглашения, причины отказов), `responses` (отклик → ответ → принятие, время ответа). Ячейки меньше 5 — `null`, `hidden: true`; псевдонимов и ПДн в ответе нет. Без демо-аккаунтов, `include_demo=true` — с ними (E40-1) |
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
| `GET|POST /admin/fsp/events`, `PATCH /admin/fsp/events/{id}` | Реестр ФСП (E39-28, ADR-052), роль `fsp_admin`: мероприятия `{title, discipline, level, date}` → `RegistryEventOut` (+ `results` — число результатов); 404 `not_found` |
| `GET /admin/fsp/participants?q=&limit=`, `POST /admin/fsp/participants` | Участники реестра `{full_name, email?, phone?}` (контакты нормализуются; дубль по email/телефону → 409 `participant_exists`); поиск по ФИО, email, телефону, ID; `linked` — уже привязан к кандидату |
| `POST /admin/fsp/participants/import` | `{csv}` «ФИО, email, телефон» (`,`/`;`, заголовок необязателен, до 5000 строк) → `{created, updated, errors: [{line, reason}]}`; совпал контакт — обновление |
| `GET /admin/fsp/results?event_id=&participant_id=`, `PUT /admin/fsp/results`, `DELETE /admin/fsp/results/{id}` | Результат «участник × мероприятие» `{participant_id, event_id, place?, team?}` (повтор правит); привязанному кандидату сразу уходит полная синхронизация |
| `POST /admin/fsp/registry/import` | Результаты списком (E43-4): `{csv, commit=false, skip_errors=false, create_events[], default_discipline, default_level}`; CSV `участник;мероприятие;дата;результат[;дисциплина;уровень]` (`;`, `,` или TAB из таблицы, заголовок необязателен, ≤ 1000 строк, иначе 422 `too_many_rows`). Участник — ФИО, email, телефон или ID реестра; место числом, «участие»/пусто — без места. Ответ: `{committed, summary{total,errors,created,updated,unchanged}, new_events[{key,title,date,discipline,level,rows,confirmed}], lines[{line,status,action,error,…}]}`. Без `commit` — превью (dry-run), ничего не пишет; коды ошибок строк: `participant_not_found`, `participant_ambiguous`, `event_ambiguous`, `no_date`, `bad_date`, `bad_result`, `duplicate`, `event_not_confirmed`. `commit` при ошибках без `skip_errors` — 422 `has_errors`. Идемпотентно по ключу участник+мероприятие (повтор — `unchanged`); новое мероприятие создаётся только если его `key` в `create_events`; затронутым кандидатам — пересчёт (`fsp.results.imported` через outbox). Роль `fsp_admin` |
| `GET /admin/fsp/requests?status=`, `POST /admin/fsp/requests/{id}/accept` `{participant_id}`, `POST …/reject` `{reason}` | Очередь заявок; в ответе `candidates` — участники реестра с теми же контактами (подсказка). Принять → привязка `method=registry`; повторное решение → 409 `request_decided` |
| `POST /admin/demo/fsp-result` | Демо: создать результат в моке → вебхук (F11) |
| `POST /admin/demo/reset` | Только при `DEMO_MODE=true`: сброс к снапшоту |

### 2.7. Публичные

| Метод и путь | Назначение |
|---|---|
| `GET /public/stats` | E39-35: цифры лендинга без авторизации и ПДн, кеш Redis 5 минут (`Cache-Control: public, max-age=300`). `PublicStatsOut {candidates, companies, invitations, median_days_to_invite}`: кандидаты с грейдом из теста, компании `verified`, приглашения компаний, медиана дней от первого грейда до первого приглашения; нет данных — `null`, лендинг прячет такой счётчик (и весь блок, если ответа нет). Демо (`is_demo`) не считается (E40-1) |
| `GET /public/badge/{slug}.svg` | Бейдж «Подтверждено ФСП · Middle Backend · ●●●●». Кеш 1 ч |
| `GET /public/credentials/{id}` | **Open Badge 3.0** (W3C VC 2.0, `application/ld+json`, `OpenBadgeCredential`): достижение «Подтверждено ФСП» с категорией и доверием ●●●●. Подпись Data Integrity `eddsa-jcs-2022` (Ed25519, JCS; ADR-051). `404 credential_not_found`, если не выпущен, отозван или профиль не публичный (нет `public_profile` или согласия `profile_publication`). Кеш 60 с |
| `GET /public/credentials/{id}/verify` | Проверка подписи, отзыва и срока: `{id, valid, signature_valid, known, revoked, expired, issuer, checked_at}`. Отозванный бейдж: `200 {valid:false, revoked:true}`; неизвестный или скрытый владельцем: `404` |
| `POST /public/credentials/verify` | Проверка предъявленного документа (тело — сам кредит): подпись по ключу издателя + статус в базе. Подделка, снятая подпись, чужой ключ → `200 {valid:false, signature_valid:false}` |
| `GET /.well-known/did.json` | DID-документ издателя (`did:web:fsp.patissons.tech`), `Multikey` `#key-1` с `publicKeyMultibase`. Ключ — `OB_SIGNING_KEY` (seed Ed25519, base64url; пусто — временный ключ процесса, только для разработки) |
| `POST /track` | Батч событий интерфейса, см. [metrics.md](metrics.md). Тело `{events[1..50]{event, ts, session_id?, run_id?, app_version?, props}, batch_id?, access_token?}` (`actor`, `role`, `channel` от клиента не принимаются → `422`). Авторизация необязательна: роль и псевдоним берутся из Bearer-токена, для `sendBeacon` (без заголовков) токен можно передать в теле; без токена событие анонимное. `202 {accepted, rejected, duplicate}`: событие с неизвестным именем, не из источника `web` или с лишним полем в `props` отклоняется (`rejected`), остальные пишутся. Повтор того же `batch_id` за 10 минут не пишет события (`duplicate: true`). 120 запросов в минуту на пользователя или IP, `429` |
| `GET /public/profiles/{slug}` | Публичный профиль (JSON без ПДн). `404`, если нет `public_profile`, согласия `profile_publication` или действующего грейда (то же для бейджа) |
| `GET /athlete/{slug}` | Краулерам (Telegram, VK, Slack по User-Agent) — HTML с OG-тегами, людям — редирект на `dashboard.fsp…/athlete/{slug}` |
| `GET /taxonomy` | `{version, skills[{slug,name,kind,group,testable}], roles[{slug,name}], disciplines[{slug,name}], grades[], formats[], employment_types[]}` (только `active` навыки). `ETag` `W/"tax-<version>-<хеш статики>"`, `If-None-Match` → 304, `Cache-Control: public, max-age=300` |
| `GET /taxonomy/professions` | Публичный (E21-1). `{professions[{slug,title,skill_weights{slug:вес},skill_types{slug:тип},active,beta}], skill_types[6], grades[{grade,cut}]}`; профессии — роли с `profession: true`, только активные (скрытые `active: false` не отдаются, E36-2; в справочнике открыты все, E39-6); `beta: true` — тонкий банк семейств (есть пустая ячейка «грейд × тип навыка», `families-check` предупреждает), в опросе метка «бета»; каждая покрывает все 6 типов навыков; `cut` — минимальный θ грейда из `scoring.yaml` `assessment.grades` |
| `GET /taxonomy/skills/suggest` | Публичный (E39-3). Query `q` (≤100, пусто — самые частые), `limit` (1–50, по умолчанию 10), `profession` (slug роли: её навыки выше), `kind` (`soft`|`hard`|`domain` — только навыки этого вида; `soft` — поле «Личные качества», E41-6). `[{slug, name, group, provisional, matched, score}]`: точное совпадение → префикс → слово/подстрока → триграммы (опечатки) по названию, slug и синонимам (`пит` → Python, `js` → JavaScript); внутри класса — частота у кандидатов и вакансий (`support_*`) и вес в профессии. Нечёткие совпадения не подтягивают «точно разных» (Java ≠ JavaScript). `provisional: true` — новый навык; слитые и отклонённые не отдаются. Кеш Redis `c:tax:suggest:s:{tax_v}:{sha}` 10 мин |
| `GET /taxonomy/professions/suggest` | Публичный (E39-3). `q`, `limit` как выше. `[{slug, title, score}]` — все видимые роли системы (`is_active`), включая добавленные админом через `/admin/professions`; скрытые не отдаются. Кеш `c:tax:suggest:p:{tax_v}:{sha}` 10 мин |
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
| `POST /internal/tg/token` | bot | `{tg_user_id}` → `{access_token, expires_in: 300}`: короткий JWT кандидата (без refresh) для вызовов бота в `/assessment/*` и `/assessment/tasks*` блока 1 (E25-3); не кандидат → `403`, неизвестный Telegram → `404` |
| `GET /internal/tg/category?tg_user_id=` | bot | `{categories[{profession, title, grade, needs_confirmation, valid_until}], claims[{profession, title, status, declared_grade, confirmed_grade}]}` — через `assessment.service` (`get_grades`, `claimed_vs_confirmed`), без своей логики |
| `GET\|PATCH /internal/tg/settings` | bot | `{salary_min, formats[], search_status}`; PATCH `{tg_user_id, salary_min?, formats?}` частичный, `salary_min: null` очищает; запись требует `pd_processing` |
| `PATCH /internal/tg/status` | bot | `{tg_user_id, status: active\|open\|dnd}` → настройки; `active` на 7 дней, как `PATCH /candidates/me/preferences` |
| `POST /internal/tg/github` | bot | `{tg_user_id, login}` |
| `GET /internal/tg/offers?tg_user_id=` | bot | Активные офферы кандидата (`sent|viewed|accepted|interview`, до 10, новые первыми) → `TgOffer[]`: поля `offer_id`, `status` и те же данные, что у шаблона `offer_new` (`company_name`, `company_responsibility`, `vacancy_title`, `formats[]`, `employment_type`, `salary_from/to`, `message`, `match_score`, `explanation[]`, `below_candidate_min`, `expires_at`) |
| `POST /internal/tg/offers/{id}/view|accept` | bot | `{tg_user_id}` → `TgOffer`. `view` переводит `sent → viewed`; правила и ошибки как у `/offers/{id}/accept` (`409 invalid_transition`, `409 offer_expired`) |
| `POST /internal/tg/offers/{id}/decline` | bot | `{tg_user_id, reason, comment?}` → `TgOffer`; `reason` — `DeclineReason` (бот переводит коды кнопок `ls|ws|wf|wg|nl|ot`) |
| `POST /internal/tg/tests`, `…/{id}/answer` | bot | Адаптивный тест |
| `GET /internal/tg/navigator?tg_user_id=` | bot | Навигатор кратко |
| `PATCH /internal/tg/status` | bot | Статус поиска |
| `GET /internal/taxonomy/snapshot` | ml | `Authorization: Service <SERVICE_TOKEN_ML>` (пустой токен = закрыто, иначе 401). `{version, skills[{id,slug,name,kind,group,status,testable,description,aliases[]}], adjacent[{a,b,weight}], parent[{child,parent,weight}], distinct[[a,b]], roles[{slug,name,profession,skills{}}], disciplines[{slug,name,rules[{skill,weight,track}]}]}`; вершины `active` и `provisional`, кеш Redis `c:tax:{version}` |

**Internal fsp-connector** (вызывает core-api):

| Метод и путь | Назначение |
|---|---|
| `GET /internal/oauth/authorize-url?state=&code_challenge=` | `{url}` — страница «Войти через ФСП» (PKCE S256; state и verifier хранит core) |
| `POST /internal/oauth/exchange` | `{code, code_verifier, candidate_id}` → `{participant_id, verified: true}` + событие `fsp.linked` (`method=oauth`); код одноразовый, повтор → 502 `fsp_auth_error` |
| `POST /internal/links` | `{candidate_id, participant_id?, email?, manual?}` → `{method: code|manual, masked_contact?}`. Есть контакт в ФСП → отправляет код (`s:fspcode:{cid}`, TTL 10 мин), привязки ещё нет; контакта нет или `manual=true` → сразу `fsp_links(manual, verified=false)` + `fsp.linked`. Ошибки: 404 `fsp_not_found`, 409 `fsp_already_linked` (+ запись в `fsp_link_conflicts`), 409 `candidate_already_linked`, 409 `fsp_ambiguous` |
| `POST /internal/links/verify` | `{candidate_id, code}` → `{verified}`; верный код → `fsp_links(code, verified=true)` + `fsp.linked`; 5 неверных попыток → 429 `too_many_attempts`, нет ожидающего кода → 410 `code_expired` |
| `/internal/registry/*` | Реестр ФСП (E39-28): `events`, `participants` (+`/import`), `results` (+`/import`), `match` `{candidate_id, emails[], phones[]}` → `{linked, participant_id, matched_by}`, `requests` (+`/by-candidate/{cid}`, `/{id}/accept`, `/{id}/reject`) — те же тела, что у публичных `/admin/fsp/*` и `/candidates/me/fsp/*`; права проверяет core |
| `GET /internal/competitions?from=&to=` | Календарь (для навигатора, если копия в core устарела) |
| `POST /integrations/fsp/webhook` | Публичный, вебхук ФСП/мока (HMAC) — маршрутизируется edge'ем сюда |

### 2.10. ml-api (внутренний, вызывает только core)

| Метод и путь | Вход | Выход |
|---|---|---|
| `POST /v1/query/parse` | `{text, rule_hint?: SearchFilters, taxonomy_version}` | `ParsedQuery` |
| `POST /v1/embeddings` | `{texts[], kind: "query"|"passage"}` | `{model, dim, vectors[][]}` |
| `POST /v1/skills/resolve` | `{mentions: [{raw, context}], taxonomy_version}` (до 50) | `[{raw, norm, decision: alias|fuzzy|new|same_pending|rejected, skill_slug?, kind: hard|soft|domain|not_skill, relation?: {type, to_slug, confidence}, reason?}]` ([skills.md §3](skills.md#3-конвейер-для-нового-упоминания)) |
| `POST /v1/skills/card-draft` | `{slug, name, kind: hard|soft|domain, skill_type?, description?, aliases[]}` | `SkillCardDraft`: форма карточки `data/skills/cards/*.yaml` (`schema_version`, `skill`, `type`, `summary`, `levels`, `concepts`, `misconceptions`) + `model` и `draft: true`. Всегда черновик; без LLM — шаблон `model=rules-template` ([skills.md §3.5](skills.md#35-реализация-в-ml-e16-4)) |
| `POST /v1/families/key-draft` | `FamilyKeyDraftRequest`: `{kind, stem, options[], lines[], actions[], steps[], rubric[]}` — пример варианта задания конструктора без ключа | `FamilyKeyDraft`: `{correct?, bug_lines?, scores?, answer?, rubric?, rationale?, model}` — черновик (E30-1, [assessment.md §10](assessment.md#10-api-v2)); `ML_FAKE` — заглушка, `LLM_ENABLED=false` — `503 llm_disabled` |
| `POST /v1/assessment/explain` | `AnswerExplainRequest`: `{kind, skill, stem, reason_code, reason_label, misconception?, truth?}` — причину определил core, без ключа и ответа кандидата | `AnswerExplain`: `{text, model}` — формулировка (E24-2, [assessment.md §10](assessment.md#10-api-v2)); `ML_FAKE` — шаблон, `LLM_ENABLED=false` — `503 llm_disabled` (core берёт свой шаблон) |
| `POST /v1/families/generate` | `FamilyGenerateRequest`: `{skill, skill_type?, kind, level 1–5, domain?, n 1–5}` | `FamilyGenerateResponse`: `{specs[], model}` — черновики форм конструктора `FamilySpec` (`kind`, `skill`, `level` — из заказа); core проверяет схемой и автопроверкой (E26-4, [assessment.md §7](assessment.md#7-жизненный-цикл-семейства-и-калибровка)); `ML_FAKE` — шаблоны по `kind`, `LLM_ENABLED=false` — `503 llm_disabled` |
| `POST /v1/families/solve` | `FamilySolveRequest`: `{kind, stem, options[]}` — вариант, как его видит кандидат (без ключа) | `FamilySolveAnswer`: `{answer, model}` — ответ в формате кандидата (число/строка, индекс, строки, порядок); вне границ варианта — `503 llm_invalid`. `ML_FAKE` — детерминированный «наугад» (E26-4) |
| `GET /healthz` | — | `{llm: up|down, embedder: up|fallback|down, model, queue_depth}`; `embedder: fallback` — модели эмбеддингов нет, `/v1/embeddings` отдаёт детерминированные запасные векторы (200, не 503; E42-2) |

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
  education: { institution?: string; degree?: string; field?: string; year_end?: number }[]; // E39-15
  links: string[];                  // E39-15, только владельцу
  hidden_skills: string[];          // E39-15, slug скрытых от работодателя навыков
  resume_draft_id?: string;         // E39-15, неподтверждённый черновик резюме для вкладки «Данные»
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
  fsp_highlights: { title: string; level: string; place?: number; of?: number; year: number; relevance?: "relevant" | "other"; note?: string }[]; // до 3; relevance — к профессии кандидата (E36-3)
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
  min_trust?: TrustLevel;          // минимальный уровень по обязательным навыкам; без них — хотя бы один навык запроса (без навыков — любой) не ниже (E39-21)
  fsp_only?: boolean; fsp_disciplines?: string[];
  active_only?: boolean;
  semantic_text?: string;          // смысловой остаток запроса для эмбеддинга («высоконагруженный API»)
  professions?: string[];          // E39-21: профессии системы (slug справочника) — действующий грейд одной из них; в потребности — только эти категории
  only_confirmed?: boolean;        // E39-21: грейд без needs_confirmation и low_confidence
  salary_min?: number;             // E39-21: ожидания кандидата не ниже (без ожиданий — подходит)
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
  // E20-5: только «заявлено в резюме», с цитатой; на категорию, грейд и подбор не влияет
  soft_skills: { name: string; quote: string }[];
  declared_grade?: { grade: Grade; quote: string };
  declared_roles: { role: RoleSlug; quote: string }[];
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
| `o:v:<offer_id>` / `o:a:<offer_id>` / `o:d:<offer_id>` | Подробнее / принять / отклонить |
| `o:r:<offer_id>:<reason>` | Причина отказа (`ls`, `ws`, `wf`, `wg`, `nl`, `ot`) |
| `o:b:<offer_id>` | Назад от выбора причины к кнопкам оффера |
| `t:s:<skill_slug>` | Начать тест |
| `t:a:<session_id>:<question_idx>:<option_id>` | Ответ теста (~45 байт; индекс вопроса защищает от нажатия старой кнопки) |
| `s:<active|open|dnd>` | Статус поиска |
| `f:l` / `f:s` | ФСП: ввести ID или email / обновить результаты |
| `g:sal` / `g:f:<remote|hybrid|office>` | Настройки: минимальная зарплата (FSM) / переключить формат |

Подробно: [telegram.md](telegram.md).
