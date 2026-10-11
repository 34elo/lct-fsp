# Модули и структура репозитория

```
apps/web/               React SPA для трёх ролей
packages/contracts/     pydantic-контракты: события, команды, DTO
packages/platform/      общая платформа Python-сервисов: БД, outbox/inbox, RabbitMQ, JWT, лимиты, логи
packages/ui/            дизайн-система @fsp/ui
services/core/          основной бэкенд: api + worker + scheduler
services/ml/            ML: эмбеддинги, разбор резюме и запросов, LLM-функции
services/fsp-connector/ интеграция с ФСП: порт, реестр, привязка, синхронизация
services/fsp-mock/      имитация API ФСП с OAuth/OIDC
services/bot/           Telegram-бот
data/                   справочник навыков, профессии, правила ФСП, scoring.yaml
tools/                  демо-данные, синтетика, валидация, нагрузка
infra/                  Docker, Caddy, скрипты развёртывания
docs/                   документация
```

У каждого сервиса, пакета и модуля core — свой `README.md` с назначением, ключевыми файлами и командами.

## Сервисы и пакеты

| Компонент | Мини-документация |
|---|---|
| core | [services/core](../../services/core/README.md) |
| ml | [services/ml](../../services/ml/README.md) |
| fsp-connector | [services/fsp-connector](../../services/fsp-connector/README.md) |
| fsp-mock | [services/fsp-mock](../../services/fsp-mock/README.md) |
| bot | [services/bot](../../services/bot/README.md) |
| web | [apps/web](../../apps/web/README.md) |
| @fsp/ui | [packages/ui](../../packages/ui/README.md) |
| fsp-contracts | [packages/contracts](../../packages/contracts/README.md) |
| fsp-platform | [packages/platform](../../packages/platform/README.md) |
| data | [data](../../data/README.md) |
| tools | [tools](../../tools/README.md) |
| infra | [infra](../../infra/README.md) |

## Модули core

| Модуль | Назначение | Таблицы |
|---|---|---|
| [identity](../../services/core/app/identity/README.md) | Пользователи, вход, токены, email | `users`, `refresh_tokens`, `email_verifications`, `user_profiles` |
| [consents](../../services/core/app/consents/README.md) | Согласия | `consents` |
| [candidates](../../services/core/app/candidates/README.md) | Анкета, видимость, PDF, удаление | `candidates`, `category_disputes` |
| [resumes](../../services/core/app/resumes/README.md) | Резюме → доказательства | `resumes`, `experience`, `education` |
| [taxonomy](../../services/core/app/taxonomy/README.md) | Справочник навыков и профессий, рост | `skills`, `roles`, `role_skills`, … |
| [graph](../../services/core/app/graph/README.md) | Доказательства, доверие, ФСП-факты | `evidence`, `candidate_skills`, `fsp_*` |
| [assessment](../../services/core/app/assessment/README.md) | Тест, грейды, банк заданий | `surveys`, `families`, `attempts`, `responses`, `grades`, `regular_tasks`, … |
| [companies](../../services/core/app/companies/README.md) | Компании и команды HR | `companies`, `company_members`, … |
| [vacancies](../../services/core/app/vacancies/README.md) | Вакансии | `vacancies`, `vacancy_skills` |
| [matching](../../services/core/app/matching/README.md) | Подбор и поиск | `needs`, `matches`, `category_subscriptions`, … |
| [offers](../../services/core/app/offers/README.md) | Интерес, приглашения, отклики, контакты | `offers`, `offer_events`, `contact_reveals`, … |
| [recommendations](../../services/core/app/recommendations/README.md) | Показы и подстройка выдачи | `impressions`, `rec_feedback` |
| [notifications](../../services/core/app/notifications/README.md) | Уведомления в UI и Telegram | `notifications` |
| [telegram](../../services/core/app/telegram/README.md) | Привязка Telegram, internal API бота | `telegram_accounts` |
| [fsp](../../services/core/app/fsp/README.md) | Клиент fsp-connector, реестр в админке | — |
| [credentials](../../services/core/app/credentials/README.md) | Open Badge 3.0 | `issued_credentials` |
| [views](../../services/core/app/views/README.md) | Публичные профили, бейджи, статистика | `profile_views` |
| [analytics](../../services/core/app/analytics/README.md) | События, воронки, живые прогоны | `analytics_events`, `live_runs` |
| [jobs](../../services/core/app/jobs/README.md) | Задачи по расписанию | — |
| [demo](../../services/core/app/demo/README.md) | Песочница жюри, снапшот демо | — |

## Границы

- Модуль core пишет только свои таблицы; чужие данные — через `service.py` модуля-владельца. Например, грейды пишет только `assessment`, подбор читает их через `assessment.service.get_grades_many`.
- ml, fsp-connector и bot не ходят в БД core — только события, команды и internal API.
- `fsp-contracts` не зависит от `fsp-platform` (проверяет import-linter).
- Фронт берёт данные только через сгенерированный клиент; цвета и шрифты — только из токенов `@fsp/ui`.
