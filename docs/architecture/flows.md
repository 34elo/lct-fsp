# Флоу системы

Обозначения: `API` = core-api, `CW` = core-worker, `MQ` = RabbitMQ, `MLW` = ml-worker, `FSPC` = fsp-connector, `PG` = PostgreSQL. Очереди и события — [messaging.md](messaging.md), эндпоинты — [api.md](api.md), граф — [graph.md](graph.md).

---

## F1. Вход и регистрация

Способы: email и пароль; Telegram (Telegram Login Widget на сайте; бот только привязывается к готовому аккаунту, E43-7); одноразовая ссылка из бота; «Войти через ФСП» (F3).

```mermaid
sequenceDiagram
  actor U as Кандидат
  participant B as bot
  participant API as core-api
  participant R as Redis
  participant W as web
  U->>B: /start link_<token> (из профиля на сайте)
  B->>API: POST /internal/tg/link {tg_user_id, token, chat_id, username}
  API-->>B: {user_id} | 410 link_token_invalid | 409
  B->>U: «Telegram привязан» | «Ссылка устарела» | «уже привязан»
  Note over B,U: /start без кода у непривязанного: «Зарегистрируйся на сайте» (E43-7)
  U->>B: Открыть платформу
  B->>API: POST /internal/auth/magic-link {tg_user_id, redirect}
  API->>R: SET s:magic:{token} EX 300
  API-->>B: {url}
  U->>W: переход по ссылке
  W->>API: POST /api/v1/auth/magic {token}
  API->>R: GETDEL s:magic:{token}
  API-->>W: access_token + refresh-cookie
```

- Ссылка живёт 5 минут и срабатывает один раз.
- Telegram Login Widget: проверка `hash` (HMAC с ключом SHA256(bot_token)), `auth_date` ≤ 24 ч.
- Привязка Telegram к аккаунту с email: deep link `t.me/<bot>?start=link_<token>`.

---

## F2. Резюме → факты и доказательства

```mermaid
sequenceDiagram
  actor U as Кандидат
  participant API as core-api
  participant S3 as MinIO
  participant MQ as RabbitMQ
  participant MLW as ml-worker-llm
  participant LLM as llm-chat
  participant CW as core-worker
  U->>API: POST /candidates/me/resumes (PDF/DOCX)
  API->>API: согласие, размер ≤ 10 МБ, тип по сигнатуре
  API->>S3: put resumes/{user}/{sha256}
  API->>MQ: cmd ml.resume.parse (приоритет 9)
  API-->>U: 202 {resume_id}
  MQ->>MLW: задача (prefetch 1)
  MLW->>MQ: ui.user.{id} прогресс: извлекаю текст
  MLW->>MLW: текст, правила (контакты, даты)
  MLW->>LLM: JSON-схема ParsedResume
  MLW->>MLW: проверка цитат, сопоставление навыков с графом навыков
  MLW->>MQ: evt ml.resume.completed {parsed}
  MQ->>CW: core.ingest
  CW->>PG: resumes.parsed, status=parsed (inbox по message_id)
  CW->>MQ: ui.user.{id} resume.parsed
  U->>API: проверяет и правит, POST .../confirm
  API->>PG: факты experience + evidence(resume), правки → evidence(self)
  API->>PG: новые навыки → конвейер навыков, outbox: cmd core.recompute
  Note over CW: далее F5
```

- Повторная загрузка того же файла не вызывает LLM: кеш по `sha256 + parser_version`.
- В боте файл приходит как `document`, бот стримит его в `POST /internal/tg/resumes`. Подтверждение в боте: «Всё верно» или «Исправить на сайте».
- Скан без текста → OCR (если есть tesseract), иначе `ml.resume.failed`.

---

## F3. Привязка ФСП → факты → навыки «загораются»

| Способ | Верификация | Вес доказательств |
|---|---|---|
| A. «Войти через ФСП» (OAuth, на демо мок) | полная | 100% |
| B. ID или email + код подтверждения | полная | 100% |
| C. Ручной ID | нет | ×0.5, пометка «не верифицировано» |

