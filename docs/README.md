# Документация ФСП Карьеры

Начать с нуля: [кейс](product/case.md) → [архитектура](architecture/overview.md) → [механика теста](mechanics/assessment.md) → [механика подбора](mechanics/matching.md) → [запуск](operations/running.md).

## Продукт

| Документ | О чём |
|---|---|
| [product/case.md](product/case.md) | Кейс и требования ТЗ кратко (оригинал — [tz-2026.pdf](tz-2026.pdf)) |
| [product/requirements.md](product/requirements.md) | Каждое требование ТЗ → как и где реализовано |
| [product/features.md](product/features.md) | Весь функционал по ролям |
| [product/qa-session.md](product/qa-session.md) | Сводка сессии вопросов и ответов с организаторами |
| [product/questions.md](product/questions.md) | Наши вопросы организаторам и ответы |

## Архитектура

| Документ | О чём |
|---|---|
| [architecture/overview.md](architecture/overview.md) | Функциональная и компонентная архитектура, потоки, концепции за рамками MVP (защита от фиктивных вакансий, ATS) |
| [architecture/modules.md](architecture/modules.md) | Структура репозитория, модули и их мини-документация |
| [architecture/data-model.md](architecture/data-model.md) | Таблицы баз данных |
| [architecture/api.md](architecture/api.md) | REST API, ошибки, internal API (спецификация — [openapi.json](openapi.json)) |
| [architecture/messaging.md](architecture/messaging.md) | События, команды, очереди, outbox/inbox (каталог — [asyncapi.json](asyncapi.json)) |
| [architecture/security.md](architecture/security.md) | Аутентификация, роли, персональные данные, 152-ФЗ |
| [architecture/frontend.md](architecture/frontend.md) | Устройство SPA, экраны, UX-правила |
| [design.md](design.md) | Дизайн-система: токены, компоненты, принципы |

## Механики

| Документ | О чём |
|---|---|
| [mechanics/assessment.md](mechanics/assessment.md) | Тест: семейства заданий, «мир», Rasch + SPRT, грейды, антисписывание, устойчивость к утечке |
| [mechanics/matching.md](mechanics/matching.md) | Категоризация, потребность → категории, ранжирование, подбор под вакансию |
| [mechanics/contact.md](mechanics/contact.md) | Интерес, приглашение, отклик, раскрытие контактов |
| [mechanics/skills.md](mechanics/skills.md) | Граф навыков, доказательства, доверие, рост справочника |
| [mechanics/fsp.md](mechanics/fsp.md) | Интеграция с реестром ФСП и FSP ID |
| [mechanics/ml.md](mechanics/ml.md) | Модели, разбор резюме, где участвует LLM |

## Эксплуатация и качество

| Документ | О чём |
|---|---|
| [operations/running.md](operations/running.md) | Сборка, запуск, демо-данные и демо-аккаунты |
| [operations/infrastructure.md](operations/infrastructure.md) | Docker Compose, gateway, порты, CI/CD, продовый стенд |
| [operations/configuration.md](operations/configuration.md) | Переменные окружения и `scoring.yaml` |
| [quality/validation.md](quality/validation.md) | Процедура валидации теста и подбора, результаты |
| [quality/testing.md](quality/testing.md) | Тесты и проверки кода |
| [libraries.md](libraries.md) | Библиотеки с версиями и лицензиями (`make libraries`) |

## Решения

[Журнал архитектурных решений (ADR)](adr/README.md) — 24 решения: что выбрали, почему и с какими последствиями.
