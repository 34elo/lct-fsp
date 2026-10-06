# Интеграция с ФСП (сервис fsp-connector)

> ⚠️ Организаторы обещали спецификацию API ФСП и/или тестовый мок. До их появления работаем с **собственным моком** по предполагаемой схеме ниже. Вся работа с ФСП живёт в отдельном сервисе **fsp-connector**: порт `FspPort`, адаптеры, привязка, синхронизация, вебхуки. Core получает только нормализованные факты событиями RabbitMQ (`fsp.linked`, `fsp.results.imported`, `fsp.competitions.updated`) и строит из них вершины графа. Смена источника — это новый адаптер в fsp-connector, а не переделка продукта (требование Q6).

## 1. Что известно о предметной области (сайт ФСП, Кубок России)

- **5 дисциплин:** продуктовое программирование (хакатон), алгоритмическое, программирование систем информационной безопасности, программирование робототехники, программирование БАС (беспилотных авиационных систем).
- **Форматы:** личный — алгоритмическое и БАС; командный — продуктовое (3–6 человек), ИБ (2–7), робототехника (2–4).
- **Этапы:** отборочные (часто онлайн) → финалы с квотами.
- **Уровни соревнований** (по ЕВСК, ⚠️ уточнить, как они отражены в данных): региональные, межрегиональные, всероссийские (Кубок, Чемпионат, Первенство России), международные.
- **Разряды и звания** (⚠️ уточнить шкалу для спортивного программирования): юношеские III–I, спортивные III–I, КМС, МС, МСМК.
- **География:** 89 региональных представительств.
- На сайте есть календарь (анонсы, архив), статистика, личный кабинет.

## 2. Порт и DTO (`services/fsp-connector/app/port.py`, DTO — в `packages/contracts/fsp.py`)

```python
class FspPort(Protocol):
    async def get_participant(self, participant_id: str) -> FspParticipant: ...
    async def find_participant(
        self,
        *,
        email: str | None = None,
        last_name: str | None = None,
        birth_date: date | None = None,
    ) -> list[FspParticipantBrief]: ...
    async def get_results(
        self, participant_id: str, since: date | None = None
    ) -> list[FspResult]: ...
    async def get_ranks(self, participant_id: str) -> list[FspRank]: ...
    async def get_competitions(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        discipline: str | None = None,
    ) -> list[FspCompetition]: ...
    async def get_standings(
        self, competition_id: str
    ) -> list[FspStandingRow]: ...  # для рейтинга, 🚀
    async def get_team(self, team_id: str) -> FspTeam: ...
    # верификация
    async def send_verification_code(self, participant_id: str) -> MaskedContact: ...
    async def check_verification_code(self, participant_id: str, code: str) -> bool: ...
    # OAuth (если есть)
    def authorize_url(self, state: str, code_challenge: str) -> str: ...
    async def exchange_code(self, code: str, code_verifier: str) -> FspOAuthIdentity: ...
```

DTO (нормализованные, наши):

```python
class FspResult(BaseModel):
    competition_id: str
    discipline: FspDiscipline  # algorithmic | product | security | uav | robotics
    stage: Literal["qualifier", "final"]
    team_id: str | None
    team_role: Literal["captain", "member", "individual"]
    place: int | None
    participants_total: int | None  # участников или команд в зачёте
    score: float | None
    track: str | None  # трек хакатона, если есть
    date: date


class FspCompetition(BaseModel):
    id: str
    title: str
    discipline: FspDiscipline
    level: Literal["regional", "interregional", "national", "international"]
    format: Literal["online", "offline"]
    region: str | None
    start_date: date
    end_date: date | None
    status: Literal["announced", "registration", "ongoing", "finished"]
    tracks: list[str] = []
    registration_url: str | None
```