```mermaid
sequenceDiagram
  actor U as Кандидат
  participant API as core-api
  participant FSPC as fsp-connector
  participant M as fsp-mock
  participant MQ as RabbitMQ
  participant CW as core-worker
  U->>API: Войти через ФСП
  API->>FSPC: GET /internal/oauth/authorize-url {state, pkce}
  API-->>U: 302 на страницу ФСП
  U->>M: подтверждает себя
  M-->>U: 302 /auth/fsp/callback?code
  U->>API: callback
  API->>FSPC: POST /internal/oauth/exchange {code, verifier, candidate_id}
  FSPC->>M: token + userinfo
  FSPC->>PG: fsp_links(verified, oauth) в своей БД
  FSPC-->>API: {participant_id, verified}
  FSPC->>MQ: evt fsp.linked
  FSPC->>M: участник, результаты, разряды, команды
  FSPC->>MQ: evt fsp.results.imported {results, ranks, teams}
  MQ->>CW: core.ingest
  CW->>PG: узлы-факты fsp_results + команды + рёбра evidence по правилам дисциплин
  CW->>MQ: ui.user.{id} fsp.imported, cmd core.recompute
  Note over CW: F5 → точки загораются, грейд растёт
```

---

## F4. GitHub → ДНК кода

```mermaid
sequenceDiagram
  actor U as Кандидат
  participant API as core-api
  participant MQ as RabbitMQ
  participant MLW as ml-worker-code
  participant GH as GitHub
  participant CW as core-worker
  U->>API: POST /candidates/me/github {login}
  API->>API: согласие, лимит 3 в сутки
  API->>MQ: cmd ml.code.analyze
  API-->>U: 202
  MLW->>GH: репозитории (ETag-кеш)
  loop глубокие репозитории (до 8)
    MLW->>GH: partial clone в tmpfs
    MLW->>MLW: авторство, языки, манифесты, зрелость, флаги, соавторы
    MLW->>MQ: ui.user.{id} прогресс 3/7
  end
  MLW->>MQ: evt ml.code.completed
  MQ->>CW: core.ingest
  CW->>PG: факты code_repos + repo_contributors + evidence(github)
  CW->>MQ: cmd core.recompute, обновление candidate_links
```

---

## F5. Пересчёт графа (центральный)

Триггеры: команда `core.recompute` после новых доказательств, `taxonomy.updated` (только затронутым кандидатам), изменение предпочтений.

```mermaid
sequenceDiagram
  participant MQ as RabbitMQ
  participant CW as core-worker
  participant PG as PostgreSQL
  participant MLAPI as ml-api
  MQ->>CW: cmd core.recompute {candidate_id, requested_at}
  CW->>PG: recomputed_at >= requested_at ? пропустить
  CW->>PG: подграф кандидата: факты + evidence (один запрос)
  CW->>CW: доверие (затухание, max по типу, noisy-OR)
  CW->>CW: наследование по иерархии из графа навыков в памяти
  CW->>CW: роли и категория, грейд с разбивкой
  CW->>MLAPI: эмбеддинг, если profile_text изменился
  CW->>PG: candidate_skills, candidates (profile_version+1), outbox
  CW->>MQ: evt skills.profile.updated {diff}
  MQ->>CW: core.handlers
  CW->>MQ: cmd core.match.candidate, ui.user.{id} profile.updated, cmd notify.telegram (если diff значимый)
```

- **Слияние без задержек:** пачка импорта ставит много команд, но обработчик пропускает те, что уже покрыты более поздним пересчётом.
- **Diff** в событии («алгоритмы ●●○○ → ●●●●, грейд Junior → Junior+») показывают фронт и бот.

---

## F6. Поиск работодателя и подстройка в сессии

