# Документация ФСП Карьера

Единая точка входа: каждый действующий документ — одной строкой ниже. Устаревшее удалено (история git). Правила работы с репозиторием — [AGENTS.md](../AGENTS.md).

**Читать с нуля:** [case.md](case.md) → [solution.md](solution.md) → [architecture/system.md](architecture/system.md) → [deploy.md](deploy.md).

## Продукт и сдача

| Документ | О чём |
|---|---|
| [case.md](case.md) | ТЗ за 5 минут: задача, критерии, что сдаём (оригинал — [tz-2026.pdf](tz-2026.pdf)) |
| [solution.md](solution.md) | Наше решение: ключевые идеи, отличия, соответствие ТЗ |
| [submission.md](submission.md) | Документ сдачи (в PDF/DOCX — `make submission-pdf`) |
| [pitch.md](pitch.md) | Питч и демо: сценарий, вау-моменты, чек-лист |
| [libraries.md](libraries.md) | Библиотеки с версиями и лицензиями (генерируется `make submission-libs`) |

## Архитектура

| Документ | О чём |
|---|---|
| [architecture/system.md](architecture/system.md) | Архитектура для защиты: схемы, сущности, потоки, вопросы и ответы |
| [architecture/services.md](architecture/services.md) | Сервисы и модули core, границы, владельцы |
| [architecture/stack.md](architecture/stack.md) | Технологии и почему они |
| [architecture/flows.md](architecture/flows.md) | Сценарии с диаграммами последовательностей |
| [architecture/data-model.md](architecture/data-model.md) | Таблицы БД |
| [architecture/api.md](architecture/api.md) | REST, схемы, SSE, internal API (справочник — [openapi.json](openapi.json)) |
| [architecture/messaging.md](architecture/messaging.md) | RabbitMQ, outbox/inbox, Redis, лимиты (справочник — [asyncapi.json](asyncapi.json)) |
| [architecture/decisions.md](architecture/decisions.md) | Журнал архитектурных решений (ADR) |
| [architecture/security.md](architecture/security.md) | Аутентификация, приватность, согласия, 152-ФЗ |
| [architecture/deployment.md](architecture/deployment.md) | Топология, compose, GPU, окружение |

## Тест, навыки, подбор

| Документ | О чём |
|---|---|
| [architecture/assessment.md](architecture/assessment.md) | Тест: семейства, «мир», Rasch + SPRT, грейды, ранжирование заданий и кандидатов |
| [architecture/skills.md](architecture/skills.md) | Граф навыков: типы, профессии, рост, софт-сигналы |
| [architecture/graph.md](architecture/graph.md) | Граф доказательств, доверие, сила |
| [architecture/matching.md](architecture/matching.md) | Подбор, ранжирование, рекомендации, uplift, `p_accept` |
| [architecture/ml.md](architecture/ml.md) | Модели, разбор резюме, LLM и режим без LLM |
| [architecture/metrics.md](architecture/metrics.md) | Метрики (v2 — §9), аналитика, живые прогоны |
| [architecture/evaluation.md](architecture/evaluation.md) | Эталоны, синтетика, демо-данные, `make eval` |

## Интеграции и интерфейсы

| Документ | О чём |
|---|---|
| [architecture/fsp.md](architecture/fsp.md) | ФСП: реестр, привязка, синхронизация, мок |
| [architecture/telegram.md](architecture/telegram.md) | Telegram-бот |
| [architecture/frontend.md](architecture/frontend.md) | SPA: маршруты, компоненты, состояние |
| [architecture/admin.md](architecture/admin.md) | Админка ФСП: что модерирует человек, что работает само |
| [design/v2/README.md](design/v2/README.md) | Эталон вида: экраны HTML, экран → маршрут → задача |
| [design/v3/landing/README.md](design/v3/landing/README.md) | Макет лендинга (E39-35) |
| [design/claude-design/brief.md](design/claude-design/brief.md) | Смысл и данные экранов (бриф для Claude Design) |
| [design/brief.md](design/brief.md) | Бриф v1; действует словарь текстов §7 |
| [design/brand.md](design/brand.md) | Бренд ФСП: цвета, логотипы, контрасты (файлы — `design/assets/`) |
| [ux/ux-spec.md](ux/ux-spec.md) | UX: что пользователь получает на каждой странице, стиль |
| [ux/feedback.md](ux/feedback.md) | Правки команды по стенду и их статус |

## Запуск и демо

| Документ | О чём |
|---|---|
| [deploy.md](deploy.md) | Развёртывание: профили lite/standard/full, команды, демо-сброс |

## Процесс

| Документ | О чём |
|---|---|
| [process/plan.md](process/plan.md) | Очередь задач для агентов (`/vibe`), журнал |
| [process/backlog.md](process/backlog.md) | Эпики и задачи с критериями готовности |
| [process/blocks.md](process/blocks.md) | Работа двумя блоками: зоны, контракты стыка, общие файлы |
| [process/workflow.md](process/workflow.md) | Git, контракты, Definition of Done, работа с агентами |
| [notes/qa-2026.md](notes/qa-2026.md) | Ответы организаторов (сессия и чат) |
| [notes/questions.md](notes/questions.md) | Открытые и закрытые вопросы к организаторам |
| [notes/research.md](notes/research.md) | Как это делают другие: платформы, наука, нормы |

## Отчёты

| Документ | О чём |
|---|---|
| [reports/metrics-2026-10-07.md](reports/metrics-2026-10-07.md) | Прогон метрик качества на дату |
| [reports/matching-weights-2026-10-07.md](reports/matching-weights-2026-10-07.md) | Подбор весов ранжирования |
| [reports/design-v2-check.md](reports/design-v2-check.md) | Сверка экранов с дизайном v2 |
| [reports/review-b1.md](reports/review-b1.md) | Ревью задач блока 1 |
| [reports/review-b2.md](reports/review-b2.md) | Ревью задач блока 2 |
| [../reports/e39-check.md](../reports/e39-check.md) | Прогон глазами жюри после E39 (E39-36) |
| [../reports/admin-audit.md](../reports/admin-audit.md) | Автоаудит админки (E39-30) |

## Правила

- Документация — часть кода: меняешь контракт, схему или формулу — правишь документ в том же PR. Решения — в [decisions.md](architecture/decisions.md).
- Источник правды для API — `openapi.json` и `asyncapi.json` из сервисов; `api.md` и `messaging.md` описывают договорённости.
- Новые документы не заводим без необходимости: дополняем подходящий раздел и строку в этом файле.
- Ссылки проверяет `uv run python tools/check_links.py` (в CI и `make lint`).