Адаптеры:
- `HttpFspAdapter(base_url, api_key, mapping)` — для нашего мока и, скорее всего, для мока организаторов. Различия схем закрываются **маппингом** (`fsp/mappings/<source>.py`): переименование полей, перевод значений перечислений, вычисление `participants_total`, если его нет.
- `CachedFspAdapter` — обёртка с кешем в Redis ([messaging.md §7](messaging.md#6-кеши)) и ретраями (httpx, экспоненциальная пауза, circuit breaker на 30 с после 5 ошибок подряд).
- Выбор адаптера — `FSP_ADAPTER=mock|organizers|real` в env.

## 3. Наш мок (`services/fsp-mock`), предполагаемый API

| Метод | Ответ |
|---|---|
| `GET /api/v1/participants/{id}` | `{id, last_name, first_name, middle_name, birth_year, region, email_masked, phone_masked, ranks:[{discipline, rank, assigned_at}]}` |
| `GET /api/v1/participants?email=&last_name=` | `[{id, full_name_masked, region, birth_year}]` |
| `GET /api/v1/participants/{id}/results?since=` | `[{competition_id, discipline, stage, team_id, team_role, place, participants_total, score, track, date}]` |
| `GET /api/v1/competitions?from=&to=&discipline=&status=` | `[{id, title, discipline, level, format, region, start_date, end_date, status, tracks, registration_url}]` |
| `GET /api/v1/competitions/{id}/standings` | `[{place, team_id?, participant_ids[], score}]` |
| `GET /api/v1/teams/{id}` | `{id, name, competition_id, members:[{participant_id, role}]}` |
| `POST /api/v1/verification/send` | `{participant_id}` → `{channel:"email", masked:"a***@mail.ru"}` (код виден в `GET /mock/codes`) |
| `POST /api/v1/verification/check` | `{participant_id, code}` → `{ok}` |
| `GET /oauth/authorize` | HTML-страница в стиле ФСП: поиск себя / выбор демо-участника → редирект с `code` |
| `POST /oauth/token` | `{access_token, token_type, expires_in, id_token}` (PKCE; `id_token` — RS256 JWT: `iss, sub=participant_id, aud=client_id, nonce, name`) |
| `GET /oauth/userinfo` | `{participant_id, full_name, sub, name}` |
| `GET /.well-known/openid-configuration` | OIDC discovery (E20-10): issuer = `FSP_MOCK_ISSUER`, endpoints, `S256` |
| `GET /oauth/jwks` | JWKS с публичным RSA-ключом (`FSP_MOCK_OIDC_PRIVATE_KEY` — PEM, иначе ключ на старте). Keycloak подключается заменой issuer на его URL |
| `POST /mock/results` | Админ: создать результат → вебхук на `FSP_WEBHOOK_URL` |
| `GET /mock/codes` | Админ: последние коды верификации (для демо) |

Аутентификация к моку: `X-Api-Key`. Вебхук мока → fsp-connector (edge маршрутизирует `/integrations/fsp/*`): `POST /integrations/fsp/webhook`, тело `{event_id, type: "result.published", participant_id, competition_id, occurred_at}`, подпись `X-Signature: sha256=<hex(HMAC(secret, body))>`.

**Данные мока** генерирует `tools/seed` вместе с витриной (одним seed'ом): ~600 участников (из них ~40% зарегистрированы на платформе), ~45 соревнований за 3 года по 5 дисциплинам и уровням, 6–8 предстоящих (для навигатора), команды для командных дисциплин, разряды. Герои демо (Аня — капитан команды, призёр всероссийского финала по продуктовому программированию) прописаны вручную.

## 4. Привязка и верификация

| Способ | Когда | Что пишет fsp-connector (своя БД) |
|---|---|---|
| OAuth «Войти через ФСП» | Есть OAuth у ФСП (на демо — мок) | `fsp_links(method=oauth, verified=true)` |
| Код подтверждения | В данных ФСП есть контакт | `method=code, verified=true` после ввода кода (5 попыток, TTL 10 мин) |
| Ручной ID | Нет ни того ни другого | `method=manual, verified=false`, доказательства × 0.5, пометка в UI «не верифицировано» |

После привязки — событие `fsp.linked`, core хранит копию в `fsp_participants`. Один `participant_id` нельзя привязать к двум аккаунтам (`UNIQUE`). Если кто-то пытается привязать чужой ID, а он уже привязан, отдаём ошибку `fsp_already_linked` и создаём запись для модерации.

## 5. Правила «дисциплина → навыки»

Источник: `data/fsp/discipline_rules.yaml` → таблица `discipline_skill_rules`, редактируются в админке. **⚠️ Черновик, согласовать с экспертами ФСП.**

```yaml
algorithmic:
  algorithms: 1.0
  data_structures: 1.0
  math: 0.7
  cpp: 0.6          # если в данных есть язык решения — вес 0.9 для него
  python: 0.4
product:
  teamwork: 0.8
  product_thinking: 0.6
  backend: 0.6      # обобщённые навыки-«роли» → категория; конкретный стек из трека или GitHub
  frontend: 0.5
  git: 0.6
  tracks:           # вариант D: навыки по описанию трека
    ml: { ml: 0.8, python: 0.6 }
    web: { frontend: 0.7, backend: 0.7 }
    mobile: { mobile: 0.8 }
security:
  security: 1.0
  pentest: 0.8
  networks: 0.7
  linux: 0.7
  reverse_engineering: 0.6
  cryptography: 0.5
uav:
  embedded: 0.8
  control_systems: 0.8
  computer_vision: 0.6
  cpp: 0.6
  python: 0.5
robotics:
  embedded: 0.8
  control_systems: 0.8
  ros: 0.7
  electronics: 0.6
  cpp: 0.5
```

Применение: каждое `FspResult` → для каждого навыка правила (+ навыки трека) → `evidence(source=fsp, strength=f(w_rule, уровень, место, этап))` ([ml.md §3.2](ml.md#32-достижение-фсп--навыки)). Капитан → `leadership`. `details` хранит человекочитаемую строку: «Призёр всероссийского финала Кубка России по продуктовому программированию, 2 место из 40 команд, капитан».

## 6. Синхронизация

- **При привязке** — полная (команда RabbitMQ `fsp.sync` от core или сразу после OAuth). Результат — событие `fsp.results.imported` с нормализованными результатами, разрядами и командами.
- **По вебхуку** — инкрементальная (`since = last_synced_at`), F11.
- **Регулярно** — команда `fsp.sync_all` от core-scheduler раз в час (фолбэк, если у реального API нет вебхуков) + обновление календаря соревнований.
- **Upsert** по `(participant_id, competition_id, stage)`. Результаты, пропавшие из источника, помечаем `is_active=false` у доказательств, но не удаляем: это аудит.
- Достижения ФСП **не редактируются вручную**, только через синхронизацию (правило 11.5).

**Реализация (E5-5).**
- **fsp-connector** (`sync.py`, `handlers.py`): очередь `fsp.sync`, команды `fsp.sync {candidate_id, reason, since?}` и `fsp.sync_all` (под замком `lock:fsp_sync:{cid}`, через inbox). Полная выгрузка (`new=true`) — когда `since` не задан и привязка ещё не синхронизировалась либо `reason ∈ {linked, manual}`; иначе `since = last_synced_at`. Перед выгрузкой сбрасывается кеш участника. `fsp.competitions.updated` (соревнования из результатов; при `sync_all` весь календарь) уходит в outbox раньше `fsp.results.imported`, в той же транзакции; состав команд подтягивается `get_team`. Если новых результатов нет, а разряды не менялись (хеш в `fsp_links.sync_cursor`), событие не публикуется.
- **core** (`app/graph/fsp_ingest.py`): обработчики очереди `core.ingest`. `fsp.linked` → `fsp_participants` и команда `fsp.sync(reason=linked)`; `fsp.competitions.updated` → `fsp_competitions`; `fsp.results.imported` → upsert `fsp_results` (`id` = uuid5 от `participant_id|competition_id|stage`), `fsp_ranks`, `fsp_teams`/`fsp_team_members`. Полная выгрузка гасит пропавшие результаты (`fsp_results.is_active=false`, доказательства `is_active=false`), строки остаются. Порядок событий не гарантирован: доказательства пересобираются из сохранённых фактов, поэтому результат, пришедший раньше календаря (нет `level`), получает доказательства после `fsp.competitions.updated`.
- **Правила → доказательства:** для каждого активного результата и каждого навыка правила дисциплины (+ правила трека, максимум весов) создаётся `evidence(source=fsp, fact_type=fsp_result, fact_id=fsp_results.id)` с силой `min(0.95, w × k_level × k_result × k_stage)` ([ml.md §3.2](ml.md#32-достижение-фсп--навыки)); `verified` берётся из привязки. Софт-навыки (`kind=soft`) точек доверия не получают; язык решения в DTO нет, поэтому вес 0.9 не применяется.
- **`details` результата** (читают грейд и командные сигналы): `competition_id, level, place, participants, stage, final, team_role, team_size, teammates, track, label`. `teammates` — хеши id напарников (`sha256`, 16 символов), сами id ФСП в доказательства не пишутся. Разряд — `fact_type=fsp_rank`, `details {rank, discipline}`, сила 0 (сигнал грейда, не навык), привязан к самому весомому навыку дисциплины; при нескольких разрядах грейд берёт старший.

## 7. 🚀 Команды ФСП и спортивный рейтинг

- **Команды:** `fsp_teams` + `fsp_team_members`. Карточка команды показывает только участников, которые есть на платформе и не скрыли профиль: суммарные навыки, достижения, совместные выступления. Командный оффер — `team_offer_id`, общий у N офферов; каждый участник принимает свой.
- **Рейтинг (если есть полные таблицы):** Эло/Glicko по результатам соревнований внутри дисциплины → отдельный сигнал к грейду и сортировке. Делаем только при наличии `standings`.

## 8. Вопросы к организаторам (дублируются в [../notes/questions.md](../notes/questions.md))

1. Формат и способ доступа к API (REST? ключ? песочница?), лимиты.
2. Есть ли: составы команд, роли (капитан), полные таблицы результатов, уровни соревнований, шкала разрядов, треки, язык решения в алгоритмике?
3. Есть ли контакты участников для кода подтверждения или OAuth/SSO?
4. Есть ли вебхуки или хотя бы `since`-фильтр для инкрементальной синхронизации?
5. Можно ли показывать работодателю названия соревнований и места (без ФИО)?