```mermaid
sequenceDiagram
  actor H as HR
  participant API as core-api
  participant R as Redis
  participant MLAPI as ml-api
  participant PG as PostgreSQL
  H->>API: POST /search/parse {text}
  API->>R: кеш разбора
  API->>API: правиловый парсер (≤ 50 мс)
  API->>MLAPI: POST /v1/query/parse (таймаут 4 с)
  API-->>H: чипсы-фильтры + смысловой остаток
  H->>API: POST /search/candidates {filters}
  API->>MLAPI: эмбеддинг остатка (кеш)
  API->>PG: отбор: граф (требования + смежность) + pgvector
  API->>API: скоринг, MMR, объяснения (пути в графе)
  API->>PG: impressions (позиции, признаки)
  API-->>H: карточки + session_id
  H->>API: открыл, в шорт-лист, не подходит
  API->>R: s:rec:{user}:{ctx}: Роккио + веса признаков
  H->>API: следующая страница
  API-->>H: выдача с учётом реакций + чипсы «Учли: …»
```

Если LLM не уложилась в таймаут, отдаём чипсы правилового парсера с `refining=true`.

---

## F7. Вакансия → подборка

1. `POST /vacancies` → `POST /vacancies/{id}/publish`. Проверки: компания проверена, есть вилка, есть обязательный навык.
2. `evt vacancy.published` → `cmd core.match.vacancy` → отбор и скоринг по всем видимым кандидатам → `matches` (топ-200) → `ui.user.{hr}` «подборка готова».
3. `cmd ml.matches.explain` (приоритет 2) → обоснования для топ-5 → `evt ml.matches.explained`.
4. `evt skills.profile.updated` → `cmd core.match.candidate` → пересчитать строки `matches` этого кандидата по всем открытым вакансиям. Новый кандидат в топе вакансии с подпиской → уведомление.

---

## F8. Оффер → Telegram → решение → контакты

```mermaid
sequenceDiagram
  actor H as HR
  participant API as core-api
  participant PG as PostgreSQL
  participant MQ as RabbitMQ
  participant CW as core-worker
  participant B as bot
  actor C as Кандидат
  H->>API: POST /offers/salary-hint
  API-->>H: ниже медианы на 18 процентов
  H->>API: POST /offers (Idempotency-Key)
  API->>API: проверки и лимиты
  API->>PG: offer + outbox (одна транзакция)
  API-->>H: 201
  API->>MQ: relay: evt offer.sent (publisher confirm)
  MQ->>CW: core.handlers (inbox)
  CW->>PG: notifications
  CW->>MQ: ui.user.{cand} + cmd notify.telegram
  MQ->>B: bot.telegram
  B->>C: оффер с кнопками
  C->>B: Принять
  B->>API: POST /internal/tg/offers/{id}/accept
  API->>PG: FOR UPDATE, accepted, contact_reveal, outbox
  API-->>B: ok
  B->>C: Принято, компания получила контакты
  API->>MQ: evt offer.accepted
  MQ->>CW: core.handlers
  CW->>MQ: ui.user.{hr} оффер принят
```

Отклонение: бот показывает причины кнопками → `POST /internal/tg/offers/{id}/decline {reason}`. Вопросов работодателю из бота нет (E39-26: вместо переписки одно сообщение при приглашении и один ответ на сайте). «Подробнее» — одноразовая ссылка на сайт.

```mermaid
stateDiagram-v2
  [*] --> sent
  sent --> viewed: кандидат открыл
  sent --> accepted
  viewed --> accepted
  sent --> declined
  viewed --> declined
  sent --> expired: 7 дней
  viewed --> expired: 7 дней
  sent --> withdrawn: компания отозвала
  viewed --> withdrawn
  accepted --> interview
  interview --> hired
  interview --> not_hired
  accepted --> not_hired
  hired --> [*]
  not_hired --> [*]
  declined --> [*]
  expired --> [*]
  withdrawn --> [*]
```

Вопросы не меняют статус: у оффера флаг `awaiting_reply_from`.

---

## F9. Адаптивный тест

