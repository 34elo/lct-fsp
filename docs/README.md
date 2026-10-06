# Документация ФСП Карьера

> ⚠️ **Читать с нуля:** [case.md](case.md) (ТЗ за 5 минут) → [solution.md](solution.md) (наше решение, **v2, рабочая версия** от 2026-10-05) → [process/plan.md §4.2](process/plan.md#42-очередь-v2) (что делаем). Документы в `architecture/` описывают текущую реализацию и обновляются по мере задач.

## Структура

```
docs/
├── case.md              ТЗ (выжимка), критерии, что сдаём
├── tz-2026.pdf          оригинал ТЗ
├── pitch.md           план питча и демо: три мысли, слайды, сценарий, вау-моменты, чек-лист
├── solution.md          решение v2: ключевые идеи, отличия, питч, соответствие ТЗ (рабочая версия)
├── product.md           продукт: выжимка, персоны, механики, правила, метрики, демо, питч
├── architecture/
│   ├── overview.md      идея, принципы, контейнеры, потоки, карта документов
│   ├── services.md      5 сервисов, модули core, владельцы, трассировка требований
│   ├── stack.md         технологии и обоснования
│   ├── graph.md         граф доказательств: вершины, рёбра, хранение, обходы, API подграфа
│   ├── skills.md        граф навыков: ядро + рост, модерация, склейка синонимов, софт-сигналы
│   ├── matching.md      подбор, взаимный подбор, похожие, подстройка в сессии, uplift
│   ├── system.md        v2: архитектура для защиты — схемы Mermaid, блоки, сущности, действия, метрики, вопросы и ответы
│   ├── assessment.md    v2: тест, семейства, калибровка, ранжирование заданий и кандидатов, API
│   ├── ml.md            модели и железо, резюме, доверие, грейд, ДНК кода, тест, интервью
│   ├── data-model.md    таблицы (DDL)
│   ├── api.md           REST, схемы, SSE, internal, ml-api, callback бота
│   ├── messaging.md     RabbitMQ: события, очереди, приоритеты; Redis: кеш, лимиты
│   ├── flows.md         сценарии F1–F14 с диаграммами
│   ├── fsp.md           fsp-connector: порт ФСП, мок, привязка, синхронизация, правила дисциплин
│   ├── telegram.md      бот: команды, состояния, шаблоны сообщений
│   ├── frontend.md      SPA: маршруты, компоненты, состояние
│   ├── security.md      аутентификация, анонимность, согласия, ответственный ИИ
│   ├── metrics.md       сбор событий, метрики, живые прогоны, SLO, дашборды
│   ├── evaluation.md    эталоны, синтетический рынок, демо-данные, make eval
│   ├── deployment.md    топология, compose, GPU, окружение, demo-reset
│   └── decisions.md     журнал архитектурных решений (ADR)
├── design/
│   ├── brief.md         что на экранах, фирменные элементы, вау-моменты
│   ├── prompt.md        промпт для Claude Design
│   ├── brand.md         токены и правила бренда
│   └── assets/          файлы брендбука ФСП
├── process/
│   ├── kickoff.md       что сделать до кода
│   ├── plan.md          план по дням, очередь задач для агентов, журнал ночей
│   ├── workflow.md      репозиторий, git, контракты, DoD, работа с агентами, заметки
│   └── backlog.md       эпики и задачи
└── notes/
    ├── questions.md     открытые вопросы и решения
    └── research.md      как это делают другие: платформы, наука, нормы
```

## Что читать

| Задача | Документы |
|---|---|
| Понять проект с нуля | [case.md](case.md) → [solution.md](solution.md) → [architecture/overview.md](architecture/overview.md) → [process/workflow.md](process/workflow.md) |
| Бэкенд | [services.md](architecture/services.md), [graph.md](architecture/graph.md), [data-model.md](architecture/data-model.md), [api.md](architecture/api.md), [messaging.md](architecture/messaging.md), [flows.md](architecture/flows.md) |
| Тест и категории (v2) | [assessment.md](architecture/assessment.md), [solution.md](solution.md) |
| ML | [ml.md](architecture/ml.md), [skills.md](architecture/skills.md), [matching.md](architecture/matching.md), [evaluation.md](architecture/evaluation.md) |
| Фронтенд | [frontend.md](architecture/frontend.md), [api.md](architecture/api.md) §3–4, [design/brief.md](design/brief.md), [design/brand.md](design/brand.md) |
| Бот | [telegram.md](architecture/telegram.md), [api.md](architecture/api.md) §2.9 |
| Интеграция ФСП | [fsp.md](architecture/fsp.md) |
| Инфраструктура | [deployment.md](architecture/deployment.md), [security.md](architecture/security.md) |
| Метрики и питч | [metrics.md](architecture/metrics.md), [evaluation.md](architecture/evaluation.md), [product.md](product.md) §15, §18 |
| Задачи и старт | [process/kickoff.md](process/kickoff.md), [process/plan.md](process/plan.md), [process/backlog.md](process/backlog.md) |

## Правила

- Документация — часть кода: меняешь контракт, схему или формулу — правишь документ в том же PR.
- ⚠️ — допущение до ответа организаторов или экспертов ([notes/questions.md](notes/questions.md)). 🚀 — вау-фича поверх ядра.
- Новые документы не заводим без необходимости: дополняем подходящий раздел.
- После старта кода источник правды для API — OpenAPI и AsyncAPI из сервисов. `api.md` и `messaging.md` описывают договорённости и то, чего нет в спецификациях.
