# AGENTS.md

Правила для ИИ-агентов (Claude Code, Codex, Cursor и др.) и людей, работающих с репозиторием. Файл короткий намеренно: детали — в `docs/`. **Читай только документы, нужные под задачу** (таблица ниже), а не всё подряд.

## Проект

**ФСП Карьера** — платформа найма в ИТ с обратной механикой для кейса Федерации спортивного программирования. Кандидат проходит опрос и тест (у каждого свой «мир», общая шкала, Rasch + SPRT) и получает категорию «профессия × грейд»; доказательства и результаты ФСП дают доверие ○○○○…●●●● и место внутри категории. Работодатель описывает потребность, видит категории и кандидатов с объяснением и сам выходит на контакт: интерес → приглашение с обязательной вилкой (сайт и Telegram). Хакатон, 4–5 человек, домашний сервер с одной GPU; обязательный путь работает без GPU и LLM.

> Категория определяется опросом и **тестом**, а не резюме. Решение — [docs/solution.md](docs/solution.md), выжимка ТЗ — [docs/case.md](docs/case.md). **Карта всех документов — [docs/README.md](docs/README.md)** (по строке на документ); устаревшее удалено (смотри историю git).

> 🔀 **Работа идёт двумя параллельными блоками** (ветки `block1` и `block2`, этап 0 — `stage0`). Кто чем владеет, что лежит на стыке, как править общие файлы и сливать ветки — [docs/process/blocks.md](docs/process/blocks.md). Правило: свою зону правишь, чужую только вызываешь через `service.py` или контракт.

## Репозиторий

```
apps/web/                 React + Vite + TS (кандидат, работодатель, админ)
services/core/            FastAPI: api + worker (FastStream) + scheduler — домен, граф, подбор, офферы
services/ml/              FastAPI: ml-api + ml-worker-llm + ml-worker-code — резюме, навыки, LLM-черновики (опционально)
services/fsp-connector/   порт ФСП, привязка, синхронизация, вебхуки (своя БД)
services/bot/             aiogram 3, без бизнес-логики
services/fsp-mock/        имитация API ФСП
packages/contracts/       pydantic-схемы событий, команд, DTO — общие для всех сервисов
packages/platform/        общая платформа: конфиг, БД, outbox/inbox, FastStream, JWT, логи
packages/ui/              @fsp/ui: токены и компоненты фронта (дизайн v2 — docs/design/v2)
tools/agents/vibe.sh      запасной запуск /vibe без открытого чата
data/                     ядро навыков, правила ФСП, банк вопросов, scoring.yaml, обезличенные эталоны
tools/                    seed (демо), synth (синтетический рынок), eval (метрики)
infra/                    compose, Caddy, Prometheus/Grafana, скрипты
docs/                     документация (карта — docs/README.md)
```

Новый сервис: `make new-service NAME=<имя>` (шаблон `tools/service-template`). Работа идёт двумя блоками — [docs/process/blocks.md](docs/process/blocks.md).

## Что читать под задачу

| Задача | Читай |
|---|---|
| Любая | этот файл + задача в [backlog.md](docs/process/backlog.md) + **[blocks.md](docs/process/blocks.md) §0 и §8** (два блока: зона, стык, общие файлы) |
| Понять кейс и решение с нуля | [case.md](docs/case.md) → [solution.md](docs/solution.md) (v2) → [system.md](docs/architecture/system.md) (архитектура) |
| Тест, категории, ранжирование v2 (E20–E30) | [assessment.md](docs/architecture/assessment.md) (нужный раздел), [solution.md](docs/solution.md), ADR-018…024 в [decisions.md](docs/architecture/decisions.md) |
| Что делать сейчас, очередь агентов | [plan.md](docs/process/plan.md) (§3 дни, §4 очередь) |
| Модели БД, миграции | [data-model.md](docs/architecture/data-model.md) (нужный раздел) |
| Эндпоинт | [api.md](docs/architecture/api.md) (нужная строка каталога + схема §3) |
| События, очереди, кеш, лимиты | [messaging.md](docs/architecture/messaging.md) |
| Граф, доверие, грейд | [graph.md](docs/architecture/graph.md), [ml.md](docs/architecture/ml.md) §3–5 |
| Навыки: конвейер, рост, софт-сигналы | [skills.md](docs/architecture/skills.md) |
| Подбор, рекомендации, uplift, `p_accept` | [matching.md](docs/architecture/matching.md), [ml.md](docs/architecture/ml.md) §6 |
| ML: резюме, GitHub, тест, интервью | [ml.md](docs/architecture/ml.md) (нужный раздел) |
| ФСП | [fsp.md](docs/architecture/fsp.md) |
| Бот | [telegram.md](docs/architecture/telegram.md) |
| Фронт | [frontend.md](docs/architecture/frontend.md), **вид экранов — [design/v2/README.md](docs/design/v2/README.md)** (макет экрана → маршрут → задача E38), смысл и данные экранов — [design/claude-design/brief.md](docs/design/claude-design/brief.md), UX-правила — [ux/ux-spec.md](docs/ux/ux-spec.md), компоненты — `packages/ui` |
| Редизайн, вид экранов, `packages/ui` | **v2:** [docs/design/v2/README.md](docs/design/v2/README.md) (эталон вида, задачи E38); лендинг — [docs/design/v3/landing](docs/design/v3/landing/README.md) |
| Метрики, события аналитики | [metrics.md](docs/architecture/metrics.md) (v2 — §9) |
| Эталоны, синтетика, seed, eval | [evaluation.md](docs/architecture/evaluation.md) |
| Инфраструктура | [deployment.md](docs/architecture/deployment.md), [security.md](docs/architecture/security.md) |
| Почему так решили | [decisions.md](docs/architecture/decisions.md) |

