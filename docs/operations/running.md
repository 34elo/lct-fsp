# Сборка и запуск

## Требования

| | Стенд проверки | Разработка |
|---|---|---|
| ОС | Linux, macOS или Windows с Docker | то же |
| CPU / RAM | ~8 ядер, 16+ ГБ (приложение в профиле `lite` занимает ≈ 1.5 ГБ, плюс БД и брокер) | 4+ ядра, 16+ ГБ |
| Диск | 10+ ГБ | 20+ ГБ |
| GPU | не нужна | нужна только для локальной LLM |
| ПО | Docker Engine 24+ с Compose v2.20+, `make`, `openssl`, [`uv`](https://docs.astral.sh/uv/) (для демо-данных) | плюс Node.js 20+ и pnpm 10 |

Порты на хосте — диапазон 28xxx; наружу открыт только gateway `28080`.

## Быстрый старт (без GPU и LLM)

```bash
git clone <repo-url> lct-fsp && cd lct-fsp
make up-lite     # .env.demo со случайными секретами, сборка, миграции, справочник навыков, запуск
make seed        # демо-данные и демо-аккаунты (1–2 минуты, повторный запуск безопасен)
```

Откройте http://localhost:28080. Swagger — http://localhost:28080/api/docs. Вход — аккаунтом из [таблицы ниже](#демо-аккаунты).

`make up-lite` поднимает всё, кроме LLM: тест, категории, подбор, офферы, ФСП и разбор резюме по правилам работают полностью. Модель эмбеддингов `multilingual-e5-small` (≈ 470 МБ) скачивается при первом старте ml-api в том `hfcache`; пока она грузится, подбор работает на запасных векторах.

### Windows без make

В Git Bash из корня репозитория (нужны Docker Desktop и `uv`):

```bash
sh infra/scripts/gen-demo-env.sh
mkdir -p reports/seed
LLM_ENABLED=false ML_FAKE=false EMBEDDING_MODEL=multilingual-e5-small docker compose --env-file .env.demo --profile core --profile ml up -d --build --wait
for step in all grades families demo2 fsp-registry; do uv run python -m tools.seed $step --env-file .env.demo; done
docker compose --env-file .env.demo --profile core --profile ml up -d --build --no-deps --force-recreate fsp-mock
```

Скрипты `*.sh` должны иметь окончания строк LF (правило в `.gitattributes`).

## Профили

| Профиль | Как запустить | ML | LLM |
|---|---|---|---|
| `lite` | `make up-lite` | настоящие эмбеддинги на CPU, правила, Natasha | выключена (`LLM_ENABLED=false`) |
| демо по умолчанию | `make up` без `.env` | заглушки (`ML_FAKE=true` в `.env.demo`) | заглушки |
| полный | `make up` с `.env`: `ML_FAKE=false`, `LLM_ENABLED=true`, `LLM_BASE_URL` | настоящие модели | OpenAI-совместимый сервер (на стенде команды — `llama-server` с Qwen3-VL-4B на хосте) |

Тест, грейд, подбор и офферы от профиля не зависят. Telegram-бот включается автоматически, если в окружении задан `TG_BOT_TOKEN`.

## Окружение

`make` берёт `.env`, если в нём задан `JWT_SECRET`, иначе `.env.demo` (создаётся автоматически со случайными секретами и `DEMO_MODE=true`). Для своего стенда: `cp .env.example .env` и замените все `CHANGE_ME`. Переменные — [configuration.md](configuration.md).

## Демо-данные

`make seed` наполняет витрину (сид по умолчанию — `tools/seed/config.yaml`, свой — `make seed SEED=42`):

- 400 кандидатов, 25 вымышленных компаний (2 на модерации), 80 вакансий, 300 офферов, история аналитики за 14 дней;
- 600 участников ФСП, 45 прошедших и 7 будущих соревнований, ≈ 40 % кандидатов привязаны к ФСП;
- грейды демо-кандидатов, банк заданий, герои демо с историей теста, откликами, приглашениями и регулярными заданиями;
- реестр ФСП с участником для входа жюри.

Сброс демо к исходному состоянию за минуту:

```bash
make demo-snapshot   # один раз после make seed
make demo-reset      # вернуть демо-данные к снапшоту (настоящие пользователи не трогаются)
make demo-warm       # прогреть кеши
```

## Демо-аккаунты

Пароль всех демо-аккаунтов — `demo-pass-1234`. Люди и компании вымышленные.

| Роль | Email | Что показывает |
|---|---|---|
| Кандидат | `anya@demo.fsp.test` | Студентка, Python; заявила Middle, не прошла, подтвердила Junior; есть в реестре ФСП — «Привязать ФСП» подтянет результаты |
| Кандидат | `dima@demo.fsp.test` | Backend на Go, 3 года опыта; есть в реестре ФСП |
| Кандидат | `boris@demo.fsp.test` | Backend Python без ФСП: провал Middle, через 35 дней — Middle подтверждён |
| Кандидат | `vika@demo.fsp.test` | AI Engineer, грейд из экспресс-теста |
| Кандидат | `gleb@demo.fsp.test` | Тест пройден с низкой честностью — «требует подтверждения» |
| Кандидат | `mira@demo.fsp.test` | 16 лет, согласие родителя есть — профиль публикуется |
| Кандидат | `timur@demo.fsp.test` | 15 лет, согласия родителя нет — профиль не публикуется |
| Кандидат для жюри | `jury-candidate@demo.fsp.test` | Без грейда: можно пройти экспресс-тест и привязать ФСП одной кнопкой |
| Работодатель | `olga@demo.fsp.test` | Владелец «Северный код» (проверена): подбор, приглашения, задания |
| Работодатель | `hr.gavan@demo.fsp.test`, `hr.neiron@demo.fsp.test`, `hr.pixel@demo.fsp.test` | Компании с вакансиями Backend, AI Engineer, Frontend и регулярными заданиями |
| Работодатель для жюри | `jury-hr@demo.fsp.test` | Проверенная компания |
| Администратор ФСП | `admin@demo.fsp.test` | Допуск заданий, модерация, реестр ФСП, профессии, аналитика |
| Массовые | `cand0001@…`, `hr01@demo.fsp.test` | Синтетическая витрина |

**Песочница жюри.** При `DEMO_MODE=true` кнопки «Демо для жюри» на лендинге (сборка с `VITE_JURY_MODE=true`) или `POST /api/v1/auth/jury` создают для каждого члена жюри свою пару «кандидат + работодатель с проверенной компанией». Кандидат песочницы проходит экспресс-тест (6–8 заданий, 3–5 минут), работодатель песочницы находит его в категории.

## Проверка

```bash
make ps                                            # статус контейнеров
make logs                                          # логи
curl http://localhost:28080/api/v1/healthz         # 200
curl http://localhost:28080/api/v1/taxonomy/professions
```

## Разработка без Docker-сборки приложения

```bash
make sync && make web-install                      # зависимости Python (uv) и фронта (pnpm)
make dev-core                                      # инфраструктура и core в Docker, ML на заглушках
pnpm --filter fsp-web dev                          # фронт на http://localhost:28173 с прокси API на :28080
```

Команды проверок — [testing.md](../quality/testing.md).

## Частые проблемы

| Симптом | Решение |
|---|---|
| Порт 28080 занят | `GATEWAY_PORT=28081` в `.env` / `.env.demo` |
| `set -eu` падает в `rabbitmq-init` | Окончания строк `*.sh` должны быть LF |
| Тесты Python на Windows падают с `UnicodeDecodeError` | Запускать с `PYTHONUTF8=1` |
| PDF-профиль не собирается вне Docker | Нужны системные библиотеки WeasyPrint (pango); в образе они есть |
| `/healthz` ml-api показывает `embedder: fallback` | Модель эмбеддингов ещё скачивается; подбор работает на запасных векторах |
