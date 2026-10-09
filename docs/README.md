# Документация ФСП Карьера

**Читать с нуля:**
1. [case.md](case.md) — ТЗ за 5 минут.
2. [solution.md](solution.md) — наше решение.
3. [architecture/system.md](architecture/system.md) — архитектура для защиты.
4. [process/plan.md §4.2](process/plan.md) — что делаем сейчас.

Запустить проект — [deploy.md](deploy.md). Сдать — [submission.md](submission.md).

## Структура

```
docs/
├── case.md              ТЗ (выжимка), критерии, что сдаём · оригинал — tz-2026.pdf
├── solution.md          решение: ключевые идеи, отличия, соответствие ТЗ
├── submission.md        документ сдачи (→ PDF/DOCX: make submission-pdf)
├── deploy.md            развёртывание, профили lite/standard/full, команды
├── pitch.md             питч и демо: сценарий, вау-моменты, чек-лист
├── libraries.md         библиотеки с версиями (генерируется)
├── openapi.json         REST API (генерируется: make openapi)
├── asyncapi.json        события и команды (генерируется: make asyncapi)
├── product.md           продуктовый анализ v1 (до ТЗ): персоны, рынок, правила — частично устарел
├── architecture/
│   ├── system.md        архитектура для защиты: схемы, сущности, действия, вопросы и ответы
│   ├── assessment.md    тест: семейства, мир, Rasch + SPRT, грейды, ранжирование заданий и кандидатов, API
│   ├── overview.md      идея, принципы, контейнеры, потоки
│   ├── services.md      сервисы, модули core, владельцы
│   ├── stack.md         технологии и обоснования
│   ├── graph.md         граф доказательств
│   ├── skills.md        граф навыков: типы, профессии, рост
│   ├── matching.md      подбор, ранжирование, рекомендации
│   ├── ml.md            модели, резюме, доверие, LLM и режим без LLM
│   ├── data-model.md    таблицы
│   ├── api.md           REST, схемы, SSE, internal API
│   ├── messaging.md     RabbitMQ, Redis
│   ├── flows.md         сценарии с диаграммами
│   ├── fsp.md           fsp-connector: порт ФСП, мок, OIDC, синхронизация
│   ├── telegram.md      бот
│   ├── frontend.md      SPA: маршруты, компоненты, состояние
│   ├── admin.md         админка ФСП: что модерирует человек, что работает само, меню
│   ├── security.md      аутентификация, приватность, согласия, 152-ФЗ
│   ├── metrics.md       метрики (v2 — §9), аналитика, живые прогоны
│   ├── evaluation.md    эталоны, синтетика, демо-данные, make eval
│   ├── deployment.md    топология, compose, GPU, окружение
│   └── decisions.md     журнал решений (ADR)
├── design/
│   ├── v2/              ЭТАЛОН ВИДА: 127 экранов HTML, fsp2.css, README (экран → маршрут → задача)
│   ├── claude-design/   бриф и промпты для Claude Design (смысл экранов, данные API)
│   ├── pack/            пакет дизайна v1: компоненты, токены, PNG старых экранов
│   ├── brief.md         бриф v1; словарь текстов §7 действует
│   ├── brand.md         бренд ФСП: токены и правила
│   └── assets/          файлы брендбука
├── ux/
│   ├── ux-spec.md       UX: стиль «показываем, а не объясняем», что даём на каждой странице
│   └── feedback.md      UX-правки команды (применяет задача E35-11)
├── process/
│   ├── plan.md          очередь задач для агентов (/vibe), журнал
│   ├── backlog.md       эпики и задачи с критериями готовности
│   ├── blocks.md        работа двумя блоками: зоны, контракты стыка, точки стыковки
│   ├── workflow.md      git, контракты, DoD, работа с агентами
│   ├── kickoff.md       старт проекта (исторический)
│   └── archive/         план v1
├── notes/
│   ├── qa-2026.md       ответы организаторов (сессия и чат)
│   ├── audit-2026-10-07.md  аудит проекта
│   ├── questions.md     открытые вопросы
│   └── research.md      как это делают другие
└── reports/             отчёты прогонов (метрики)
```

## Что читать под задачу

| Задача | Документы |
|---|---|
| Тест, категории, ранжирование | [assessment.md](architecture/assessment.md), [solution.md](solution.md), ADR в [decisions.md](architecture/decisions.md) |
| Бэкенд | [services.md](architecture/services.md), [data-model.md](architecture/data-model.md), [api.md](architecture/api.md), [messaging.md](architecture/messaging.md), [process/blocks.md](process/blocks.md) |
| Фронтенд, вид экранов | [design/v2/README.md](design/v2/README.md), [claude-design/brief.md](design/claude-design/brief.md), [ux/ux-spec.md](ux/ux-spec.md), [frontend.md](architecture/frontend.md) |
| ML | [ml.md](architecture/ml.md), [skills.md](architecture/skills.md), [matching.md](architecture/matching.md), [evaluation.md](architecture/evaluation.md) |
| ФСП | [fsp.md](architecture/fsp.md) |
| Бот | [telegram.md](architecture/telegram.md) |
| Метрики, валидация | [metrics.md §9](architecture/metrics.md), [reports/](reports/), `make metrics` |
| Инфраструктура и запуск | [deploy.md](deploy.md), [deployment.md](architecture/deployment.md), [security.md](architecture/security.md) |
| Сдача и питч | [submission.md](submission.md), [pitch.md](pitch.md), [notes/qa-2026.md](notes/qa-2026.md) |

## Правила

- Документация — часть кода: меняешь контракт, схему или формулу — правишь документ в том же PR. Решения — в [decisions.md](architecture/decisions.md).
- Источник правды для API — `openapi.json` и `asyncapi.json` из сервисов; `api.md` и `messaging.md` описывают договорённости.
- Вид экранов — [design/v2](design/v2/README.md); нет пункта меню или ссылки без рабочего экрана (AGENTS.md, UX-правило).
- Новые документы не заводим без необходимости: дополняем подходящий раздел.