## Правила

1. **Документы — источник правды.** Код не противоречит `docs/architecture/` и `packages/contracts/`. Хочешь иначе — сначала предложи. Принятое решение записывается в [decisions.md](docs/architecture/decisions.md).
2. **Контракты первыми.** Меняешь API или событие — в том же PR правишь `packages/contracts`, [api.md](docs/architecture/api.md) / [messaging.md](docs/architecture/messaging.md). Ломающее изменение — новый `schema_version` или новое имя.
3. **Границы сервисов.**
   - ml, fsp-connector и bot не ходят в БД core: только события, команды и internal API.
   - Модули core общаются через `service.py` друг друга, в чужие `repo` и `models` не лезут (import-linter).
4. **Детерминированное ядро.** Доверие, грейд, скоринг, uplift, `p_accept` считаются формулами из `scoring_config`. LLM только извлекает данные и формулирует текст: ответ по JSON-схеме, затем валидация. Навык из резюме без найденной в тексте цитаты отбрасывается.
5. **Приватность.**
   - ПДн нет в логах, аналитике и промптах для обоснований.
   - Работодатель до принятия оффера или отклика получает только DTO карточки: без контактов, остальное — по настройкам видимости кандидата (ФИО — только с его согласия; ADR-027).
   - Модели только локальные. Наружу ходим только в GitHub, Telegram и ФСП.
   - Никакого вывода эмоций или «личности» из голоса, мимики, тона.
6. **Безопасность.**
   - Секреты только в `.env`: не читать, не печатать, не коммитить.
   - Код кандидатов только читаем, никогда не выполняем.
   - Файлы проверяем по сигнатуре.
7. **Одна GPU.** В LLM ходим только через ml-api (синхронно) или очередь `ml.llm` (приоритеты, `prefetch=1`). Из core напрямую в llama-server не ходим. Без GPU разрабатываем с `ML_FAKE=true`.
8. **Надёжность сообщений.** Событие пишется в outbox в той же транзакции. Обработчик идемпотентен (inbox) и сверяет версии (`profile_version`, `vacancy.version`).
9. **Маленькие изменения.**
   - Одна задача — одна ветка — один PR.
   - Не рефакторить вне задачи.
   - Не добавлять зависимости без причины.
   - Не создавать новые документы и файлы-заметки без просьбы.
10. **Тесты обязательны:**
    - формулы — юнит-тесты на примеры из документации;
    - эндпоинты — проверка прав («чужой ресурс → 404»);
    - обработчики событий — повторная доставка не меняет результат.
11. **Язык.**
    - Документация, UI, тексты бота — русский.
    - Код, идентификаторы, имена веток — английский.
    - Коммиты — Conventional Commits, описание по-русски: `feat(core/offers): лимит офферов в сутки`.

## UX-правило

- **Нет пункта меню, ссылки или кнопки без работающего экрана.** Не готово — скрываем, заглушку («раздел готовится») не показываем.
- Каждый экран отвечает на два вопроса: «где я?» и «что делать дальше?» — одно главное действие на экран.
- Тексты — по словарю из `docs/design/brief.md` §7.

## Стиль

- **Python 3.12:** ruff (lint + format), type hints везде, Pydantic v2, SQLAlchemy 2 async, structlog с `correlation_id`. Деньги — `int` ₽/мес, время — UTC. Ошибки API — Problem Details с машинным `code`.
- **TypeScript:** strict. Данные только через сгенерированные orval-хуки (`apps/web/src/api` руками не правим). Цвета и шрифты только из токенов. Каждый экран проверяем на 375 px и в тёмной теме.
- **Тесты:** pytest (`-q`), testcontainers для PostgreSQL, RabbitMQ, Redis. vitest и Playwright на фронте.

## Команды

Основные: `make sync`, `make lint` (с `make docs-links`), `make deadcode`, `make test`, `make e2e`, `make up` / `make up-lite`, `make seed`, `make demo-reset`, `make families-check`, `make eval`, `make eval-assessment`, `make metrics`, `make load`, `make openapi`, `make api-gen`, `make submission-pdf`. Полный список — `Makefile`, пояснения — [docs/deploy.md](docs/deploy.md).
Вывод сокращай: `pytest -q`, `docker compose logs --tail 50 <svc>`.

## Ловушки

- Java ≠ JavaScript, C ≠ C# — пары «точно разные» (`skill_distinct`) проверяются до слияния навыков.
- Новый навык (`provisional`) даёт силу доказательства не больше 0.25.
- Командные сигналы только повышают скор (`K_soft`, потолок β), за отсутствие сигналов не штрафуем.
- Пересчёт профиля сливается по `recomputed_at ≥ requested_at`, задержек не нужно.
- Компании в демо-данных только вымышленные.
- LLM — общий `llama-server` с Qwen3-VL-4B (умеет картинки) на хосте, `LLM_BASE_URL` + `LLM_API_KEY` из `.env`. Свою модель в compose не поднимаем.
- Порты 8000, 3000, 15432, 18000–18090, 19000 на ПК заняты другим проектом. Наши порты на хосте — 28xxx, наружу только gateway 28080.
- Сгенерированное (`apps/web/src/api`, lock-файлы, `infra/snapshots`) не читай целиком без нужды.

## В конце задачи

Коротко доложи:
1. что сделано;
2. как проверить (команды);
3. какие документы обновлены;
4. что осталось или какие есть вопросы.

Критерии готовности — [workflow.md §5](docs/process/workflow.md#5-definition-of-done).

Когда создаёшь сервис, положи в его корень свой `AGENTS.md` до 40 строк: назначение, команды, ключевые файлы, ссылки на разделы docs.
