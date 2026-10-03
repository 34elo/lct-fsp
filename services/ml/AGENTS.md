# AGENTS.md — ml

Назначение: ml-api (HTTP для core), ml-worker-llm (`ml.llm`, prefetch=1), ml-worker-code (`ml.code`). Заглушки `ML_FAKE=true` (E0-9); при `ML_FAKE=false` реально работает разбор резюме через LLM (E3-3), остальное — E10-* и др.

## Команды
- `ML_FAKE=true uv run --package fsp-ml uvicorn fsp_ml.main:app --reload` — ml-api
- `ML_FAKE=true uv run --package fsp-ml python -m fsp_ml.worker llm` — worker очереди `ml.llm` (или `code`)
- `uv run pytest services/ml -q` — тесты (отдельно от core: у них разные пакеты)
- `uv run ruff check services/ml` — линтер

## Ключевые файлы
- `fsp_ml/main.py` — ml-api: `/v1/query/parse`, `/v1/embeddings`, `/v1/skills/resolve`, `/healthz`
- `fsp_ml/normalize.py`, `taxonomy.py` — нормализация и быстрый путь resolve (снимок графа из core); `embedder.py` — bge-m3 или фейк
- `fsp_ml/fake.py` — детерминированные ответы по контрактам `fsp_contracts.ml`
- `fsp_ml/handlers.py` — команда → события `ml.*.completed/failed` (`HANDLERS`, `handle`; `resume_parse_llm` — реальный)
- `fsp_ml/llm.py` — OpenAI-совместимый клиент (JSON-схема); `resume_text.py`, `resume_rules.py`, `resume_parser.py` — разбор резюме; промпты — `prompts/<task>/v<N>.j2`
- `fsp_ml/worker.py` — подписка на `ml.llm` / `ml.code`, публикация результатов
- `fixtures/` — JSON-фикстуры резюме и анализа кода (вымышленные данные)
- Сценарии ошибок: `object_key` на `.scanned` → `ml.resume.failed`; `github_login=not-found` → `ml.code.failed`

## Правила
- Пакет называется `fsp_ml` (не `app`): в воркспейсе несколько сервисов, имена `app` конфликтуют.
- `message_id` результата = uuid5(команда, тип): повторная доставка даёт тот же дубль, inbox отбрасывает.
- При `ML_FAKE=false` без модели/снимка графа ml-api отвечает 503 `ml_unavailable`, воркеры не стартуют. `EMBEDDING_MODEL_PATH` включает реальный bge-m3.
- Документы: docs/architecture/ml.md, messaging.md §2–3, api.md §2.10.
