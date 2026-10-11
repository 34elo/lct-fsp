# ml

ML-сервис: эмбеддинги, разбор резюме, разбор запроса, сопоставление навыков, черновики ключей и объяснений, генерация заданий LLM. Решений не принимает — только извлекает и формулирует ([ml.md](../../docs/mechanics/ml.md)).

| Процесс | Команда | Что делает |
|---|---|---|
| `ml-api` | `uvicorn fsp_ml.main:app --port 8100` | Синхронный HTTP для core (`/v1/*`, `/healthz`) |
| `ml-worker-llm` | `python -m fsp_ml.worker llm` | Очередь `ml.llm`: разбор резюме, генерация заданий; `prefetch=1`, приоритеты |
| `ml-worker-code` | `python -m fsp_ml.worker code` | Очередь `ml.code` |

## Ключевые файлы (`fsp_ml/`)

| Файл | Что |
|---|---|
| `main.py` | Сборка ml-api, эмбеддинги, сопоставление навыков |
| `embedder.py` | sentence-transformers на CPU, загрузка модели с HF в фоне, запасные векторы |
| `resume_text.py`, `resume_rules.py`, `resume_ner.py`, `resume_structure.py`, `resume_parser.py` | Разбор резюме: текст → правила → Natasha → LLM → проверка цитат |
| `query_parse.py` | Разбор запроса работодателя |
| `skill_pipeline.py`, `skill_moderation.py`, `skill_card.py`, `normalize.py`, `taxonomy.py` | Конвейер новых навыков и снимок справочника |
| `family_key.py`, `family_bank.py`, `answer_explain.py` | Черновик ключа, генератор и решатель заданий, текст «Объясни ответ» |
| `llm.py` | OpenAI-совместимый клиент с JSON-схемой |
| `handlers.py`, `worker.py` | Команды очередей → события-результаты |
| `fake.py` | Детерминированные ответы для `ML_FAKE=true` |

Промпты — `prompts/<задача>/v<N>.j2`; фикстуры — `fixtures/`.

## Режимы

`ML_FAKE=true` — заглушки; `LLM_ENABLED=false` — правиловые ветки без LLM; модель эмбеддингов — `EMBEDDING_MODEL` (`bge-m3` или `multilingual-e5-small`), LLM — `LLM_BASE_URL`, `LLM_MODEL`.

```bash
ML_FAKE=true uv run --package fsp-ml uvicorn fsp_ml.main:app --reload
uv run pytest services/ml -q
```

Пакет называется `fsp_ml`, а не `app`: в workspace несколько сервисов.
