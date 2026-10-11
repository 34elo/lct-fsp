# Конфигурация

Два уровня: переменные окружения (инфраструктура, секреты, флаги) и `data/scoring.yaml` (все числа формул). Пример окружения с комментариями — [.env.example](../../.env.example).

## Переменные окружения

**Общие**

| Переменная | Назначение |
|---|---|
| `ENV` | `dev` / `demo` / `prod`; вне `dev` cookie помечаются `Secure` |
| `GATEWAY_PORT` | Порт gateway на хосте (28080) |
| `DEMO_MODE` | Вход жюри, демо-кнопки ФСП, обход кулдауна для демо-аккаунтов |
| `LOG_LEVEL` | Уровень логов |
| `ALLOWED_ORIGINS` | Origin'ы SPA для проверки cookie-эндпоинтов (JSON-список) |
| `WEB_BASE_URL`, `VITE_APP_URL` | Адрес кабинета для ссылок из бота и кнопок лендинга |
| `VITE_JURY_MODE` | Сборка фронта с кнопками входа жюри |

**Хранилища**

| Переменная | Назначение |
|---|---|
| `POSTGRES_*`, `CORE_DB_PASSWORD`, `FSPC_DB_PASSWORD`, `DATABASE_URL`, `FSP_CONNECTOR_DATABASE_URL` | PostgreSQL и роли сервисов |
| `REDIS_URL` | Redis |
| `RABBITMQ_*`, `RABBITMQ_URL` | RabbitMQ, отдельный пароль на сервис |
| `S3_ENDPOINT`, `S3_PUBLIC_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET` | MinIO |

**Секреты приложения**

| Переменная | Назначение |
|---|---|
| `JWT_SECRET` | Подпись access-токенов |
| `PII_KEY` | Ключ Fernet для шифрования ФИО и контактов |
| `PSEUDO_ID_SECRET` | HMAC для `pseudo_id` |
| `ANALYTICS_SALT` | HMAC для псевдонимов аналитики |
| `SERVICE_TOKEN_BOT`, `SERVICE_TOKEN_ML`, `SERVICE_TOKEN_CORE`, `SERVICE_TOKEN_MOCK` | Токены internal API |
| `OB_SIGNING_KEY`, `OB_ISSUER_DID` | Ключ Ed25519 и издатель Open Badge |

**Флаги поведения**

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `EMAIL_VERIFICATION_REQUIRED` | `false` | Требовать подтверждённый email перед приглашением и откликом |
| `REQUIRE_CANDIDATE_CONTACTS` | `false` | Не показывать работодателям профиль без ФИО и контакта (демо-аккаунты — показывать) |
| `SMTP_*` | пусто | Отправка кода подтверждения; пустой `SMTP_HOST` — письма не уходят |

**ФСП**

| Переменная | Назначение |
|---|---|
| `FSP_CONNECTOR_URL` | Адрес fsp-connector для core |
| `FSP_ADAPTER` | Источник данных ФСП (`mock`) |
| `FSP_BASE_URL`, `FSP_PUBLIC_URL`, `FSP_API_KEY` | Адрес и ключ источника |
| `FSP_OAUTH_CLIENT_ID`, `FSP_OAUTH_CLIENT_SECRET`, `FSP_OAUTH_REDIRECT_URI` | OAuth-клиент (FSP ID / мок) |
| `FSP_WEBHOOK_SECRET` | Подпись вебхука |

**ML и LLM**

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `ML_FAKE` | `true` | Заглушки ML |
| `LLM_ENABLED` | `true` | `false` — все функции без LLM |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | `qwen3-vl-4b` | OpenAI-совместимый сервер LLM |
| `EMBEDDING_MODEL` | `bge-m3` | `bge-m3` или `multilingual-e5-small` |
| `EMBEDDING_MODEL_PATH`, `EMBEDDING_HF_ID`, `EMBEDDING_AUTOLOAD` | | Локальный каталог модели или загрузка с HF при старте |
| `ML_API_URL` | | Адрес ml-api для core; пусто — эмбеддинги не считаются |
| `MUTMINE_GITHUB`, `MUTMINE_CACHE`, `GITHUB_TOKEN` | | Майнинг мутаций открытого кода |

**Telegram**: `TG_BOT_TOKEN` (пусто — бот не запускается), `TG_BOT_USERNAME`.

## `data/scoring.yaml`

Все коэффициенты формул в одном файле; код читает их при старте. Разделы:

| Раздел | Что настраивает | Документ |
|---|---|---|
| `trust_levels`, `evidence_sources`, `provisional_skill_max_strength` | Уровни доверия, сила и затухание источников доказательств, коэффициенты ФСП, слагаемое F | [skills.md](../mechanics/skills.md), [fsp.md](../mechanics/fsp.md) |
| `category` | Роль и стек профиля по покрытию профессий | [skills.md](../mechanics/skills.md) |
| `assessment` | Пороги грейдов, сложность по уровням, длина теста, EAP, калибровка, SPRT, бонус, экспресс, план, выбор заданий, пилоты, кулдауны, честность, таймер, жизненный цикл заданий | [assessment.md](../mechanics/assessment.md) |
| `grade_thresholds`, `grade_signals` | Сигнальный грейд анкеты | [matching.md](../mechanics/matching.md#9-ограничения-и-известные-отличия) |
| `matching_weights`, `grade_fit_scoring`, `skills_coverage`, `hard_filters`, `team_signal_*`, `employer_emphasis` | Скоринг под вакансию и командные сигналы | [matching.md](../mechanics/matching.md#5-подбор-под-вакансию) |
| `session_tuning` | Подстройка выдачи в сессии | [matching.md](../mechanics/matching.md#6-подстройка-выдачи-в-сессии) |
| `p_accept` | Вероятность принятия и прогноз ответа | [matching.md](../mechanics/matching.md#7-помощь-работодателю-при-приглашении) |
| `strength` | Веса силы профиля и `rank` | [matching.md](../mechanics/matching.md#3-ранжирование-внутри-категории) |
| `needs` | Порог affinity, веса «обязательно/желательно», подписки | [matching.md](../mechanics/matching.md#2-потребность--категории) |
| `limits` | Лимиты офферов и интересов, сроки, переранжирование, uplift, кеш | [contact.md](../mechanics/contact.md) |