1. `POST /assessment/tests {skill_id}` (или `/internal/tg/tests` из бота) → сессия в Redis `s:test:{id}` (θ, SE, заданные вопросы) + строка `test_sessions`.
2. Следующий вопрос — максимум информации Фишера в текущей θ ([ml.md §8](ml.md#8-адаптивный-тест)).
3. Остановка: ≥ 5 вопросов и SE < 0.45, или 8 вопросов. 60 с на вопрос.
4. Результат → факт `test_sessions` + `evidence(test)` → `cmd core.recompute`. В боте: «Python ●●○○ → ●●●○».
5. Пересдача — через 30 дней (в демо-режиме без ограничения). Результат действует 12 месяцев.

---

## F10. ИИ-интервью

1. Условие: есть глубоко разобранный репозиторий с долей авторства ≥ 50%.
2. `cmd ml.interview.generate` (приоритет 7) → 3 фрагмента кода кандидата → вопросы + рубрики → `evt ml.interview.generated`.
3. Ответы текстом (🚀 голосом через whisper.cpp), по 3 минуты.
4. `cmd ml.interview.grade` (приоритет 8) → оценки 0–3 → `evt ml.interview.graded` → факт `interview_sessions` + `evidence(ai_interview)` + подтверждение авторства репозитория → `cmd core.recompute`.

---

## F11. Новый результат ФСП → профиль обновился → push

```mermaid
sequenceDiagram
  actor A as Админ (демо)
  participant API as core-api
  participant M as fsp-mock
  participant FSPC as fsp-connector
  participant MQ as RabbitMQ
  participant CW as core-worker
  participant B as bot
  A->>API: POST /admin/demo/fsp-result
  API->>M: POST /mock/results
  M->>FSPC: вебхук result.published + HMAC
  FSPC->>FSPC: подпись, идемпотентность по event_id
  FSPC->>M: результаты since last_synced
  FSPC->>MQ: evt fsp.results.imported {new: true}
  MQ->>CW: core.ingest: факты + evidence → recompute (F5)
  CW->>MQ: ui.user.{id} profile.updated
  CW->>MQ: cmd notify.telegram: 2 место, навыки обновлены
  MQ->>B: bot.telegram
```

Если у реального API ФСП нет вебхуков, работает фолбэк `fsp.sync_all` раз в час.

---

## F12. Расписание

`core-scheduler` публикует команды в `core.jobs` и `fsp.sync`: истечение офферов (5 мин), сброс «активно ищу» (1 ч), карта рынка (2 мин при изменениях), синхронизация ФСП и календаря (1 ч), рейтинг компаний (1 ч), `candidate_links` (10 мин при импортах), очистка (сутки). Таблица — [messaging.md §4](messaging.md#4-расписание).

---

## F13. Удаление профиля

1. `DELETE /candidates/me` (подтверждение паролем или фразой) → в одной транзакции: скрыт из поиска (`deleted_at`), согласия отозваны, стёрты резюме и файлы, доказательства, навыки, тесты и грейды, ПДн анкеты и учётной записи; `evt candidate.deleted`.
2. core-worker: удаляет факты, доказательства, `candidate_skills`, эмбеддинг, файлы в MinIO, Telegram-привязку. В офферах остаётся только псевдоним.
3. fsp-connector по тому же событию удаляет `fsp_links` и сырые данные участника.
4. Отзыв отдельного согласия удаляет связанные данные: `fsp_data` → факты ФСП, `code_analysis` → репозитории и интервью. Затем F5.

---

## F14. Uplift: какой навык подтвердить, чтобы подходить под N% больше вакансий

```mermaid
sequenceDiagram
  actor C as Кандидат
  participant API as core-api
  participant R as Redis
  participant PG as PostgreSQL
  C->>API: GET /candidates/me/uplift
  API->>R: кеш по profile_version и vacancies_version
  API->>PG: релевантные вакансии V + их требования
  API->>API: base = сколько из V подходит сейчас
  loop каждый навык из спроса (топ-30)
    API->>API: копия профиля с навыком ●●●○ + наследование
    API->>API: сколько из V подходит теперь
  end
  API->>API: жадная комбинация до 3 навыков, дельта медианы вилок
  API->>PG: как подтвердить: тест, соревнования ФСП (правила дисциплин)
  API-->>C: Docker: +64 процента (14 → 23), тест 10 мин, Кубок 15 ноября
```

Бот присылает лучший uplift после обновления профиля или раз в неделю, если прирост ≥ 15%. Подробно — [matching.md §6](matching.md#6-uplift-для-кандидата-какой-навык-добавить).
